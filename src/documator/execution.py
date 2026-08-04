import contextlib
import os
import re
import signal
import subprocess
from dataclasses import dataclass
from typing import NewType

from documator.domain import ExitCode, TimeoutSeconds, WorkingDir

Command = NewType("Command", str)
CapturedOutput = NewType("CapturedOutput", str)
OutputBlock = NewType("OutputBlock", str)
OutputSpan = NewType("OutputSpan", str)
Annotation = NewType("Annotation", str)
# Anything the run writes into the reader's vault, where `[[` and `#` are live syntax.
Emitted = NewType("Emitted", str)


@dataclass(frozen=True, slots=True)
class _Capture:
    output: CapturedOutput
    failure: Annotation | None


# The failure travels alongside the block, because command output can forge the
# annotation the block carries.
@dataclass(frozen=True, slots=True)
class ExecutedBlock:
    block: OutputBlock
    failure: Annotation | None


@dataclass(frozen=True, slots=True)
class ExecutedSpan:
    span: OutputSpan
    failure: Annotation | None


def execute_block(
    command: Command, working_dir: WorkingDir, timeout: TimeoutSeconds
) -> ExecutedBlock:
    capture = _capture(command, working_dir, timeout)
    return ExecutedBlock(_fenced(_annotated_body(capture)), capture.failure)


def execute_span(
    command: Command, working_dir: WorkingDir, timeout: TimeoutSeconds
) -> ExecutedSpan:
    capture = _capture(command, working_dir, timeout)
    return ExecutedSpan(_inline_or_promoted(capture), capture.failure)


def marker(note: Annotation) -> str:
    return f"[documator: {note}]"


def _capture(
    command: Command, working_dir: WorkingDir, timeout: TimeoutSeconds
) -> _Capture:
    # One pipe for both streams, so writes stay in the order the command made them.
    with subprocess.Popen(
        command,
        shell=True,
        cwd=working_dir.root,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        # A command's bytes are its own business; never let the locale decide, and
        # never let undecodable output abort the render.
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
        env=_terminal_free_env(),
    ) as process:
        try:
            output = CapturedOutput(process.communicate(timeout=timeout.root)[0])
        except subprocess.TimeoutExpired:
            return _Capture(
                _killed(process), Annotation(f"timed out after {timeout.root}s")
            )
    status = ExitCode(process.returncode)
    if status == 0:
        return _Capture(output, None)
    return _Capture(output, Annotation(f"exit {status}"))


# Kill the whole session, else a backgrounded grandchild holds the pipe open forever.
# start_new_session makes the shell's pid the group id, which outlives the shell itself.
def _killed(process: subprocess.Popen[str]) -> CapturedOutput:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    return CapturedOutput(process.communicate()[0])


# A command that believes a terminal is watching writes escape sequences and cursor
# moves into the document. The pipe alone is not enough of a hint: moon exports
# STARBASE_FORCE_TTY to every task, so a nested `moon` overrides its own detection.
def _terminal_free_env() -> dict[str, str]:
    inherited = {
        name: value
        for name, value in os.environ.items()
        if name not in ("STARBASE_FORCE_TTY", "FORCE_COLOR", "CLICOLOR_FORCE")
    }
    # Width is pinned too, else whoever renders decides how wide the committed
    # document is.
    return inherited | {"NO_COLOR": "1", "TERM": "dumb", "COLUMNS": "80"}


def _annotated_body(capture: _Capture) -> CapturedOutput:
    output = CapturedOutput(neutralized(Emitted(_trimmed(capture.output))))
    if capture.failure is None:
        return output
    return CapturedOutput(f"{output}\n{marker(capture.failure)}".lstrip("\n"))


# A zero-width space strips `[[` and `#` of their power to create links or tags, while
# leaving them looking exactly as whatever produced them wrote them.
def neutralized(text: Emitted) -> Emitted:
    unlinked = re.sub(
        r"\[\[|\]\]", lambda pair: f"{pair.group()[0]}\u200b{pair.group()[1]}", text
    )
    return Emitted(re.sub(r"(?<!\w)#(?=[\w/])", "#\u200b", unlinked))


# A code span cannot hold a line break, so multi-line output leaves the sentence and
# becomes an ordinary fence on its own line instead.
def _inline_or_promoted(capture: _Capture) -> OutputSpan:
    if "\n" in capture.output.strip():
        return OutputSpan(f"\n{_fenced(_annotated_body(capture))}")
    return _spanned(_annotated_inline(capture))


def _annotated_inline(capture: _Capture) -> CapturedOutput:
    output = CapturedOutput(neutralized(Emitted(capture.output.strip())))
    if capture.failure is not None:
        return CapturedOutput(f"{output} {marker(capture.failure)}".lstrip())
    if not output:
        return CapturedOutput(marker(Annotation("no output")))
    return output


def _spanned(output: CapturedOutput) -> OutputSpan:
    delimiter = "`" * (_longest_backtick_run(output) + 1)
    # Unpadded, a body touching a backtick merges into the delimiter and loses one.
    padding = " " if output.startswith("`") or output.endswith("`") else ""
    return OutputSpan(f"{delimiter}{padding}{output}{padding}{delimiter}")


def _fenced(output: CapturedOutput) -> OutputBlock:
    delimiter = "`" * max(3, _longest_backtick_run(output) + 1)
    body = f"{_trimmed(output)}\n" if output.strip() else ""
    return OutputBlock(f"{delimiter}\n{body}{delimiter}\n")


def _trimmed(output: CapturedOutput) -> CapturedOutput:
    return CapturedOutput(output.rstrip("\n"))


def _longest_backtick_run(output: CapturedOutput) -> int:
    return max((len(run) for run in re.findall(r"`+", output)), default=0)
