import pytest

from documator.domain import TimeoutSeconds
from documator.execution import Command, execute_block

GENEROUS = TimeoutSeconds(10)


def test_captures_stdout_in_a_plain_fence() -> None:
    assert execute_block(Command("echo hello"), GENEROUS) == "```\nhello\n```\n"


def test_merges_stderr_into_the_captured_stream() -> None:
    output = execute_block(Command("echo out; echo err >&2"), GENEROUS)

    assert "out" in output
    assert "err" in output


def test_marks_a_non_zero_exit_and_keeps_its_output() -> None:
    output = execute_block(Command("echo partial; exit 3"), GENEROUS)

    assert "partial" in output
    assert "exit 3" in output


def test_marks_a_timeout_differently_from_a_non_zero_exit() -> None:
    timed_out = execute_block(Command("sleep 5"), TimeoutSeconds(0.1))
    failed = execute_block(Command("false"), GENEROUS)

    assert "timed out" in timed_out
    assert "timed out" not in failed


def test_does_not_leak_environment_between_invocations() -> None:
    execute_block(Command("export DOCUMATOR_LEAK=1"), GENEROUS)

    assert "1" not in execute_block(Command("echo $DOCUMATOR_LEAK"), GENEROUS)


def test_does_not_leak_working_directory_between_invocations() -> None:
    here = execute_block(Command("pwd"), GENEROUS)
    execute_block(Command("cd /"), GENEROUS)

    assert execute_block(Command("pwd"), GENEROUS) == here


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("printf 'a\\n```\\nb'", "````\na\n```\nb\n````\n"),
        ("printf '````'", "`````\n````\n`````\n"),
    ],
)
def test_lengthens_the_fence_past_backticks(command: str, expected: str) -> None:
    assert execute_block(Command(command), GENEROUS) == expected


def test_renders_empty_output_as_an_empty_fence() -> None:
    assert execute_block(Command("true"), GENEROUS) == "```\n```\n"
