import io
import logging
import time
from typing import override

import pytest
from inline_snapshot import snapshot

from documator.logs import configure, drain


class _Terminal(io.StringIO):
    @override
    def isatty(self) -> bool:
        return True


def _frozen() -> None:
    for handler in logging.getLogger().handlers:
        handler.formatter.converter = lambda _: time.gmtime(0)  # pyrefly: ignore


def test_a_terminal_gets_lines_coloured_by_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    stream = _Terminal()
    configure(stream)
    _frozen()

    logging.getLogger("documator").info("rendered note.md")
    logging.getLogger("documator").warning("ignored notes.txt")
    logging.getLogger("documator").error("exit 3 in note.md")

    assert stream.getvalue() == snapshot("""\
00:00:00 INFO    rendered note.md\x1b[0m
\x1b[33m00:00:00 WARNING ignored notes.txt\x1b[0m
\x1b[31m00:00:00 ERROR   exit 3 in note.md\x1b[0m
""")


def test_a_redirected_stream_gets_no_colour() -> None:
    stream = io.StringIO()
    configure(stream)
    _frozen()

    logging.getLogger("documator").error("exit 3 in note.md")

    assert stream.getvalue() == snapshot("00:00:00 ERROR   exit 3 in note.md\n")


def test_no_color_disables_colour_on_a_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    stream = _Terminal()
    configure(stream)
    _frozen()

    logging.getLogger("documator").error("exit 3 in note.md")

    assert stream.getvalue() == snapshot("00:00:00 ERROR   exit 3 in note.md\n")


def test_the_summary_replays_problems_with_errors_last() -> None:
    stream = io.StringIO()
    summary = configure(stream)
    _frozen()

    logging.getLogger("documator").error("exit 3 in note.md")
    logging.getLogger("documator").info("rendered note.md")
    logging.getLogger("documator").warning("ignored notes.txt")

    assert summary.report() == snapshot("""\

── 1 warning, 1 error ──
00:00:00 WARNING ignored notes.txt
00:00:00 ERROR   exit 3 in note.md
""")


def test_a_clean_run_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    summary = configure(_Terminal())
    _frozen()

    logging.getLogger("documator").info("rendered note.md")

    assert summary.report() == snapshot("""\

\x1b[32m── no warnings or errors ──\x1b[0m
""")


def test_the_summary_heading_takes_the_colour_of_its_worst_problem(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    summary = configure(_Terminal())
    _frozen()

    logging.getLogger("documator").warning("ignored notes.txt")
    logging.getLogger("documator").error("exit 3 in note.md")

    assert summary.report() == snapshot("""\

\x1b[31m── 1 warning, 1 error ──\x1b[0m
\x1b[33m00:00:00 WARNING ignored notes.txt\x1b[0m
\x1b[31m00:00:00 ERROR   exit 3 in note.md\x1b[0m
""")


def test_a_silent_run_has_nothing_to_summarise() -> None:
    assert configure(io.StringIO()).report() == ""


def test_a_drained_summary_does_not_replay_the_previous_pass() -> None:
    stream = io.StringIO()
    configure(stream)
    _frozen()

    logging.getLogger("documator").error("exit 3 in note.md")
    drain(stream)
    logging.getLogger("documator").info("rendered note.md")
    drain(stream)

    assert stream.getvalue() == snapshot("""\
00:00:00 ERROR   exit 3 in note.md

── 1 error ──
00:00:00 ERROR   exit 3 in note.md
00:00:00 INFO    rendered note.md

── no warnings or errors ──
""")
