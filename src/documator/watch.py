import logging
from threading import Event

from watchfiles import watch as watch_paths

from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds
from documator.render import render

DEBOUNCE_MS = 300
OPERATIONAL_ERROR = ExitCode(2)

logger = logging.getLogger(__name__)


def watch(
    input_dir: InputDir,
    output_dir: OutputDir,
    timeout: TimeoutSeconds,
    stop_event: Event | None = None,
) -> ExitCode:
    # watchfiles logs its own "N changes detected" at INFO; we report the re-render.
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    exit_code = _render_swallowing_errors(input_dir, output_dir, timeout)
    logger.info("Watching %s for changes", input_dir.root)
    for changes in watch_paths(
        input_dir.root, debounce=DEBOUNCE_MS, stop_event=stop_event
    ):
        logger.info("Re-rendering after %d change(s)", len(changes))
        exit_code = _render_swallowing_errors(input_dir, output_dir, timeout)
    return exit_code


def _render_swallowing_errors(
    input_dir: InputDir, output_dir: OutputDir, timeout: TimeoutSeconds
) -> ExitCode:
    try:
        return render(input_dir, output_dir, timeout)
    except Exception:
        logger.exception("Render failed; still watching")
        return OPERATIONAL_ERROR
