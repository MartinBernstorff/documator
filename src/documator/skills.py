from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from iterpy import Arr
from pydantic import ValidationError

from documator.domain import (
    ExitCode,
    InputDir,
    OutputDir,
    RelativePath,
    TimeoutSeconds,
)
from documator.engine import (
    Claim,
    Failure,
    Origin,
    Placement,
    allocate,
    blocked,
    directory_conflict,
    log,
    prune,
    relative_files,
    render_markdown,
    report_conflict,
    worst,
)
from documator.frontmatter import SkillName, Template, compose, partition, split
from documator.inert import PathClass, classify, skill_name
from documator.manifest import (
    DestinationPath,
    Manifest,
    TemplatePath,
    clear_claims,
    read_claims,
    read_manifest,
    write_claims,
    write_manifest,
)
from documator.notice import annotated
from documator.parsing import Markdown
from documator.sections import emitted
from documator.structural import (
    Collision,
    Derived,
    Reason,
    StructuralFailure,
    Unreadable,
    invalid_name,
    misplaced,
    misplacement,
    report,
    unusable,
)
from documator.summary import Errored, Problem, Produced, summarise
from documator.transclusion import (
    AttachmentPath,
    NotePath,
    Target,
    Vault,
    index,
    without_invisible_notes,
)


@dataclass(frozen=True, slots=True)
class _Template:
    derived: Derived
    bundle: tuple[RelativePath, ...]


# Frontmatter is lifted from the source before anything runs, so no block and no
# transclusion can forge it.
@dataclass(frozen=True, slots=True)
class _Validated:
    template: _Template
    authored: Template


class _Verb(StrEnum):
    COMPILED = "compiled"
    BUNDLED = "bundled"


# Markdown content stays text until write time, where the notice is stamped into it.
@dataclass(frozen=True, slots=True)
class _Artifact:
    verb: _Verb
    source: TemplatePath
    target: DestinationPath
    content: Markdown | bytes
    failures: list[Failure]


# A marked folder holding SKILL.md is a hard leaf, so skills never nest. Everything
# unmarked is a term: it names something for links to point at and compiles to nothing.
def _templates(input_dir: InputDir, current: RelativePath) -> list[_Template]:
    entries = Arr(
        sorted((input_dir.root / current).iterdir(), key=lambda entry: entry.name)
    ).filter(
        lambda entry: classify(RelativePath(current / entry.name)) is PathClass.OPEN
    )
    files = entries.filter(lambda entry: entry.is_file())
    # Matched on the exact name, so a case-insensitive filesystem cannot report a
    # `skill.md` as the manifest and then bundle that same file over the output.
    manifest = (
        None if current == Path() else _derived(RelativePath(current / "SKILL.md"))
    )
    if manifest is not None and files.any(lambda entry: entry.name == "SKILL.md"):
        return [_folder_template(input_dir, manifest)]
    nested = (
        entries.filter(lambda entry: entry.is_dir())
        .map(
            lambda entry: Arr(_templates(input_dir, RelativePath(current / entry.name)))
        )
        .flatten()
    )
    bare = (
        files.filter(lambda entry: entry.suffix.lower() == ".md")
        .map(lambda entry: _derived(RelativePath(current / entry.name)))
        .map(_bare_template)
        .flatten()
    )
    return [*nested, *bare]


# The mark and the name it yields are decided together, so no caller has to re-prove
# that a path it already knows is marked really is.
def _derived(source: RelativePath) -> Derived | None:
    named = skill_name(source)
    return None if named is None else Derived(SkillName(named), source)


def _bare_template(derived: Derived | None) -> Arr[_Template]:
    return Arr([] if derived is None else [_Template(derived, ())])


def _folder_template(input_dir: InputDir, derived: Derived) -> _Template:
    source, folder = derived.source, RelativePath(derived.source.parent)
    bundle = (
        Arr(sorted((input_dir.root / folder).rglob("*"), key=str))
        .filter(lambda path: path.is_file())
        .map(lambda path: RelativePath(path.relative_to(input_dir.root)))
        .filter(lambda path: path != source and classify(path) is PathClass.OPEN)
        .filter(lambda path: misplacement(path) is None)
        .to_list()
    )
    return _Template(derived, tuple(bundle))


