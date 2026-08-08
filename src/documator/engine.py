import functools
import logging
import os
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from iterpy import Arr

from documator.domain import (
    ExitCode,
    FileContent,
    FileMode,
    InputDir,
    OutputDir,
    RelativePath,
    TimeoutSeconds,
    WorkingDir,
)
from documator.execution import (
    Annotation,
    Command,
    OutputBlock,
    OutputSpan,
    execute_block,
    execute_span,
    marker,
)
from documator.frontmatter import partition
from documator.inert import skill_name, stem
from documator.manifest import DestinationPath, Manifest, manifest_path, reserved
from documator.parsing import (
    Block,
    DeclarationBlock,
    ExecutableBlock,
    ExecutableSpan,
    LinkBlock,
    Markdown,
    PassthroughBlock,
    StructuralErrorBlock,
    TransclusionBlock,
    parse,
)
from documator.sections import section
from documator.transclusion import (
    AttachmentPath,
    LinkedAttachment,
    LinkedNote,
    NonNoteEmbed,
    NotePath,
    Reference,
    Target,
    TransclusionFailure,
    Vault,
    resolve,
    resolve_link,
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


# An input nested inside the output is fine: pruning reaches only what the manifest
# claims, so a run can render `templates/` into the repo root that holds it.
class ConflictReason(StrEnum):
    IDENTICAL = "input and output directories are the same"
    OUTPUT_NESTED_IN_INPUT = "output directory is nested inside the input directory"


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


# A tracked output the run no longer produces. Both modes work from this set: one
# deletes it, the other reports that it is still there.
def orphans(
    output_dir: OutputDir, tracked: Manifest, produced: set[DestinationPath]
) -> list[DestinationPath]:
    destination = output_dir.root
    owned = tracked.destinations()
    # Guarded, because the output may be a whole repository: the walk is the cost.
    if log.isEnabledFor(logging.DEBUG):
        for kept in (
            Arr(sorted(destination.rglob("*"), key=str))
            .filter(lambda path: path.is_file() and path != manifest_path(output_dir))
            .map(
                lambda path: DestinationPath(
                    RelativePath(path.relative_to(destination))
                )
            )
            .filter(lambda relative: relative not in owned)
        ):
            log.debug("kept %s: not written by documator", kept)
    return (
        Arr(sorted(owned - produced, key=str))
        .filter(lambda relative: (destination / relative).is_file())
        .to_list()
    )


def prune(
    output_dir: OutputDir, tracked: Manifest, produced: set[DestinationPath]
) -> None:
    destination = output_dir.root
    emptied = set[Path]()
    for relative in orphans(output_dir, tracked, produced):
        log.info("pruned %s", relative)
        (destination / relative).unlink()
        emptied.add((destination / relative).parent)
    # Only a directory this run emptied is removed; somebody else's empty folder stays.
    for directory in sorted(emptied, key=lambda path: len(path.parts), reverse=True):
        current = directory
        while current != destination and _is_empty_dir(current):
            current.rmdir()
            current = current.parent


def _is_empty_dir(path: Path) -> bool:
    return path.is_dir() and not any(path.iterdir())


# The target is the site the failure is filed under, which prints it; naming it here too
# would say the path twice on every line.
@dataclass(frozen=True, slots=True)
class Untracked:
    target: DestinationPath

    def __str__(self) -> str:
        return "refusing to overwrite: not written by documator"


@dataclass(frozen=True, slots=True)
class Obstructed:
    target: DestinationPath
    ancestor: DestinationPath

    def __str__(self) -> str:
        return f"refusing to write: {self.ancestor} is not a directory"


# A flat layout gives an attachment outside the linking skill's own bundle nowhere to
# land, so the link is refused rather than pointed at a path that will never exist.
@dataclass(frozen=True, slots=True)
class Unreachable:
    attachment: AttachmentPath

    def __str__(self) -> str:
        return f"link to {self.attachment}, which this run does not emit"


@dataclass(frozen=True, slots=True)
class Reserved:
    target: DestinationPath

    def __str__(self) -> str:
        return "refusing to write: documator keeps its manifest there"


type WriteRefusal = Untracked | Obstructed | Reserved


# Pruning no longer clears the way, so a foreign file at a target path — or one standing
# where a target's parent directory belongs — blocks that write instead of vanishing.
def refusal(
    output_dir: OutputDir, owned: set[DestinationPath], target: DestinationPath
) -> WriteRefusal | None:
    destination = output_dir.root
    if target == reserved():
        return Reserved(target)
    if (destination / target).exists() and target not in owned:
        return Untracked(target)
    for ancestor in reversed(target.parents):
        occupied = destination / ancestor
        if occupied.exists() and not occupied.is_dir():
            return Obstructed(target, DestinationPath(RelativePath(ancestor)))
    return None


# The one gate every write goes through: a refusal costs the file, never the run.
def blocked(
    output_dir: OutputDir, owned: set[DestinationPath], target: DestinationPath
) -> Failure | None:
    refused = refusal(output_dir, owned, target)
    if refused is None:
        return None
    failure = Failure(target, Annotation(str(refused)), ExitCode(2))
    log.error("%s", failure)
    return failure


# Check mode answers "would a real run change anything?", so it never touches the tree:
# every difference it finds is reported instead of applied.
class Mode(StrEnum):
    WRITE = "write"
    CHECK = "check"


@dataclass(frozen=True, slots=True)
class Stale:
    target: DestinationPath

    def __str__(self) -> str:
        return "out of date: re-run documator to write it"


@dataclass(frozen=True, slots=True)
class Orphaned:
    target: DestinationPath

    def __str__(self) -> str:
        return "no longer produced: re-run documator to prune it"


# What a real run would leave at a destination. A copy carries its source's mode across,
# so a mode change alone is a change; a rendered file is written without one.
@dataclass(frozen=True, slots=True)
class Landed:
    content: FileContent
    mode: FileMode | None

    @classmethod
    def copied(cls, source: Path) -> Landed:
        return cls(
            FileContent(source.read_bytes()),
            FileMode(stat.S_IMODE(source.stat().st_mode)),
        )

    @classmethod
    def rendered(cls, text: Markdown) -> Landed:
        return cls(FileContent(text.encode("utf-8")), None)

    def matches(self, site: Path) -> bool:
        if site.read_bytes() != self.content:
            return False
        return self.mode is None or stat.S_IMODE(site.stat().st_mode) == self.mode


# A difference is a content failure (1), not an impossible run (2): the tree is fine, it
# is just behind the templates.
def outdated(
    output_dir: OutputDir, target: DestinationPath, landed: Landed
) -> Failure | None:
    site = output_dir.root / target
    if site.is_file() and landed.matches(site):
        return None
    failure = Failure(target, Annotation(str(Stale(target))), ExitCode(1))
    log.error("%s", failure)
    return failure


def report_orphans(
    output_dir: OutputDir, tracked: Manifest, produced: set[DestinationPath]
) -> list[Failure]:
    return [_orphan(target) for target in orphans(output_dir, tracked, produced)]


def _orphan(target: DestinationPath) -> Failure:
    failure = Failure(target, Annotation(str(Orphaned(target))), ExitCode(1))
    log.error("%s", failure)
    return failure


# Where a failure arose: a note being rendered, or the path a write was refused at.
type Site = NotePath | DestinationPath


# An unresolvable transclusion stops the engine (2); a bad command only fails content.
@dataclass(frozen=True, slots=True)
class Failure:
    site: Site
    note: Annotation
    exit_code: ExitCode

    def __str__(self) -> str:
        return f"{self.site}: {self.note}"


@dataclass(frozen=True, slots=True)
class Rendered:
    text: Markdown
    failures: list[Failure]


# Held per artifact rather than per note, because a link has to work from where the text
# came to rest, not from where it was written.
@dataclass(frozen=True, slots=True)
class Placement:
    document: DestinationPath
    attachments: Mapping[AttachmentPath, DestinationPath]

    def reach(self, attachment: AttachmentPath) -> RelativePath | None:
        landed = self.attachments.get(attachment)
        if landed is None:
            return None
        return RelativePath(
            Path(os.path.relpath(landed, start=Path(self.document).parent))
        )


# The chain is the transclusion path that led here, so a cycle is visible from inside.
@dataclass(frozen=True, slots=True)
class Origin:
    vault: Vault
    chain: tuple[Target, ...]
    placement: Placement

    def note(self) -> NotePath:
        return self.chain[-1].note

    def working_dir(self) -> WorkingDir:
        return self.vault.beside(self.note())

    def entered(self, target: Target) -> Origin:
        return Origin(self.vault, (*self.chain, target), self.placement)


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
        case ExecutableSpan(text, command):
            return _Step(_execute_span(text, command, origin, timeout, scope), scope)
        case TransclusionBlock(reference):
            return _Step(_render_transclusion(reference, origin, timeout), scope)
        case LinkBlock(text, reference):
            return _Step(_render_link(text, reference, origin), scope)
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
    resolved = _expanded(command, scope)
    if isinstance(resolved, Undefined):
        return _authoring_error(text, Annotation(str(resolved)), origin)
    log.info("executing %s in %s", resolved, origin.note())
    executed = execute_block(resolved, origin.working_dir(), timeout)
    return _reported(executed.block, executed.failure, resolved, origin)


def _execute_span(
    text: Markdown,
    command: Command,
    origin: Origin,
    timeout: TimeoutSeconds,
    scope: Scope,
) -> Rendered:
    resolved = _expanded(command, scope)
    if isinstance(resolved, Undefined):
        return _inline_authoring_error(text, Annotation(str(resolved)), origin)
    log.info("executing %s in %s", resolved, origin.note())
    executed = execute_span(resolved, origin.working_dir(), timeout)
    return _reported(executed.span, executed.failure, resolved, origin)


def _expanded(command: Command, scope: Scope) -> Command | Undefined:
    expanded = scope.expand(Interpolable(command))
    if isinstance(expanded, Undefined):
        return expanded
    # The expanded command is the one that ran, so it is the one worth reproducing.
    return Command(expanded)


def _authoring_error(text: Markdown, note: Annotation, origin: Origin) -> Rendered:
    failure = _failure_at(note, origin, ExitCode(1))
    return Rendered(Markdown(f"{text}\n{marker(note)}\n"), [failure])


# The echoed source is already a span, so the marker follows it rather than breaking the
# sentence the command sat in.
def _inline_authoring_error(
    text: Markdown, note: Annotation, origin: Origin
) -> Rendered:
    failure = _failure_at(note, origin, ExitCode(1))
    return Rendered(Markdown(f"{text} {marker(note)}"), [failure])


# The failure is built before it is logged, so the line a reader sees inline is the same
# string the end-of-run summary replays.
def _failure_at(note: Annotation, origin: Origin, exit_code: ExitCode) -> Failure:
    failure = Failure(origin.note(), note, exit_code)
    log.error("%s", failure)
    return failure


def _reported(
    text: OutputBlock | OutputSpan,
    failure: Annotation | None,
    command: Command,
    origin: Origin,
) -> Rendered:
    if failure is None:
        return Rendered(Markdown(text), [])
    # The command is kept in the note, because "exit 1" alone names nothing to go fix.
    at_fault = _failure_at(Annotation(f"{command}: {failure}"), origin, ExitCode(1))
    return Rendered(Markdown(text), [at_fault])


# A broken link leaves one wrong word in otherwise complete prose, so it is a content
# failure (1) rather than the structural hole an unresolvable transclusion leaves (2).
def _render_link(text: Markdown, reference: Reference, origin: Origin) -> Rendered:
    resolved = resolve_link(origin.vault, reference)
    if isinstance(resolved, LinkedNote):
        return Rendered(Markdown(_emitted(resolved)), [])
    if isinstance(resolved, LinkedAttachment):
        return _render_attachment(text, resolved, origin)
    return _inline_authoring_error(text, Annotation(str(resolved)), origin)


def _render_attachment(
    text: Markdown, linked: LinkedAttachment, origin: Origin
) -> Rendered:
    reached = origin.placement.reach(linked.attachment)
    if reached is None:
        note = Annotation(str(Unreachable(linked.attachment)))
        return _inline_authoring_error(text, note, origin)
    label = linked.wording.alias or stem(RelativePath(linked.attachment.root))
    return Rendered(Markdown(f"[{label}]({reached.as_posix()}{_fragment(linked)})"), [])


# A skill reference is a call the model may choose to make, so an alias has nothing to
# relabel; a term is prose, so the alias is the sentence's own wording.
def _emitted(linked: LinkedNote) -> str:
    path = RelativePath(linked.note.root)
    invoked = skill_name(path)
    if invoked is not None:
        return f"/{invoked}{_fragment(linked)}"
    return f"{linked.wording.alias or stem(path)}{_fragment(linked)}"


def _fragment(linked: LinkedNote | LinkedAttachment) -> str:
    return f"#{linked.wording.fragment}" if linked.wording.fragment else ""


def _render_transclusion(
    reference: Reference, origin: Origin, timeout: TimeoutSeconds
) -> Rendered:
    resolution = resolve(origin.vault, reference, origin.chain)
    if isinstance(resolution, NonNoteEmbed):
        return Rendered(Markdown(str(resolution)), [])
    if isinstance(resolution, Target):
        return _render_target(resolution, origin, timeout)
    return _operational(resolution, origin)


def _render_target(target: Target, origin: Origin, timeout: TimeoutSeconds) -> Rendered:
    log.info("transcluding %s into %s", target, origin.note())
    source = Markdown(origin.vault.read(target.note))
    # The note's own frontmatter describes the note, not the text it lends out, so only
    # its body crosses the boundary.
    lent = partition(source).body if not target.path else section(source, target)
    # Tested on the markdown rather than on each failure type, so a section failure
    # added later cannot slip through and be rendered as if it were a body.
    if not isinstance(lent, str):
        return _operational(lent, origin)
    return render_markdown(lent, origin.entered(target), timeout)


def _operational(failure: TransclusionFailure, origin: Origin) -> Rendered:
    note = Annotation(str(failure))
    return Rendered(Markdown(marker(note)), [_failure_at(note, origin, ExitCode(2))])


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
