import logging
import shutil
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
    Cycle,
    NonNoteEmbed,
    NotePath,
    Reference,
    TransclusionFailure,
    Vault,
    index,
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


# The exit code travels with the note, because an unresolvable transclusion stops the
# engine (2) while a command the author wrote badly only fails the content (1).
@dataclass(frozen=True, slots=True)
class _Failure:
    note: Annotation
    exit_code: ExitCode


@dataclass(frozen=True, slots=True)
class _Rendered:
    text: Markdown
    failures: list[_Failure]


# The chain is the transclusion path that led here, so a cycle is visible from inside.
@dataclass(frozen=True, slots=True)
class _Origin:
    vault: Vault
    chain: tuple[NotePath, ...]

    def note(self) -> NotePath:
        return self.chain[-1]

    def working_dir(self) -> WorkingDir:
        return WorkingDir((self.vault.root / self.note()).parent)

    def entered(self, note: NotePath) -> _Origin:
        return _Origin(self.vault, (*self.chain, note))


def _render_block(block: Block, origin: _Origin, timeout: TimeoutSeconds) -> _Rendered:
    match block:
        case PassthroughBlock(text):
            return _Rendered(text, [])
        case ExecutableBlock(command):
            log.info("executing %s in %s", command, origin.note())
            executed = execute_block(command, origin.working_dir(), timeout)
            if executed.failure is None:
                return _Rendered(Markdown(executed.block), [])
            log.error("%s in %s: %s", command, origin.note(), executed.failure)
            return _Rendered(
                Markdown(executed.block), [_Failure(executed.failure, ExitCode(1))]
            )
        case TransclusionBlock(reference):
            return _render_transclusion(reference, origin, timeout)
        case StructuralErrorBlock(text, reason):
            failure = Annotation(reason.message)
            log.error("%s in %s", failure, origin.note())
            return _Rendered(
                Markdown(f"{text}\n{marker(failure)}\n"),
                [_Failure(failure, ExitCode(1))],
            )


def _render_transclusion(
    reference: Reference, origin: _Origin, timeout: TimeoutSeconds
) -> _Rendered:
    resolution = resolve(origin.vault, reference)
    match resolution:
        case NonNoteEmbed(embedded):
            return _Rendered(Markdown(f"![[{embedded}]]"), [])
        case Path() as note if note not in origin.chain:
            log.info("transcluding %s into %s", note, origin.note())
            return _render_markdown(
                Markdown((origin.vault.root / note).read_text(encoding="utf-8")),
                origin.entered(note),
                timeout,
            )
        case Path() as note:
            return _operational(Cycle((*origin.chain, note)), origin)
        case failure:
            return _operational(failure, origin)


def _operational(failure: TransclusionFailure, origin: _Origin) -> _Rendered:
    note = Annotation(str(failure))
    log.error("%s in %s", note, origin.note())
    return _Rendered(Markdown(marker(note)), [_Failure(note, ExitCode(2))])


def _render_markdown(
    source: Markdown, origin: _Origin, timeout: TimeoutSeconds
) -> _Rendered:
    blocks = Arr(parse(source)).map(lambda block: _render_block(block, origin, timeout))
    return _Rendered(
        Markdown("".join(blocks.map(lambda block: block.text))),
        blocks.map(lambda block: Arr(block.failures)).flatten().to_list(),
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

    # Indexed once per run, so every transclusion in the run sees the same vault.
    vault = index(input_dir)

    failures: list[_Failure] = []
    for relative in relative_paths:
        source = input_dir.root / relative
        target = output_dir.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".md":
            rendered = _render_markdown(
                Markdown(source.read_text(encoding="utf-8")),
                _Origin(vault, (NotePath(Path(relative)),)),
                timeout,
            )
            target.write_text(rendered.text, encoding="utf-8")
            failures.extend(rendered.failures)
        else:
            shutil.copy2(source, target)
        log.info("rendered %s", relative)

    return ExitCode(max((failure.exit_code for failure in failures), default=0))
