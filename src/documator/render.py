import shutil

from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds
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
from documator.manifest import (
    DestinationPath,
    Manifest,
    TemplatePath,
    read_manifest,
    write_manifest,
)
from documator.notice import annotated
from documator.parsing import Markdown
from documator.transclusion import NotePath, index


def render(
    input_dir: InputDir, output_dir: OutputDir, timeout: TimeoutSeconds
) -> ExitCode:
    conflict = directory_conflict(input_dir, output_dir)
    if conflict is not None:
        return report_conflict(conflict)

    relative_paths = relative_files(input_dir)
    tracked = read_manifest(output_dir)

    # Prune first, so a path this run reclaims is free before anything writes into it.
    prune(output_dir, tracked, {DestinationPath(path) for path in relative_paths})

    # Indexed once per run, so every transclusion in the run sees the same vault.
    vault = index(input_dir)

    failures: list[Failure] = []
    written: dict[TemplatePath, DestinationPath] = {}
    for relative in relative_paths:
        template = TemplatePath(relative)
        destination = DestinationPath(relative)
        # Checked before rendering, so a file that cannot land never runs its blocks.
        refused = blocked(
            output_dir, tracked.destinations() | set(written.values()), destination
        )
        if refused is not None:
            failures.append(refused)
            continue
        source = input_dir.root / relative
        target = output_dir.root / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".md":
            rendered = render_markdown(
                Markdown(source.read_text(encoding="utf-8")),
                Origin(vault, (NotePath(relative),)),
                timeout,
            )
            target.write_text(annotated(rendered.text, template), encoding="utf-8")
            failures.extend(rendered.failures)
        else:
            shutil.copy2(source, target)
        written[template] = destination
        log.info("rendered %s", relative)

    # Written last and only for what really landed, so the manifest can never claim a
    # file this run refused to write.
    write_manifest(output_dir, Manifest(written))

    return worst(failures)
