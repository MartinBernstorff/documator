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
    Failure,
    Origin,
    blocked,
    directory_conflict,
    log,
    prune,
    relative_files,
    render_markdown,
    report_conflict,
    worst,
)
from documator.frontmatter import SkillName, Template, compose, split
from documator.inert import PathClass, classify
from documator.manifest import (
    DestinationPath,
    Manifest,
    TemplatePath,
    read_manifest,
    write_manifest,
)
from documator.notice import annotated
from documator.parsing import Markdown
from documator.structural import (
    Collision,
    Derived,
    Reason,
    StructuralFailure,
    Unreadable,
    invalid_name,
    report,
    unusable,
)
from documator.transclusion import (
    AttachmentPath,
    NotePath,
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


# A folder holding SKILL.md is a hard leaf, so skills never nest.
def _templates(input_dir: InputDir, current: RelativePath) -> list[_Template]:
    entries = Arr(
        sorted((input_dir.root / current).iterdir(), key=lambda entry: entry.name)
    ).filter(
        lambda entry: classify(RelativePath(current / entry.name)) is PathClass.OPEN
    )
    files = entries.filter(lambda entry: entry.is_file())
    # Matched on the exact name, so a case-insensitive filesystem cannot report a
    # `skill.md` as the manifest and then bundle that same file over the output.
    if current != Path() and files.any(lambda entry: entry.name == "SKILL.md"):
        return [_folder_template(input_dir, current)]
    nested = (
        entries.filter(lambda entry: entry.is_dir())
        .map(
            lambda entry: Arr(_templates(input_dir, RelativePath(current / entry.name)))
        )
        .flatten()
    )
    bare = files.filter(lambda entry: entry.suffix.lower() == ".md").map(
        lambda entry: _Template(
            Derived(SkillName(entry.stem), RelativePath(current / entry.name)), ()
        )
    )
    return [*nested, *bare]


def _folder_template(input_dir: InputDir, folder: RelativePath) -> _Template:
    source = folder / "SKILL.md"
    bundle = (
        Arr(sorted((input_dir.root / folder).rglob("*"), key=str))
        .filter(lambda path: path.is_file())
        .map(lambda path: RelativePath(path.relative_to(input_dir.root)))
        .filter(lambda path: path != source and classify(path) is PathClass.OPEN)
        .to_list()
    )
    return _Template(
        Derived(SkillName(folder.name), RelativePath(source)), tuple(bundle)
    )


def _artifacts(
    validated: _Validated, vault: Vault, timeout: TimeoutSeconds
) -> list[_Artifact]:
    derived = validated.template.derived
    note = NotePath(derived.source)
    rendered = render_markdown(validated.authored.body, Origin(vault, (note,)), timeout)
    compiled = _Artifact(
        _Verb.COMPILED,
        TemplatePath(derived.source),
        DestinationPath(RelativePath(Path(derived.name) / "SKILL.md")),
        compose(derived.name, validated.authored.declared, rendered.text),
        rendered.failures,
    )
    folder = RelativePath(derived.source.parent)
    return [
        compiled,
        *(
            _bundled(derived.name, path, folder, vault, timeout)
            for path in validated.template.bundle
        ),
    ]


# Flattening applies only above the skill folder, so the bundle keeps its own structure.
def _bundled(
    name: SkillName,
    path: RelativePath,
    folder: RelativePath,
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
    # A bundled note is a document, not a skill, so it renders without frontmatter.
    rendered = render_markdown(
        Markdown(vault.read(note)), Origin(vault, (note,)), timeout
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


# The flat layout gives a loose file no destination, so ignoring beats an error that
# would make exit 2 permanent; the level stays graded so a real mistake stands out.
def _report_ignored(path: RelativePath) -> None:
    if classify(path) is PathClass.OPEN:
        log.warning("ignored %s: move it into a SKILL.md folder to bundle it", path)
    else:
        log.info("ignored %s", path)


def skills(
    input_dir: InputDir, output_dir: OutputDir, timeout: TimeoutSeconds
) -> ExitCode:
    conflict = directory_conflict(input_dir, output_dir)
    if conflict is not None:
        return report_conflict(conflict)

    # Indexed once per run, so every transclusion in the run sees the same vault.
    vault = without_invisible_notes(index(input_dir))

    templates = _templates(input_dir, RelativePath(Path()))
    for ignored in _unclaimed(input_dir, templates):
        _report_ignored(ignored)

    named, misnamed = _named(templates)
    unique, colliding = _unique(named)
    validated, unusable_sources = _usable(unique, vault)
    # Logged as discovered; the report is what re-orders them.
    structural = [*misnamed, *colliding, *unusable_sources]
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
    prune(output_dir, tracked, produced | ({reasons} if structural else set()))

    content = (
        Arr(artifacts).map(lambda artifact: Arr(artifact.failures)).flatten().to_list()
    )
    written: dict[TemplatePath, DestinationPath] = {}
    for artifact in artifacts:
        refused = blocked(
            output_dir, tracked.destinations() | set(written.values()), artifact.target
        )
        if refused is not None:
            content.append(refused)
            continue
        target = output_dir.root / artifact.target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_bytes(artifact))
        written[artifact.source] = artifact.target
        log.info("%s %s into %s", artifact.verb, artifact.source, artifact.target)

    if structural:
        refused = blocked(
            output_dir, tracked.destinations() | set(written.values()), reasons
        )
        if refused is not None:
            content.append(refused)
        else:
            (output_dir.root / reasons).write_text(report(structural), encoding="utf-8")
            # The report answers to the run, not to a template, so it is its own source.
            written[TemplatePath(RelativePath(reasons))] = reasons

    # Written last and only for what really landed, so the manifest can never claim a
    # file this run refused to write.
    write_manifest(output_dir, Manifest(written))

    # A structural failure is a content failure; 2 stays reserved for an impossible run.
    return ExitCode(max(worst(content), 1 if structural else 0))


def _bytes(artifact: _Artifact) -> bytes:
    if isinstance(artifact.content, bytes):
        return artifact.content
    return annotated(artifact.content, artifact.source).encode("utf-8")
