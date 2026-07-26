import logging
from threading import Event

from watchfiles import watch as watch_paths

from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds
from documator.engine import directory_conflict, report_conflict
from documator.render import render

DEBOUNCE_MS = 300

logger = logging.getLogger(__name__)


def watch(
    input_dir: InputDir,
    output_dir: OutputDir,
    timeout: TimeoutSeconds,
    stop_event: Event | None = None,
) -> ExitCode:
    # watchfiles logs its own "N changes detected" at INFO; we report the re-render.
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    conflict = directory_conflict(input_dir, output_dir)
    if conflict is not None:
        return report_conflict(conflict)

    _render_swallowing_errors(input_dir, output_dir, timeout)
    logger.info("Watching %s for changes", input_dir.root)
    for changes in watch_paths(
        input_dir.root, debounce=DEBOUNCE_MS, stop_event=stop_event
    ):
        logger.info("Re-rendering after %d change(s)", len(changes))
        _render_swallowing_errors(input_dir, output_dir, timeout)

    # A session reports whether it shut down cleanly; per-iteration outcomes are logged.
    return ExitCode(0)


def _render_swallowing_errors(
    input_dir: InputDir, output_dir: OutputDir, timeout: TimeoutSeconds
) -> None:
    try:
        render(input_dir, output_dir, timeout)
    except Exception:
        logger.exception("Render failed; still watching")
