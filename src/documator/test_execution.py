import time

import pytest

from documator.domain import TimeoutSeconds
from documator.execution import Command, execute_block


def test_captures_stdout_in_a_plain_fence() -> None:
    assert (
        execute_block(Command("echo hello"), TimeoutSeconds(10)) == "```\nhello\n```\n"
    )


def test_merges_stderr_into_stdout_in_write_order() -> None:
    output = execute_block(Command("echo a; echo b >&2; echo c"), TimeoutSeconds(10))

    assert output == "```\na\nb\nc\n```\n"


def test_keeps_stderr_written_before_a_timeout() -> None:
    output = execute_block(Command("echo diagnosing >&2; sleep 5"), TimeoutSeconds(0.3))

    assert "diagnosing" in output


def test_marks_a_non_zero_exit_and_keeps_its_output() -> None:
    output = execute_block(Command("echo partial; exit 3"), TimeoutSeconds(10))

    assert "partial" in output
    assert "exit 3" in output


def test_marks_a_timeout_differently_from_a_non_zero_exit() -> None:
    timed_out = execute_block(Command("sleep 5"), TimeoutSeconds(0.1))
    failed = execute_block(Command("false"), TimeoutSeconds(10))

    assert "timed out" in timed_out
    assert "timed out" not in failed


def test_bounds_a_command_that_backgrounds_a_survivor() -> None:
    started = time.monotonic()

    execute_block(Command("echo hi; sleep 30 &"), TimeoutSeconds(0.3))

    assert time.monotonic() - started < 5


def test_does_not_leak_environment_between_invocations() -> None:
    execute_block(Command("export DOCUMATOR_LEAK=1"), TimeoutSeconds(10))

    assert "1" not in execute_block(Command("echo $DOCUMATOR_LEAK"), TimeoutSeconds(10))


def test_does_not_leak_working_directory_between_invocations() -> None:
    here = execute_block(Command("pwd"), TimeoutSeconds(10))
    execute_block(Command("cd /"), TimeoutSeconds(10))

    assert execute_block(Command("pwd"), TimeoutSeconds(10)) == here


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("printf 'a\\n```\\nb'", "````\na\n```\nb\n````\n"),
        ("printf '````'", "`````\n````\n`````\n"),
    ],
)
def test_lengthens_the_fence_past_backticks(command: str, expected: str) -> None:
    assert execute_block(Command(command), TimeoutSeconds(10)) == expected


def test_renders_empty_output_as_an_empty_fence() -> None:
    assert execute_block(Command("true"), TimeoutSeconds(10)) == "```\n```\n"
