import contextlib
import os
import re
import signal
import subprocess
from typing import NewType

from documator.domain import ExitCode, TimeoutSeconds

Command = NewType("Command", str)
CapturedOutput = NewType("CapturedOutput", str)
OutputBlock = NewType("OutputBlock", str)
Annotation = NewType("Annotation", str)


def execute_block(command: Command, timeout: TimeoutSeconds) -> OutputBlock:
    return _fenced(_capture(command, timeout))


def _capture(command: Command, timeout: TimeoutSeconds) -> CapturedOutput:
    # One pipe for both streams, so writes stay in the order the command made them.
    with subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    ) as process:
        try:
            output = CapturedOutput(process.communicate(timeout=timeout)[0])
        except subprocess.TimeoutExpired:
            return _annotated(
                _killed(process), Annotation(f"timed out after {timeout}s")
            )
    status = ExitCode(process.returncode)
    if status == 0:
        return output
    return _annotated(output, Annotation(f"exit {status}"))


# Kill the whole session, else a backgrounded grandchild holds the pipe open forever.
# start_new_session makes the shell's pid the group id, which outlives the shell itself.
def _killed(process: subprocess.Popen[str]) -> CapturedOutput:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGKILL)
    return CapturedOutput(process.communicate()[0])


def _annotated(output: CapturedOutput, note: Annotation) -> CapturedOutput:
    return CapturedOutput(f"{_trimmed(output)}\n[documator: {note}]".lstrip("\n"))


def _fenced(output: CapturedOutput) -> OutputBlock:
    delimiter = "`" * max(3, _longest_backtick_run(output) + 1)
    body = f"{_trimmed(output)}\n" if output.strip() else ""
    return OutputBlock(f"{delimiter}\n{body}{delimiter}\n")


def _trimmed(output: CapturedOutput) -> CapturedOutput:
    return CapturedOutput(output.rstrip("\n"))


def _longest_backtick_run(output: CapturedOutput) -> int:
    return max((len(run) for run in re.findall(r"`+", output)), default=0)
