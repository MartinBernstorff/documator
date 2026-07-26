from typing import NewType

from documator.domain import TimeoutSeconds

Command = NewType("Command", str)
OutputBlock = NewType("OutputBlock", str)


def execute_block(command: Command, timeout: TimeoutSeconds) -> OutputBlock:
    raise NotImplementedError