def _artifacts(
    validated: _Validated, vault: Vault, timeout: TimeoutSeconds
) -> list[_Artifact]:
    derived = validated.template.derived
    note = NotePath(derived.source)
    folder = RelativePath(derived.source.parent)
    # Only the skill's own bundle is reachable: a flat layout gives an attachment
    # anywhere else in the vault no place of its own to land.
    landed = {
        AttachmentPath(path): DestinationPath(
            RelativePath(Path(derived.name) / path.relative_to(folder))
        )
        for path in validated.template.bundle
        if path.suffix.lower() != ".md"
    }
    compiled_at = DestinationPath(RelativePath(Path(derived.name) / "SKILL.md"))
    origin = Origin(vault, (Target.whole(note),), Placement(compiled_at, landed))
    rendered = render_markdown(emitted(validated.authored.body), origin, timeout)
    compiled = _Artifact(
        _Verb.COMPILED,
        TemplatePath(derived.source),
        compiled_at,
        compose(derived.name, validated.authored.declared, rendered.text),
        rendered.failures,
    )
    return [
        compiled,
        *(
            _bundled(derived.name, path, folder, landed, vault, timeout)
            for path in validated.template.bundle
        ),
    ]


# Flattening applies only above the skill folder, so the bundle keeps its own structure.
def _bundled(
    name: SkillName,
    path: RelativePath,
    folder: RelativePath,
    landed: Mapping[AttachmentPath, DestinationPath],
    vault: Vault,
    timeout: TimeoutSeconds,
) -> _Artifact:
    target = DestinationPath(RelativePath(Path(name) / path.relative_to(folder)))
    source = TemplatePath(path)
    if path.suffix.lower() != ".md":
        return _Artifact(
            _Verb.BUNDLED, source, target, vault.read_bytes(AttachmentPath(path)), []
        )
    note = NotePath(path)
    # A bundled note is a document rather than a skill, so its frontmatter is prose the
    # reader keeps: split off only so the scratch rule sees a body, then handed back.
    authored = partition(Markdown(vault.read(note)))
    rendered = render_markdown(
        Markdown(authored.preamble + emitted(authored.body)),
        Origin(vault, (Target.whole(note),), Placement(target, landed)),
        timeout,
    )
    return _Artifact(_Verb.BUNDLED, source, target, rendered.text, rendered.failures)


# Names and collisions are decided from paths alone, so a broken skill never gets as far
# as executing one of its `!command` blocks.
def _named(
    templates: list[_Template],
) -> tuple[list[_Template], list[StructuralFailure]]:
    judged = [(template, invalid_name(template.derived)) for template in templates]
    return (
        [template for template, failure in judged if failure is None],
        [failure for _, failure in judged if failure is not None],
    )


# The namespace is global and spans both template forms, because scoped checking is
# incoherent under a flat output layout. Neither side of a clash is emitted, since an
# arbitrary winner would make the surviving skill depend on tiebreak luck.
def _unique(
    templates: list[_Template],
) -> tuple[list[_Template], list[StructuralFailure]]:
    claims = Arr(templates).groupby(lambda template: template.derived.name).to_list()
    return (
        [
            template
            for _, claimants in claims
            if len(claimants) == 1
            for template in claimants
        ],
        [
            Collision(
                SkillName(name),
                tuple(template.derived.source for template in claimants),
            )
            for name, claimants in claims
            if len(claimants) > 1
        ],
    )


def _read(template: _Template, vault: Vault) -> _Validated | StructuralFailure:
    derived = template.derived
    try:
        authored = split(Markdown(vault.read(NotePath(derived.source))))
    except (OSError, UnicodeDecodeError, ValidationError) as error:
        # Collapsed to one line, because each reason is one bullet in the report.
        return Unreadable(derived, Reason(" ".join(str(error).split())))
    rejected = unusable(derived, authored)
    return rejected if rejected is not None else _Validated(template, authored)


def _usable(
    templates: list[_Template], vault: Vault
) -> tuple[list[_Validated], list[StructuralFailure]]:
    read = [_read(template, vault) for template in templates]
    return (
        [outcome for outcome in read if isinstance(outcome, _Validated)],
        [outcome for outcome in read if not isinstance(outcome, _Validated)],
    )


