import signal
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from inline_snapshot import snapshot

from documator.cli import main
from documator.tree_layout import TreeLayout, assert_tree, build_tree

WATCH_DEADLINE_SECONDS = 15.0


def _wait_for(
    done: Callable[[], bool], nudge: Callable[[], None] = lambda: None
) -> None:
    deadline = time.monotonic() + WATCH_DEADLINE_SECONDS
    while time.monotonic() < deadline:
        nudge()
        if done():
            return
        time.sleep(0.05)
    raise AssertionError("the watching CLI never reached the expected state")


def test_render_with_valid_args_exits_zero(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("in\nout"))

    assert main(["render", str(tmp_path / "in"), str(tmp_path / "out")]) == 0


def test_render_with_missing_input_dir_exits_two(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("out"))

    assert main(["render", str(tmp_path / "nope"), str(tmp_path / "out")]) == 2


def test_render_with_missing_output_dir_exits_two(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("in"))

    assert main(["render", str(tmp_path / "in"), str(tmp_path / "nope")]) == 2


def test_render_mirrors_the_input_tree(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
            out
        """),
    )

    assert main(["render", str(tmp_path / "in"), str(tmp_path / "out")]) == 0

    assert_tree(tmp_path / "out", TreeLayout("note.md | # Note\\n"))


def test_render_with_a_failing_block_exits_one(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | ```\\n!exit 3\\n```\\n
            out
        """),
    )

    assert main(["render", str(tmp_path / "in"), str(tmp_path / "out")]) == 1


def test_timeout_flag_bounds_a_block(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | ```\\n!sleep 5\\n```\\n
            out
        """),
    )

    args = ["render", str(tmp_path / "in"), str(tmp_path / "out"), "--timeout", "0.3"]
    assert main(args) == 1

    assert_tree(
        tmp_path / "out",
        TreeLayout("note.md | ```\\n[documator: timed out after 0.3s]\\n```\\n"),
    )


def test_default_timeout_lets_a_short_command_finish(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | ```\\n!sleep 0.5; echo done\\n```\\n
            out
        """),
    )

    assert main(["render", str(tmp_path / "in"), str(tmp_path / "out")]) == 0

    assert_tree(tmp_path / "out", TreeLayout("note.md | ```\\ndone\\n```\\n"))


def test_render_into_nested_output_exits_two(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              out
        """),
    )

    assert main(["render", str(tmp_path / "in"), str(tmp_path / "in" / "out")]) == 2


def test_render_accepts_an_explicit_timeout(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
            out
        """),
    )

    args = ["render", str(tmp_path / "in"), str(tmp_path / "out"), "--timeout", "2.5"]
    assert main(args) == 0

    assert_tree(tmp_path / "out", TreeLayout("note.md | # Note\\n"))


def test_non_numeric_timeout_exits_two(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("in\nout"))

    args = ["render", str(tmp_path / "in"), str(tmp_path / "out"), "--timeout", "soon"]
    assert main(args) == 2


def test_non_positive_timeout_exits_two(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("in\nout"))

    args = ["render", str(tmp_path / "in"), str(tmp_path / "out"), "--timeout", "0"]
    assert main(args) == 2


def test_unknown_flag_exits_two(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("in\nout"))

    args = ["render", str(tmp_path / "in"), str(tmp_path / "out"), "--parallel"]
    assert main(args) == 2


def test_skills_flattens_a_nested_template_tree(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              a
                foo.md | # Foo\\n
            out
        """),
    )

    assert main(["skills", str(tmp_path / "in"), str(tmp_path / "out")]) == 0

    assert_tree(
        tmp_path / "out",
        TreeLayout("""
            foo
              SKILL.md | ---\\nname: foo\\ndescription: foo\\n---\\n# Foo\\n
        """),
    )


def test_skills_with_a_failing_block_exits_one(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | ```\\n!exit 3\\n```\\n
            out
        """),
    )

    assert main(["skills", str(tmp_path / "in"), str(tmp_path / "out")]) == 1


def test_skills_with_missing_input_dir_exits_two(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("out"))

    assert main(["skills", str(tmp_path / "nope"), str(tmp_path / "out")]) == 2


def test_skills_timeout_flag_bounds_a_block(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | ```\\n!sleep 5\\n```\\n
            out
        """),
    )

    args = ["skills", str(tmp_path / "in"), str(tmp_path / "out"), "--timeout", "0.3"]
    assert main(args) == 1

    assert (tmp_path / "out" / "foo" / "SKILL.md").read_text() == snapshot("""\
---
name: foo
description: foo
---
```
[documator: timed out after 0.3s]
```
""")


def test_watch_flag_keeps_rendering_after_the_first_pass(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | original\\n
            out
        """),
    )
    rendered = tmp_path / "out" / "note.md"

    def edit() -> None:
        (tmp_path / "in" / "note.md").write_text("edited\n")

    # --watch never returns, so drive the real CLI out-of-process and kill it.
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "documator",
            "render",
            str(tmp_path / "in"),
            str(tmp_path / "out"),
            "--watch",
        ]
    )

    try:
        # The first pass runs before the watcher arms, so wait it out before editing;
        # only a re-render can turn the output into "edited" afterwards.
        _wait_for(lambda: rendered.is_file() and rendered.read_text() == "original\n")
        _wait_for(lambda: rendered.read_text() == "edited\n", edit)
    finally:
        process.terminate()
        process.wait(timeout=WATCH_DEADLINE_SECONDS)


def test_interrupting_watch_exits_zero_despite_a_failing_block(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | ```\\n!echo partial; exit 3\\n```\\n
            out
        """),
    )
    rendered = tmp_path / "out" / "note.md"

    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "documator",
            "render",
            str(tmp_path / "in"),
            str(tmp_path / "out"),
            "--watch",
        ]
    )

    _wait_for(lambda: rendered.is_file() and "exit 3" in rendered.read_text())
    process.send_signal(signal.SIGINT)

    assert process.wait(timeout=WATCH_DEADLINE_SECONDS) == 0
