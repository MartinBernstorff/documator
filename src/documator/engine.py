import functools
import logging
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from documator.domain import (
    ExitCode,
    InputDir,
    OutputDir,
    RelativePath,
    TimeoutSeconds,
    WorkingDir,
)
from documator.execution import Annotation, Command, execute_block, marker
from documator.parsing import (
    Block,
    DeclarationBlock,
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
from documator.variables import (
    Interpolable,
    Scope,
    Undefined,
    VariableName,
    VariableValue,
)

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


@dataclass(frozen=True, slots=True)
class _Step:
    rendered: Rendered
    scope: Scope


def _render_block(
    block: Block, origin: Origin, timeout: TimeoutSeconds, scope: Scope
) -> _Step:
    match block:
        case PassthroughBlock(text):
            return _Step(Rendered(text, []), scope)
        case DeclarationBlock(text, name, value):
            return _declare(text, name, value, origin, scope)
        case ExecutableBlock(text, command):
            return _Step(_execute(text, command, origin, timeout, scope), scope)
        case TransclusionBlock(reference):
            return _Step(_render_transclusion(reference, origin, timeout), scope)
        case StructuralErrorBlock(text, reason):
            failure = _authoring_error(text, Annotation(reason.message), origin)
            return _Step(failure, scope)


def _declare(
    text: Markdown,
    name: VariableName,
    value: VariableValue,
    origin: Origin,
    scope: Scope,
) -> _Step:
    declared = scope.declare(name, value)
    if isinstance(declared, Scope):
        return _Step(Rendered(Markdown(""), []), declared)
    return _Step(_authoring_error(text, Annotation(str(declared)), origin), scope)


def _execute(
    text: Markdown,
    command: Command,
    origin: Origin,
    timeout: TimeoutSeconds,
    scope: Scope,
) -> Rendered:
    expanded = scope.expand(Interpolable(command))
    if isinstance(expanded, Undefined):
        return _authoring_error(text, Annotation(str(expanded)), origin)
    # The expanded command is the one that ran, so it is the one worth reproducing.
    resolved = Command(expanded)
    log.info("executing %s in %s", resolved, origin.note())
    executed = execute_block(resolved, origin.working_dir(), timeout)
    if executed.failure is None:
        return Rendered(Markdown(executed.block), [])
    log.error("%s in %s: %s", resolved, origin.note(), executed.failure)
    return Rendered(Markdown(executed.block), [Failure(executed.failure, ExitCode(1))])


def _authoring_error(text: Markdown, note: Annotation, origin: Origin) -> Rendered:
    log.error("%s in %s", note, origin.note())
    return Rendered(Markdown(f"{text}\n{marker(note)}\n"), [Failure(note, ExitCode(1))])


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


# Declarations make the walk stateful, so blocks fold rather than map: each one sees the
# scope its predecessors left behind, and a fresh scope starts at every note.
@dataclass(frozen=True, slots=True)
class _Progress:
    text: Markdown
    failures: tuple[Failure, ...]
    scope: Scope


def render_markdown(
    source: Markdown, origin: Origin, timeout: TimeoutSeconds
) -> Rendered:
    walked = functools.reduce(
        lambda progress, block: _advance(progress, block, origin, timeout),
        parse(source),
        _Progress(Markdown(""), (), Scope.empty()),
    )
    return Rendered(walked.text, list(walked.failures))


def _advance(
    progress: _Progress, block: Block, origin: Origin, timeout: TimeoutSeconds
) -> _Progress:
    step = _render_block(block, origin, timeout, progress.scope)
    return _Progress(
        Markdown(progress.text + step.rendered.text),
        (*progress.failures, *step.rendered.failures),
        step.scope,
    )
