from dataclasses import dataclass
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
from documator.transclusion import NotePath, Vault, index, without_invisible_notes


@dataclass(frozen=True, slots=True)
class _Compiled:
    template: RelativePath
    target: RelativePath
    text: Markdown
    failures: list[Failure]


def _compile(
    template: RelativePath, vault: Vault, timeout: TimeoutSeconds
) -> _Compiled:
    name = SkillName(template.stem)
    note = NotePath(template)
    # Frontmatter is lifted from the source, so no block or transclusion can forge it.
    source = split(Markdown(vault.read(note)))
    rendered = render_markdown(source.body, Origin(vault, (note,)), timeout)
    return _Compiled(
        template,
        RelativePath(Path(name) / "SKILL.md"),
        compose(name, source.declared, rendered.text),
        rendered.failures,
    )


def _emits(path: RelativePath) -> bool:
    return path.suffix.lower() == ".md" and classify(path) is PathClass.OPEN


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

    files = Arr(relative_files(input_dir))
    for ignored in files.filter(lambda path: not _emits(path)).to_list():
        _report_ignored(ignored)

    # The whole tree resolves before anything is touched, so pruning is never partial.
    compiled = (
        files.filter(_emits)
        .map(lambda template: _compile(template, vault, timeout))
        .to_list()
    )

    prune(output_dir, {skill.target for skill in compiled})

    for skill in compiled:
        target = output_dir.root / skill.target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(skill.text, encoding="utf-8")
        log.info("compiled %s into %s", skill.template, skill.target)

    return worst(
        Arr(compiled).map(lambda skill: Arr(skill.failures)).flatten().to_list()
    )
