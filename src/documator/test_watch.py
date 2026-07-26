import logging
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from pathlib import Path
from threading import Event, Thread

import pytest

from documator.domain import ExitCode, InputDir, OutputDir
from documator.render import DEFAULT_TIMEOUT
from documator.watch import watch

POLL_SECONDS = 0.05
DEADLINE_SECONDS = 10.0

Nudge = Callable[[int], None]


class Watcher:
    def __init__(self, input_dir: InputDir, output_dir: OutputDir) -> None:
        self._stop = Event()
        self._exit_codes: list[ExitCode] = []
        self._thread = Thread(
            target=lambda: self._exit_codes.append(
                watch(input_dir, output_dir, DEFAULT_TIMEOUT, self._stop)
            ),
            daemon=True,
        )
        self._thread.start()

    def wait_until(self, done: Callable[[], bool], nudge: Nudge) -> None:
        # The watcher only arms after the initial render, so nudge until it takes.
        deadline = time.monotonic() + DEADLINE_SECONDS
        nudges = 0
        while not done() and time.monotonic() < deadline:
            nudges += 1
            nudge(nudges)
            time.sleep(POLL_SECONDS)
        assert done(), "the watcher never reached the expected state"

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=DEADLINE_SECONDS)


@contextmanager
def _watching(input_dir: InputDir, output_dir: OutputDir) -> Generator[Watcher]:
    watcher = Watcher(input_dir, output_dir)
    try:
        # Yield only once the initial render has landed, so anything a test observes
        # afterwards can only have come from a re-render.
        watcher.wait_until(
            _holds(output_dir.root / "note.md", "original\n"), lambda _nudge: None
        )
        yield watcher
    finally:
        watcher.stop()


def _vault(tmp_path: Path) -> tuple[InputDir, OutputDir]:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (input_dir / "note.md").write_text("original\n")
    return InputDir(input_dir), OutputDir(output_dir)


def _rewrite(path: Path, body: str) -> Nudge:
    def write(_nudge: int) -> None:
        path.write_text(body)

    return write


def _holds(path: Path, body: str) -> Callable[[], bool]:
    return lambda: path.is_file() and path.read_text() == body


def test_watch_mirrors_a_changed_note_into_the_output(tmp_path: Path) -> None:
    input_dir, output_dir = _vault(tmp_path)

    with _watching(input_dir, output_dir) as watcher:
        watcher.wait_until(
            _holds(output_dir.root / "note.md", "edited\n"),
            _rewrite(input_dir.root / "note.md", "edited\n"),
        )


@pytest.mark.parametrize("filename", ["data.csv", "diagram.png"])
def test_watch_mirrors_a_changed_non_markdown_file(
    tmp_path: Path, filename: str
) -> None:
    input_dir, output_dir = _vault(tmp_path)

    with _watching(input_dir, output_dir) as watcher:
        watcher.wait_until(
            _holds(output_dir.root / filename, "payload\n"),
            _rewrite(input_dir.root / filename, "payload\n"),
        )


def test_watch_debounces_a_burst_of_saves(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO, logger="documator.watch")
    input_dir, output_dir = _vault(tmp_path)
    note = input_dir.root / "note.md"

    def re_renders() -> int:
        return sum("Re-rendering" in record.message for record in caplog.records)

    def burst(nudge: int) -> None:
        for write in range(20):
            note.write_text(f"change {nudge}.{write}\n")

    with _watching(input_dir, output_dir) as watcher:
        watcher.wait_until(lambda: re_renders() >= 1, burst)

    # 20 writes inside one ~300 ms window must not each earn their own render.
    assert re_renders() < 20


def test_watch_keeps_going_after_a_render_fails(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.ERROR, logger="documator.watch")
    input_dir, output_dir = _vault(tmp_path)
    unreadable = input_dir.root / "locked.md"

    def render_failed() -> bool:
        return any("Render failed" in record.message for record in caplog.records)

    def lock(nudge: int) -> None:
        if not unreadable.exists():
            unreadable.write_text("secret\n")
            unreadable.chmod(0o000)
        # Keep the change stream alive in case the watcher had not armed yet.
        (input_dir.root / "note.md").write_text(f"change {nudge}\n")

    def unlock_and_add(_nudge: int) -> None:
        if unreadable.exists():
            unreadable.chmod(0o600)
            unreadable.unlink()
        (input_dir.root / "after.md").write_text("recovered\n")

    with _watching(input_dir, output_dir) as watcher:
        watcher.wait_until(render_failed, lock)
        watcher.wait_until(
            _holds(output_dir.root / "after.md", "recovered\n"), unlock_and_add
        )


def test_watch_renders_once_before_any_change(tmp_path: Path) -> None:
    input_dir, output_dir = _vault(tmp_path)
    stopped = Event()
    stopped.set()

    assert watch(input_dir, output_dir, DEFAULT_TIMEOUT, stopped) == 0
    assert (output_dir.root / "note.md").read_text() == "original\n"


def test_watch_returns_the_renders_exit_code(tmp_path: Path) -> None:
    nested = tmp_path / "in" / "out"
    nested.mkdir(parents=True)
    stopped = Event()
    stopped.set()

    conflicting = OutputDir(nested)
    assert watch(InputDir(nested.parent), conflicting, DEFAULT_TIMEOUT, stopped) == 2


def test_a_render_that_raises_reports_an_operational_error(tmp_path: Path) -> None:
    input_dir, output_dir = _vault(tmp_path)
    unreadable = input_dir.root / "locked.md"
    unreadable.write_text("secret\n")
    unreadable.chmod(0o000)
    stopped = Event()
    stopped.set()

    try:
        assert watch(input_dir, output_dir, DEFAULT_TIMEOUT, stopped) == 2
    finally:
        unreadable.chmod(0o600)
