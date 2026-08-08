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


class ExistingDir(ExistingPath):
    @field_validator("root")
    @classmethod
    def _path_is_dir(cls, value: Path) -> Path:
        if not value.is_dir():
            raise PydanticCustomError(
                "path_not_dir", "path is not a directory: {path}", {"path": value}
            )
        return value


class ExistingFile(ExistingPath):
    @field_validator("root")
    @classmethod
    def _path_is_file(cls, value: Path) -> Path:
        if not value.is_file():
            raise PydanticCustomError(
                "path_not_file", "path is not a file: {path}", {"path": value}
            )
        return value


class InputDir(ExistingDir): ...


# Only the root must exist; the render creates the subfolders it mirrors.
class OutputDir(ExistingDir): ...


# A block reads paths the way its own document does, so it runs beside the source file.
class WorkingDir(ExistingDir): ...


class TimeoutSeconds(RootModel[float]):
    @field_validator("root")
    @classmethod
    def _is_positive(cls, value: float) -> float:
        if value <= 0:
            raise PydanticCustomError(
                "timeout_not_positive",
                "timeout must be positive: {seconds}",
                {"seconds": value},
            )
        return value


RelativePath = NewType("RelativePath", Path)

ExitCode = NewType("ExitCode", int)

FileContent = NewType("FileContent", bytes)

FileMode = NewType("FileMode", int)
