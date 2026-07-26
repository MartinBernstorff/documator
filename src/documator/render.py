import logging
import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NewType

from iterpy import Arr

from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds
from documator.execution import Annotation, execute_block
from documator.parsing import (
    Block,
    ExecutableBlock,
    Markdown,
    PassthroughBlock,
    StructuralErrorBlock,
    parse,
)

RelativePath = NewType("RelativePath", Path)

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


@dataclass(frozen=True, slots=True)
class _RenderedBlock:
    text: Markdown
    failure: Annotation | None


@dataclass(frozen=True, slots=True)
class _RenderedMarkdown:
    text: Markdown
    failures: list[Annotation]


def _render_block(
    block: Block, relative: RelativePath, timeout: TimeoutSeconds
) -> _RenderedBlock:
    match block:
        case PassthroughBlock(text):
            return _RenderedBlock(text, None)
        case ExecutableBlock(command):
            log.info("executing %s in %s", command, relative)
            executed = execute_block(command, timeout)
            if executed.failure is not None:
                log.error("%s in %s: %s", command, relative, executed.failure)
            return _RenderedBlock(Markdown(executed.block), executed.failure)
        case StructuralErrorBlock(text, reason):
            failure = Annotation(reason.message)
            log.error("%s in %s", failure, relative)
            marked = Markdown(f"{text}\n[documator: {failure}]\n")
            return _RenderedBlock(marked, failure)


def _render_markdown(
    source: Markdown, relative: RelativePath, timeout: TimeoutSeconds
) -> _RenderedMarkdown:
    blocks = Arr(parse(source)).map(
        lambda block: _render_block(block, relative, timeout)
    )
    return _RenderedMarkdown(
        Markdown("".join(blocks.map(lambda block: block.text))),
        [block.failure for block in blocks if block.failure is not None],
    )


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

    failures: list[Annotation] = []
    for relative in relative_paths:
        source = input_dir.root / relative
        target = output_dir.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix == ".md":
            rendered = _render_markdown(Markdown(source.read_text()), relative, timeout)
            target.write_text(rendered.text)
            failures.extend(rendered.failures)
        else:
            shutil.copy2(source, target)
        log.info("rendered %s", relative)

    return ExitCode(1 if failures else 0)
