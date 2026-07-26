import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import NewType

from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds

DEFAULT_TIMEOUT = TimeoutSeconds(10.0)

EXIT_CLEAN = ExitCode(0)
EXIT_OPERATIONAL_ERROR = ExitCode(2)

MANIFEST_NAME = ".documator-manifest"

ErrorMessage = NewType("ErrorMessage", str)
RelativePath = NewType("RelativePath", Path)

log = logging.getLogger("documator")


@dataclass(frozen=True)
class OperationalError:
    message: ErrorMessage


@dataclass(frozen=True)
class RenderDirs:
    input_dir: InputDir
    output_dir: OutputDir


def resolve_dirs(
    input_dir: InputDir, output_dir: OutputDir
) -> RenderDirs | OperationalError:
    resolved_input = Path(input_dir).resolve()
    resolved_output = Path(output_dir).resolve()

    if not resolved_input.is_dir():
        return OperationalError(
            ErrorMessage(f"input directory does not exist: {resolved_input}")
        )
    if resolved_output.exists() and not resolved_output.is_dir():
        return OperationalError(
            ErrorMessage(f"output path is not a directory: {resolved_output}")
        )
    if resolved_input == resolved_output:
        return OperationalError(
            ErrorMessage(f"input and output directory are the same: {resolved_input}")
        )
    for outer, inner in (
        (resolved_input, resolved_output),
        (resolved_output, resolved_input),
    ):
        if inner.is_relative_to(outer):
            return OperationalError(
                ErrorMessage(
                    f"{inner} is nested inside {outer}; input and output directories"
                    " must be disjoint"
                )
            )
    return RenderDirs(InputDir(resolved_input), OutputDir(resolved_output))


def render(
    input_dir: InputDir, output_dir: OutputDir, timeout: TimeoutSeconds
) -> ExitCode:
    dirs = resolve_dirs(input_dir, output_dir)
    if isinstance(dirs, OperationalError):
        log.error(dirs.message)
        return EXIT_OPERATIONAL_ERROR

    previous = _read_manifest(dirs.output_dir)
    produced = _mirror(dirs.input_dir, dirs.output_dir)
    _prune(dirs.output_dir, previous - produced)
    _write_manifest(dirs.output_dir, produced)
    return EXIT_CLEAN


def _mirror(input_dir: InputDir, output_dir: OutputDir) -> set[RelativePath]:
    root = Path(input_dir)
    destination_root = Path(output_dir)
    destination_root.mkdir(parents=True, exist_ok=True)

    produced: set[RelativePath] = set()
    for source in sorted(p for p in root.rglob("*") if p.is_file()):
        relative = RelativePath(source.relative_to(root))
        log.info(f"rendering {relative.as_posix()}")
        destination = destination_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        produced.add(relative)
    return produced


def _prune(output_dir: OutputDir, stale: set[RelativePath]) -> None:
    root = Path(output_dir)
    for relative in sorted(stale):
        target = root / relative
        if target.is_file() or target.is_symlink():
            log.info(f"pruning {relative.as_posix()}")
            target.unlink()
        _prune_empty_ancestors(root, target.parent)


def _prune_empty_ancestors(root: Path, directory: Path) -> None:
    while directory != root and directory.is_relative_to(root) and directory.is_dir():
        if any(directory.iterdir()):
            return
        directory.rmdir()
        directory = directory.parent


def _read_manifest(output_dir: OutputDir) -> set[RelativePath]:
    manifest = Path(output_dir) / MANIFEST_NAME
    if not manifest.is_file():
        return set()
    return {
        RelativePath(Path(line))
        for line in manifest.read_text().splitlines()
        if line.strip()
    }


def _write_manifest(output_dir: OutputDir, produced: set[RelativePath]) -> None:
    lines = sorted(relative.as_posix() for relative in produced)
    (Path(output_dir) / MANIFEST_NAME).write_text("".join(f"{p}\n" for p in lines))
