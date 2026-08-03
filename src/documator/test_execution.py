import time
from pathlib import Path

from inline_snapshot import snapshot

from documator.domain import TimeoutSeconds, WorkingDir
from documator.execution import Command, execute_block, execute_span


def test_captures_stdout_in_a_plain_fence() -> None:
    output = execute_block(
        Command("echo hello"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert output.block == snapshot("""\
```
hello
```
""")


def test_merges_stderr_into_stdout_in_write_order() -> None:
    output = execute_block(
        Command("echo a; echo b >&2; echo c"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert output.block == snapshot("""\
```
a
b
c
```
""")


def test_keeps_stderr_written_before_a_timeout() -> None:
    output = execute_block(
        Command("echo diagnosing >&2; sleep 5"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(0.3),
    )

    assert output.block == snapshot("""\
```
diagnosing
[documator: timed out after 0.3s]
```
""")


def test_marks_a_non_zero_exit_and_keeps_its_output() -> None:
    output = execute_block(
        Command("echo partial; exit 3"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert output.block == snapshot("""\
```
partial
[documator: exit 3]
```
""")


def test_marks_a_timeout_differently_from_a_non_zero_exit() -> None:
    timed_out = execute_block(
        Command("sleep 5"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(0.1),
    )
    failed = execute_block(Command("false"), WorkingDir(Path.cwd()), TimeoutSeconds(10))

    assert timed_out.block == snapshot("""\
```
[documator: timed out after 0.1s]
```
""")
    assert failed.block == snapshot("""\
```
[documator: exit 1]
```
""")


def test_reports_a_clean_run_as_unfailed() -> None:
    assert (
        execute_block(
            Command("echo hi"),
            WorkingDir(Path.cwd()),
            TimeoutSeconds(10),
        ).failure
        is None
    )


def test_reports_a_non_zero_exit_as_a_failure() -> None:
    failure = execute_block(
        Command("exit 3"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    ).failure

    assert failure == snapshot("exit 3")


def test_reports_a_timeout_as_a_failure() -> None:
    failure = execute_block(
        Command("sleep 5"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(0.1),
    ).failure

    assert failure == snapshot("timed out after 0.1s")


def test_output_forging_the_annotation_is_not_reported_as_a_failure() -> None:
    forged = execute_block(
        Command("echo '[documator: exit 1]'"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert forged.failure is None


# A snapshot would carry the zero-width spaces invisibly, so assert the absence that
# is the whole point of the guard.
def test_neutralizes_wiki_links_in_output() -> None:
    output = execute_block(
        Command("echo '![[Note]] [[Other]]'"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert "[[" not in output.block
    assert "]]" not in output.block
    assert "Note" in output.block


def test_neutralizes_tags_in_output() -> None:
    output = execute_block(
        Command("echo 'see #alpha and #beta/gamma'"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert "#alpha" not in output.block
    assert "#beta" not in output.block
    assert "alpha" in output.block


def test_keeps_a_hash_that_cannot_start_a_tag() -> None:
    output = execute_block(
        Command("echo 'commit abc#1 and # heading'"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert output.block == snapshot("""\
```
commit abc#1 and # heading
```
""")


def test_bounds_a_command_that_backgrounds_a_survivor() -> None:
    started = time.monotonic()

    execute_block(
        Command("echo hi; sleep 30 &"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(0.3),
    )

    assert time.monotonic() - started < 5


def test_does_not_leak_environment_between_invocations() -> None:
    execute_block(
        Command("export DOCUMATOR_LEAK=1"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    leaked = execute_block(
        Command("echo $DOCUMATOR_LEAK"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert leaked.block == snapshot("""\
```
```
""")


def test_runs_the_command_in_the_given_working_directory(tmp_path: Path) -> None:
    (tmp_path / "sibling.txt").write_text("neighbour\n", encoding="utf-8")

    output = execute_block(
        Command("cat sibling.txt"), WorkingDir(tmp_path), TimeoutSeconds(10)
    )

    assert output.block == snapshot("""\
```
neighbour
```
""")


def test_does_not_leak_working_directory_between_invocations() -> None:
    here = execute_block(
        Command("pwd"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    ).block
    execute_block(Command("cd /"), WorkingDir(Path.cwd()), TimeoutSeconds(10))

    assert (
        execute_block(
            Command("pwd"),
            WorkingDir(Path.cwd()),
            TimeoutSeconds(10),
        ).block
        == here
    )


def test_lengthens_the_fence_past_a_fence_in_the_output() -> None:
    output = execute_block(
        Command("printf 'a\\n```\\nb'"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert output.block == snapshot("""\
````
a
```
b
````
""")


def test_lengthens_the_fence_past_output_that_is_only_backticks() -> None:
    output = execute_block(
        Command("printf '````'"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert output.block == snapshot("""\
`````
````
`````
""")


def test_renders_empty_output_as_an_empty_fence() -> None:
    output = execute_block(Command("true"), WorkingDir(Path.cwd()), TimeoutSeconds(10))

    assert output.block == snapshot("""\
```
```
""")


def test_captures_one_line_of_output_in_a_span() -> None:
    output = execute_span(
        Command("echo hello"), WorkingDir(Path.cwd()), TimeoutSeconds(10)
    )

    assert output.span == snapshot("`hello`")


def test_strips_blank_lines_around_a_single_line_of_span_output() -> None:
    output = execute_span(
        Command("printf '\\n\\nhello\\n\\n'"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert output.span == snapshot("`hello`")


def test_marks_empty_span_output_so_it_leaves_no_hole() -> None:
    output = execute_span(Command("true"), WorkingDir(Path.cwd()), TimeoutSeconds(10))

    assert output.span == snapshot("`[documator: no output]`")


def test_marks_a_failing_span_inside_its_backticks() -> None:
    output = execute_span(
        Command("echo partial; exit 3"), WorkingDir(Path.cwd()), TimeoutSeconds(10)
    )

    assert output.span == snapshot("`partial [documator: exit 3]`")


def test_marks_a_failing_span_without_output_as_the_marker_alone() -> None:
    output = execute_span(Command("false"), WorkingDir(Path.cwd()), TimeoutSeconds(10))

    assert output.span == snapshot("`[documator: exit 1]`")


def test_marks_a_span_that_times_out() -> None:
    output = execute_span(
        Command("sleep 5"), WorkingDir(Path.cwd()), TimeoutSeconds(0.1)
    )

    assert output.span == snapshot("`[documator: timed out after 0.1s]`")


def test_promotes_multi_line_span_output_to_a_fence() -> None:
    output = execute_span(
        Command("printf 'a\\nb\\n'"), WorkingDir(Path.cwd()), TimeoutSeconds(10)
    )

    assert output.span == snapshot("""\

```
a
b
```
""")


def test_a_promoted_fence_carries_the_failure_marker_inside_it() -> None:
    output = execute_span(
        Command("printf 'a\\nb\\n'; exit 3"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert output.span == snapshot("""\

```
a
b
[documator: exit 3]
```
""")


def test_lengthens_the_span_delimiter_past_backticks_in_the_output() -> None:
    output = execute_span(
        Command("printf 'a``b'"), WorkingDir(Path.cwd()), TimeoutSeconds(10)
    )

    assert output.span == snapshot("```a``b```")


def test_pads_span_output_that_touches_a_backtick() -> None:
    output = execute_span(
        Command("printf '`x`'"), WorkingDir(Path.cwd()), TimeoutSeconds(10)
    )

    assert output.span == snapshot("`` `x` ``")


def test_reports_a_failing_span_as_a_failure() -> None:
    assert execute_span(
        Command("exit 3"), WorkingDir(Path.cwd()), TimeoutSeconds(10)
    ).failure == snapshot("exit 3")


def test_span_output_forging_the_annotation_is_not_reported_as_a_failure() -> None:
    forged = execute_span(
        Command("echo '[documator: exit 1]'"),
        WorkingDir(Path.cwd()),
        TimeoutSeconds(10),
    )

    assert forged.failure is None


# A snapshot would carry the zero-width spaces invisibly, so assert the absence that
# is the whole point of the guard.
def test_neutralizes_wiki_links_in_span_output() -> None:
    output = execute_span(
        Command("echo '[[Other]]'"), WorkingDir(Path.cwd()), TimeoutSeconds(10)
    )

    assert "[[" not in output.span
    assert "]]" not in output.span
    assert "Other" in output.span


def test_neutralizes_tags_in_span_output() -> None:
    output = execute_span(
        Command("echo 'see #alpha'"), WorkingDir(Path.cwd()), TimeoutSeconds(10)
    )

    assert "#alpha" not in output.span
    assert "alpha" in output.span


def test_runs_a_span_in_the_given_working_directory(tmp_path: Path) -> None:
    (tmp_path / "sibling.txt").write_text("neighbour\n", encoding="utf-8")

    output = execute_span(
        Command("cat sibling.txt"), WorkingDir(tmp_path), TimeoutSeconds(10)
    )

    assert output.span == snapshot("`neighbour`")
