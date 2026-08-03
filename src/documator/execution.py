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


def execute_block(
    command: Command, working_dir: WorkingDir, timeout: TimeoutSeconds
) -> ExecutedBlock:
    capture = _capture(command, working_dir, timeout)
    return ExecutedBlock(_fenced(_annotated_body(capture)), capture.failure)


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


def _fenced(output: CapturedOutput) -> OutputBlock:
    delimiter = "`" * max(3, _longest_backtick_run(output) + 1)
    body = f"{_trimmed(output)}\n" if output.strip() else ""
    return OutputBlock(f"{delimiter}\n{body}{delimiter}\n")


def _trimmed(output: CapturedOutput) -> CapturedOutput:
    return CapturedOutput(output.rstrip("\n"))


def _longest_backtick_run(output: CapturedOutput) -> int:
    return max((len(run) for run in re.findall(r"`+", output)), default=0)
