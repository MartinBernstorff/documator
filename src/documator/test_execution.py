import time

import pytest

from documator.domain import TimeoutSeconds
from documator.execution import Command, execute_block


def test_captures_stdout_in_a_plain_fence() -> None:
    assert (
        execute_block(Command("echo hello"), TimeoutSeconds(10)).block
        == "```\nhello\n```\n"
    )


def test_merges_stderr_into_stdout_in_write_order() -> None:
    output = execute_block(Command("echo a; echo b >&2; echo c"), TimeoutSeconds(10))

    assert output.block == "```\na\nb\nc\n```\n"


def test_keeps_stderr_written_before_a_timeout() -> None:
    output = execute_block(Command("echo diagnosing >&2; sleep 5"), TimeoutSeconds(0.3))

    assert "diagnosing" in output.block


def test_marks_a_non_zero_exit_and_keeps_its_output() -> None:
    output = execute_block(Command("echo partial; exit 3"), TimeoutSeconds(10))

    assert "partial" in output.block
    assert "exit 3" in output.block


def test_marks_a_timeout_differently_from_a_non_zero_exit() -> None:
    timed_out = execute_block(Command("sleep 5"), TimeoutSeconds(0.1))
    failed = execute_block(Command("false"), TimeoutSeconds(10))

    assert "timed out" in timed_out.block
    assert "timed out" not in failed.block


def test_reports_a_clean_run_as_unfailed() -> None:
    assert execute_block(Command("echo hi"), TimeoutSeconds(10)).failure is None


def test_reports_a_non_zero_exit_as_a_failure() -> None:
    assert execute_block(Command("exit 3"), TimeoutSeconds(10)).failure == "exit 3"


def test_reports_a_timeout_as_a_failure() -> None:
    failure = execute_block(Command("sleep 5"), TimeoutSeconds(0.1)).failure

    assert failure is not None
    assert "timed out" in failure


def test_output_forging_the_annotation_is_not_reported_as_a_failure() -> None:
    forged = execute_block(Command("echo '[documator: exit 1]'"), TimeoutSeconds(10))

    assert forged.failure is None


def test_neutralizes_wiki_links_in_output() -> None:
    output = execute_block(Command("echo '![[Note]] [[Other]]'"), TimeoutSeconds(10))

    assert "[[" not in output.block
    assert "]]" not in output.block
    assert "Note" in output.block


def test_neutralizes_tags_in_output() -> None:
    output = execute_block(
        Command("echo 'see #alpha and #beta/gamma'"), TimeoutSeconds(10)
    )

    assert "#alpha" not in output.block
    assert "#beta" not in output.block
    assert "alpha" in output.block


def test_keeps_a_hash_that_cannot_start_a_tag() -> None:
    output = execute_block(
        Command("echo 'commit abc#1 and # heading'"), TimeoutSeconds(10)
    )

    assert "abc#1" in output.block
    assert "# heading" in output.block


def test_bounds_a_command_that_backgrounds_a_survivor() -> None:
    started = time.monotonic()

    execute_block(Command("echo hi; sleep 30 &"), TimeoutSeconds(0.3))

    assert time.monotonic() - started < 5


def test_does_not_leak_environment_between_invocations() -> None:
    execute_block(Command("export DOCUMATOR_LEAK=1"), TimeoutSeconds(10))

    assert (
        "1"
        not in execute_block(Command("echo $DOCUMATOR_LEAK"), TimeoutSeconds(10)).block
    )


def test_does_not_leak_working_directory_between_invocations() -> None:
    here = execute_block(Command("pwd"), TimeoutSeconds(10)).block
    execute_block(Command("cd /"), TimeoutSeconds(10))

    assert execute_block(Command("pwd"), TimeoutSeconds(10)).block == here


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("printf 'a\\n```\\nb'", "````\na\n```\nb\n````\n"),
        ("printf '````'", "`````\n````\n`````\n"),
    ],
)
def test_lengthens_the_fence_past_backticks(command: str, expected: str) -> None:
    assert execute_block(Command(command), TimeoutSeconds(10)).block == expected


def test_renders_empty_output_as_an_empty_fence() -> None:
    assert execute_block(Command("true"), TimeoutSeconds(10)).block == "```\n```\n"
