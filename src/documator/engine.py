import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import NewType

from iterpy import Arr

from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds, WorkingDir
from documator.execution import Annotation, execute_block, marker
from documator.parsing import (
    Block,
    ExecutableBlock,
    Markdown,
    PassthroughBlock,
    StructuralErrorBlock,
    TransclusionBlock,
    parse,
)
from documator.transclusion import (
    NonNoteEmbed,
    NotePath,
    Reference,
    TransclusionFailure,
    Vault,
    resolve,
)

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


def directory_conflict(
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


def report_conflict(conflict: DirectoryConflict) -> ExitCode:
    log.error(
        "%s: input=%s output=%s",
        conflict.reason,
        conflict.input_dir,
        conflict.output_dir,
    )
    return ExitCode(2)


def relative_files(input_dir: InputDir) -> list[RelativePath]:
    source = input_dir.root
    return sorted(
        (RelativePath(p.relative_to(source)) for p in source.rglob("*") if p.is_file()),
        key=str,
    )


def prune(output_dir: OutputDir, produced: set[RelativePath]) -> None:
    destination = output_dir.root
    # Children sort after parents, so reverse order empties a directory first.
    for path in sorted(destination.rglob("*"), key=str, reverse=True):
        relative = RelativePath(path.relative_to(destination))
        if path.is_file() and relative not in produced:
            log.info("pruned %s", relative)
            path.unlink()
        elif path.is_dir() and not any(path.iterdir()):
            path.rmdir()


# An unresolvable transclusion stops the engine (2); a bad command only fails content.
@dataclass(frozen=True, slots=True)
class Failure:
    note: Annotation
    exit_code: ExitCode


@dataclass(frozen=True, slots=True)
class Rendered:
    text: Markdown
    failures: list[Failure]


# The chain is the transclusion path that led here, so a cycle is visible from inside.
@dataclass(frozen=True, slots=True)
class Origin:
    vault: Vault
    chain: tuple[NotePath, ...]

    def note(self) -> NotePath:
        return self.chain[-1]

    def working_dir(self) -> WorkingDir:
        return self.vault.beside(self.note())

    def entered(self, note: NotePath) -> Origin:
        return Origin(self.vault, (*self.chain, note))


def worst(failures: list[Failure]) -> ExitCode:
    return ExitCode(max((failure.exit_code for failure in failures), default=0))


def _render_block(block: Block, origin: Origin, timeout: TimeoutSeconds) -> Rendered:
    match block:
        case PassthroughBlock(text):
            return Rendered(text, [])
        case ExecutableBlock(command):
            log.info("executing %s in %s", command, origin.note())
            executed = execute_block(command, origin.working_dir(), timeout)
            if executed.failure is None:
                return Rendered(Markdown(executed.block), [])
            log.error("%s in %s: %s", command, origin.note(), executed.failure)
            return Rendered(
                Markdown(executed.block), [Failure(executed.failure, ExitCode(1))]
            )
        case TransclusionBlock(reference):
            return _render_transclusion(reference, origin, timeout)
        case StructuralErrorBlock(text, reason):
            failure = Annotation(reason.message)
            log.error("%s in %s", failure, origin.note())
            return Rendered(
                Markdown(f"{text}\n{marker(failure)}\n"),
                [Failure(failure, ExitCode(1))],
            )


def _render_transclusion(
    reference: Reference, origin: Origin, timeout: TimeoutSeconds
) -> Rendered:
    resolution = resolve(origin.vault, reference, origin.chain)
    if isinstance(resolution, NonNoteEmbed):
        return Rendered(Markdown(str(resolution)), [])
    if isinstance(resolution, NotePath):
        log.info("transcluding %s into %s", resolution, origin.note())
        return render_markdown(
            Markdown(origin.vault.read(resolution)),
            origin.entered(resolution),
            timeout,
        )
    return _operational(resolution, origin)


def _operational(failure: TransclusionFailure, origin: Origin) -> Rendered:
    note = Annotation(str(failure))
    log.error("%s in %s", note, origin.note())
    return Rendered(Markdown(marker(note)), [Failure(note, ExitCode(2))])


def render_markdown(
    source: Markdown, origin: Origin, timeout: TimeoutSeconds
) -> Rendered:
    blocks = Arr(parse(source)).map(lambda block: _render_block(block, origin, timeout))
    return Rendered(
        Markdown("".join(blocks.map(lambda block: block.text))),
        blocks.map(lambda block: Arr(block.failures)).flatten().to_list(),
    )
