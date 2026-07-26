import logging
import shutil
from pathlib import Path
from typing import NewType

from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds

DEFAULT_TIMEOUT = TimeoutSeconds(10.0)

EXIT_CLEAN = ExitCode(0)
EXIT_OPERATIONAL = ExitCode(2)

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


def _relative_files(root: Path) -> list[RelativePath]:
    return sorted(
        (RelativePath(p.relative_to(root)) for p in root.rglob("*") if p.is_file()),
        key=str,
    )


def _prune(root: Path, produced: set[RelativePath]) -> None:
    # Children sort after their parent, so reverse order empties a directory
    # before we reach the directory itself.
    for path in sorted(root.rglob("*"), key=str, reverse=True):
        if path.is_file() and RelativePath(path.relative_to(root)) not in produced:
            log.info("pruned %s", path.relative_to(root))
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()


def render(
    input_dir: InputDir, output_dir: OutputDir, timeout: TimeoutSeconds
) -> ExitCode:
    conflict = _directory_conflict(input_dir, output_dir)
    if conflict is not None:
        log.error(conflict)
        return EXIT_OPERATIONAL

    source = input_dir.root
    destination = output_dir.root

    produced: set[RelativePath] = set()
    for relative in _relative_files(source):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)
        produced.add(relative)
        log.info("rendered %s", relative)

    _prune(destination, produced)
    return EXIT_CLEAN
