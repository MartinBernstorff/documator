import shutil

from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds
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
from documator.parsing import Markdown
from documator.transclusion import NotePath, index


def render(
    input_dir: InputDir, output_dir: OutputDir, timeout: TimeoutSeconds
) -> ExitCode:
    conflict = directory_conflict(input_dir, output_dir)
    if conflict is not None:
        return report_conflict(conflict)

    relative_paths = relative_files(input_dir)

    # Prune first, so a stale path cannot block a file whose kind changed.
    prune(output_dir, set(relative_paths))

    # Indexed once per run, so every transclusion in the run sees the same vault.
    vault = index(input_dir)

    failures: list[Failure] = []
    for relative in relative_paths:
        source = input_dir.root / relative
        target = output_dir.root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.suffix.lower() == ".md":
            rendered = render_markdown(
                Markdown(source.read_text(encoding="utf-8")),
                Origin(vault, (NotePath(relative),)),
                timeout,
            )
            target.write_text(rendered.text, encoding="utf-8")
            failures.extend(rendered.failures)
        else:
            shutil.copy2(source, target)
        log.info("rendered %s", relative)

    return worst(failures)
