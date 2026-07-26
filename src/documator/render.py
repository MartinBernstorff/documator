import logging
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NewType

from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds

RelativePath = NewType("RelativePath", Path)

DEFAULT_TIMEOUT = TimeoutSeconds(10.0)

log = logging.getLogger("documator")


class ConflictReason(StrEnum):
    IDENTICAL = "input and output directories are the same"
    OUTPUT_NESTED_IN_INPUT = "output directory is nested inside the input directory"
    INPUT_NESTED_IN_OUTPUT = "input directory is nested inside the output directory"


@dataclass(frozen=True)
class DirectoryConflict:
    reason: ConflictReason
    input_dir: Path
    output_dir: Path


def _directory_conflict(
    input_dir: InputDir, output_dir: OutputDir
) -> DirectoryConflict | None:
    source = input_dir.root.resolve()
    destination = output_dir.root.resolve()
    reason = None
    if source == destination:
        reason = ConflictReason.IDENTICAL
    elif destination.is_relative_to(source):
        reason = ConflictReason.OUTPUT_NESTED_IN_INPUT
    elif source.is_relative_to(destination):
        reason = ConflictReason.INPUT_NESTED_IN_OUTPUT
    if reason is None:
        return None
    return DirectoryConflict(reason, source, destination)


def _relative_files(input_dir: InputDir) -> list[RelativePath]:
    source = input_dir.root
    return sorted(
        (RelativePath(p.relative_to(source)) for p in source.rglob("*") if p.is_file()),
        key=str,
    )


def _prune(output_dir: OutputDir, produced: set[RelativePath]) -> None:
    destination = output_dir.root
    # Children sort after parents, so reverse order empties a directory first.
    for path in sorted(destination.rglob("*"), key=str, reverse=True):
        relative = RelativePath(path.relative_to(destination))
        if path.is_file() and relative not in produced:
            log.info("pruned %s", relative)
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def render(
    input_dir: InputDir, output_dir: OutputDir, timeout: TimeoutSeconds
) -> ExitCode:
    conflict = _directory_conflict(input_dir, output_dir)
    if conflict is not None:
        log.error(
            "%s: input=%s output=%s",
            conflict.reason,
            conflict.input_dir,
            conflict.output_dir,
        )
        return ExitCode(2)

    relative_paths = _relative_files(input_dir)

    # Prune first, so a stale path cannot block a file whose kind changed.
    _prune(output_dir, set(relative_paths))

    for relative in relative_paths:
        target = output_dir.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(input_dir.root / relative, target)
        log.info("rendered %s", relative)

    return ExitCode(0)
