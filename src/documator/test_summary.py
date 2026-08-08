import logging
from pathlib import Path

import pytest
from inline_snapshot import snapshot

from documator.domain import ExitCode, RelativePath
from documator.engine import Failure
from documator.execution import Annotation
from documator.summary import Errored, Produced, Warned, summarise
from documator.transclusion import NotePath


def test_the_count_leads_and_the_errors_come_last(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="documator"):
        summarise(
            Produced(3),
            [
                Errored(
                    Failure(
                        NotePath(RelativePath(Path("a.md"))),
                        Annotation("boom"),
                        ExitCode(1),
                    )
                ),
                Warned(Annotation("loose.txt: ignored")),
                Errored(
                    Failure(
                        NotePath(RelativePath(Path("b.md"))),
                        Annotation("bang"),
                        ExitCode(1),
                    )
                ),
            ],
        )

    assert [
        (record.levelname, record.message) for record in caplog.records
    ] == snapshot(
        [
            ("ERROR", "3 files, 1 warning, 2 errors"),
            (
                "WARNING",
                "loose.txt: ignored",
            ),
            ("ERROR", "a.md: boom"),
            ("ERROR", "b.md: bang"),
        ]
    )


def test_a_clean_run_reports_its_count_at_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="documator"):
        summarise(Produced(1), [])

    assert [
        (record.levelname, record.message) for record in caplog.records
    ] == snapshot([("INFO", "1 file, 0 warnings, 0 errors")])


def test_a_run_with_only_warnings_keeps_the_count_at_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="documator"):
        summarise(Produced(2), [Warned(Annotation("loose.txt: ignored"))])

    assert [record.levelname for record in caplog.records] == snapshot(
        ["WARNING", "WARNING"]
    )
