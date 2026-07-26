import logging
import shutil
from pathlib import Path
from typing import NewType

from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds

RelativePath = NewType("RelativePath", Path)

log = logging.getLogger("documator")


def _directory_conflict(input_dir: InputDir, output_dir: OutputDir) -> str | None:
    source = input_dir.root.resolve()
    destination = output_dir.root.resolve()
    if source == destination:
        return f"input and output directories are the same: {source}"
    if destination.is_relative_to(source):
        return f"output directory {destination} is nested inside input {source}"
    if source.is_relative_to(destination):
        return f"input directory {source} is nested inside output {destination}"
    return None


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
        log.error(conflict)
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
