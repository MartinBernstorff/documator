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
from documator.parsing import Markdown
from documator.structural import (
    Reason,
    StructuralError,
    Unreadable,
    collision,
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
    name: SkillName
    source: RelativePath
    bundle: tuple[RelativePath, ...]


# Frontmatter is lifted from the source before anything runs, so no block or
# transclusion can forge it and every check is decided on what the author wrote.
@dataclass(frozen=True, slots=True)
class _Checked:
    template: _Template
    parsed: Template


class _Verb(StrEnum):
    COMPILED = "compiled"
    BUNDLED = "bundled"


@dataclass(frozen=True, slots=True)
class _Artifact:
    verb: _Verb
    source: RelativePath
    target: RelativePath
    content: bytes
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
            SkillName(entry.stem), RelativePath(current / entry.name), ()
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
    return _Template(SkillName(folder.name), RelativePath(source), tuple(bundle))


def _artifacts(
    checked: _Checked, vault: Vault, timeout: TimeoutSeconds
) -> list[_Artifact]:
    template = checked.template
    note = NotePath(template.source)
    rendered = render_markdown(checked.parsed.body, Origin(vault, (note,)), timeout)
    compiled = _Artifact(
        _Verb.COMPILED,
        template.source,
        RelativePath(Path(template.name) / "SKILL.md"),
        compose(template.name, checked.parsed.declared, rendered.text).encode("utf-8"),
        rendered.failures,
    )
    folder = RelativePath(template.source.parent)
    return [
        compiled,
        *(
            _bundled(template.name, path, folder, vault, timeout)
            for path in template.bundle
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
    target = RelativePath(Path(name) / path.relative_to(folder))
    if path.suffix.lower() != ".md":
        return _Artifact(
            _Verb.BUNDLED, path, target, vault.read_bytes(AttachmentPath(path)), []
        )
    note = NotePath(path)
    # A bundled note is a document, not a skill, so it renders without frontmatter.
    rendered = render_markdown(
        Markdown(vault.read(note)), Origin(vault, (note,)), timeout
    )
    return _Artifact(
        _Verb.BUNDLED, path, target, rendered.text.encode("utf-8"), rendered.failures
    )


# Names and collisions are decided from paths alone, so a broken skill never gets as far
# as executing one of its `!command` blocks.
def _named(templates: list[_Template]) -> tuple[list[_Template], list[StructuralError]]:
    judged = [
        (template, invalid_name(template.source, template.name))
        for template in templates
    ]
    return (
        [template for template, error in judged if error is None],
        [error for _, error in judged if error is not None],
    )


# The namespace is global and spans both template forms, because scoped checking is
# incoherent under a flat output layout.
def _unique(
    templates: list[_Template],
) -> tuple[list[_Template], list[StructuralError]]:
    claims = (
        Arr(templates)
        .groupby(lambda template: template.name)
        .map(
            lambda claim: collision(
                SkillName(claim[0]),
                tuple(template.source for template in claim[1]),
            )
        )
    )
    collisions = [error for error in claims.to_list() if error is not None]
    clashing = {error.name for error in collisions}
    return (
        [template for template in templates if template.name not in clashing],
        list(collisions),
    )


def _read(template: _Template, vault: Vault) -> _Checked | StructuralError:
    try:
        parsed = split(Markdown(vault.read(NotePath(template.source))))
    except (OSError, UnicodeDecodeError, ValidationError) as error:
        # Collapsed to one line, because each reason is one bullet in the report.
        return Unreadable(template.source, Reason(" ".join(str(error).split())))
    rejected = unusable(template.source, parsed)
    return rejected if rejected is not None else _Checked(template, parsed)


def _usable(
    templates: list[_Template], vault: Vault
) -> tuple[list[_Checked], list[StructuralError]]:
    read = [_read(template, vault) for template in templates]
    return (
        [outcome for outcome in read if isinstance(outcome, _Checked)],
        [outcome for outcome in read if not isinstance(outcome, _Checked)],
    )


def _unclaimed(input_dir: InputDir, templates: list[_Template]) -> list[RelativePath]:
    claimed = (
        Arr(templates)
        .map(lambda template: Arr([template.source, *template.bundle]))
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
    checked, unusable_sources = _usable(unique, vault)
    errors = [*misnamed, *colliding, *unusable_sources]
    for error in errors:
        log.error("%s", error)

    # The whole tree resolves before anything is touched, so pruning is never partial.
    artifacts = (
        Arr(checked)
        .map(lambda skill: Arr(_artifacts(skill, vault, timeout)))
        .flatten()
        .to_list()
    )

    # The reasons are an artifact of their own, so a stale one dies with the run that
    # produced it and a skill that failed loses its previously-compiled copy.
    reasons = RelativePath(Path("documator-errors.md"))
    produced = {artifact.target for artifact in artifacts}
    prune(output_dir, produced | ({reasons} if errors else set()))

    for artifact in artifacts:
        target = output_dir.root / artifact.target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact.content)
        log.info("%s %s into %s", artifact.verb, artifact.source, artifact.target)

    if errors:
        (output_dir.root / reasons).write_text(report(errors), encoding="utf-8")

    failed = worst(
        Arr(artifacts).map(lambda artifact: Arr(artifact.failures)).flatten().to_list()
    )
    # A structural error is a content failure; 2 stays reserved for an impossible run.
    return ExitCode(max(failed, 1 if errors else 0))
