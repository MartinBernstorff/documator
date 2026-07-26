import re
import subprocess
from typing import NewType

from documator.domain import TimeoutSeconds

Command = NewType("Command", str)
CapturedOutput = NewType("CapturedOutput", str)
OutputBlock = NewType("OutputBlock", str)


def execute_block(command: Command, timeout: TimeoutSeconds) -> OutputBlock:
    return _fenced(_capture(command, timeout))


def _capture(command: Command, timeout: TimeoutSeconds) -> CapturedOutput:
    try:
        completed = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as expired:
        return _marked(_decoded(expired.stdout), f"timed out after {timeout}s")
    merged = CapturedOutput(completed.stdout + completed.stderr)
    if completed.returncode == 0:
        return merged
    return _marked(merged, f"exit {completed.returncode}")


def _decoded(partial: str | bytes | None) -> CapturedOutput:
    if isinstance(partial, bytes):
        return CapturedOutput(partial.decode(errors="replace"))
    return CapturedOutput(partial or "")


def _marked(output: CapturedOutput, note: str) -> CapturedOutput:
    return CapturedOutput(f"{output.rstrip('\n')}\n[documator: {note}]".lstrip("\n"))


def _fenced(output: CapturedOutput) -> OutputBlock:
    delimiter = "`" * max(3, _longest_backtick_run(output) + 1)
    body = f"{output.rstrip('\n')}\n" if output.strip() else ""
    return OutputBlock(f"{delimiter}\n{body}{delimiter}\n")


def _longest_backtick_run(output: CapturedOutput) -> int:
    return max((len(run) for run in re.findall(r"`+", output)), default=0)
