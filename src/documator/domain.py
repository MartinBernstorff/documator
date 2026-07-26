from pathlib import Path
from typing import NewType

from pydantic import RootModel, field_validator
from pydantic_core import PydanticCustomError


class ExistingPath(RootModel[Path]):
    @field_validator("root")
    @classmethod
    def _path_exists(cls, value: Path) -> Path:
        if not value.exists():
            raise PydanticCustomError(
                "path_missing", "path does not exist: {path}", {"path": value}
            )
        return value


class InputDir(ExistingPath):
    @field_validator("root")
    @classmethod
    def _path_is_dir(cls, value: Path) -> Path:
        if not value.is_dir():
            raise PydanticCustomError(
                "path_not_dir", "path is not a directory: {path}", {"path": value}
            )
        return value


# The render creates the output tree, so it need not exist beforehand.
class OutputDir(RootModel[Path]): ...


TimeoutSeconds = NewType("TimeoutSeconds", float)
ExitCode = NewType("ExitCode", int)

OPERATIONAL_ERROR = ExitCode(2)
