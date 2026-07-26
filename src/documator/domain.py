from pathlib import Path
from typing import NewType

from pydantic import RootModel, field_validator


class ExistingPath(RootModel[Path]):
    @field_validator("root")
    @classmethod
    def _path_exists(cls, value: Path) -> Path:
        if not value.exists():
            raise ValueError(f"path does not exist: {value}")
        return value


class InputDir(ExistingPath): ...


# The render creates the output tree, so it need not exist beforehand.
class OutputDir(RootModel[Path]): ...


TimeoutSeconds = NewType("TimeoutSeconds", float)
ExitCode = NewType("ExitCode", int)

OPERATIONAL_ERROR = ExitCode(2)
