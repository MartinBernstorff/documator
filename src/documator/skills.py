from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from iterpy import Arr

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
from documator.frontmatter import SkillName, compose, split
from documator.inert import PathClass, classify
from documator.parsing import Markdown
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
    template: _Template, vault: Vault, timeout: TimeoutSeconds
) -> list[_Artifact]:
    note = NotePath(template.source)
    # Frontmatter is lifted from the source, so no block or transclusion can forge it.
    source = split(Markdown(vault.read(note)))
    rendered = render_markdown(source.body, Origin(vault, (note,)), timeout)
    compiled = _Artifact(
        _Verb.COMPILED,
        template.source,
        RelativePath(Path(template.name) / "SKILL.md"),
        compose(template.name, source.declared, rendered.text).encode("utf-8"),
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

    # The whole tree resolves before anything is touched, so pruning is never partial.
    artifacts = (
        Arr(templates)
        .map(lambda template: Arr(_artifacts(template, vault, timeout)))
        .flatten()
        .to_list()
    )

    prune(output_dir, {artifact.target for artifact in artifacts})

    for artifact in artifacts:
        target = output_dir.root / artifact.target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(artifact.content)
        log.info("%s %s into %s", artifact.verb, artifact.source, artifact.target)

    return worst(
        Arr(artifacts).map(lambda artifact: Arr(artifact.failures)).flatten().to_list()
    )