def _unclaimed(input_dir: InputDir, templates: list[_Template]) -> list[RelativePath]:
    claimed = (
        Arr(templates)
        .map(lambda template: Arr([template.derived.source, *template.bundle]))
        .flatten()
        .to_list()
    )
    return (
        Arr(relative_files(input_dir))
        .filter(lambda path: path not in claimed)
        .to_list()
    )


def skills(
    input_dir: InputDir, output_dir: OutputDir, timeout: TimeoutSeconds
) -> ExitCode:
    conflict = directory_conflict(input_dir, output_dir)
    if conflict is not None:
        return report_conflict(conflict)

    # Indexed once per run, so every transclusion in the run sees the same vault.
    vault = without_invisible_notes(index(input_dir))

    templates = _templates(input_dir, RelativePath(Path()))
    # An unmarked note is a term, so producing no skill is what it is for: the warning
    # channel stays free for mistakes, and a link that wanted one is the error instead.
    for path in _unclaimed(input_dir, templates):
        log.info("ignored %s", path)

    named, misnamed = _named(templates)
    unique, colliding = _unique(named)
    validated, unusable_sources = _usable(unique, vault)
    # Logged as discovered; the report is what re-orders them.
    structural = [
        *misplaced(relative_files(input_dir)),
        *misnamed,
        *colliding,
        *unusable_sources,
    ]
    for failure in structural:
        log.error("%s", failure)

    # The whole tree resolves before anything is touched, so pruning is never partial.
    artifacts = (
        Arr(validated)
        .map(lambda skill: Arr(_artifacts(skill, vault, timeout)))
        .flatten()
        .to_list()
    )

    # The reasons are an artifact of their own, so a stale one dies with the run that
    # produced it and a skill that failed loses its previously-compiled copy.
    reasons = DestinationPath(RelativePath(Path("documator-errors.md")))
    produced = {artifact.target for artifact in artifacts}
    tracked = read_manifest(output_dir)
    # Pruning goes by the manifest alone: a claim a dead run left behind says documator
    # meant to write that path, which is no reason to delete what sits there now.
    prune(output_dir, tracked, produced | ({reasons} if structural else set()))
    owned = tracked.destinations() | read_claims(output_dir).destinations()

    content = (
        Arr(artifacts).map(lambda artifact: Arr(artifact.failures)).flatten().to_list()
    )
    # The report answers to the run, not to a template, so it is its own source.
    reported = Claim(TemplatePath(RelativePath(reasons)), reasons)
    intended = allocate(
        output_dir,
        owned,
        [
            *(Claim(artifact.source, artifact.target) for artifact in artifacts),
            *([reported] if structural else []),
        ],
    )
    content.extend(intended.refusals)
    write_claims(output_dir, intended.claimed)

    written: dict[TemplatePath, DestinationPath] = {}
    for artifact in artifacts:
        if not intended.covers(artifact.target):
            continue
        # Re-checked at the write, because an artifact this run already landed can stand
        # where a later one's parent directory belongs.
        refused = blocked(output_dir, owned | set(written.values()), artifact.target)
        if refused is not None:
            content.append(refused)
            continue
        target = output_dir.root / artifact.target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_bytes(artifact))
        written[artifact.source] = artifact.target
        log.info("%s %s into %s", artifact.verb, artifact.source, artifact.target)

    # Counted before the report lands, because the report is the run describing itself
    # rather than a skill it compiled.
    compiled = Produced(len(written))

    if structural and intended.covers(reasons):
        refused = blocked(output_dir, owned | set(written.values()), reasons)
        if refused is not None:
            content.append(refused)
        else:
            (output_dir.root / reasons).write_text(report(structural), encoding="utf-8")
            written[reported.source] = reported.target

    # Rewritten last and now only for what really landed, so a run that finishes leaves
    # a manifest that claims no file it refused to write.
    write_manifest(output_dir, Manifest(written))
    clear_claims(output_dir)

    problems: list[Problem] = [
        *(Errored(failure) for failure in structural),
        *(Errored(failure) for failure in content),
    ]
    summarise(compiled, problems)

    # A structural failure is a content failure; 2 stays reserved for an impossible run.
    return ExitCode(max(worst(content), 1 if structural else 0))


def _bytes(artifact: _Artifact) -> bytes:
    if isinstance(artifact.content, bytes):
        return artifact.content
    return annotated(artifact.content, artifact.source).encode("utf-8")
