import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path

from documator.cli import main

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


def _dirs(tmp_path: Path) -> tuple[Path, Path]:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    return input_dir, output_dir


def test_render_with_valid_args_exits_zero(tmp_path: Path) -> None:
    input_dir, output_dir = _dirs(tmp_path)
    assert main(["render", str(input_dir), str(output_dir)]) == 0


def test_render_with_missing_input_dir_exits_two(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    assert main(["render", str(tmp_path / "nope"), str(output_dir)]) == 2


def test_render_with_missing_output_dir_exits_two(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    assert main(["render", str(input_dir), str(tmp_path / "nope")]) == 2


def test_render_mirrors_the_input_tree(tmp_path: Path) -> None:
    input_dir, output_dir = _dirs(tmp_path)
    (input_dir / "note.md").write_text("# Note\n")

    assert main(["render", str(input_dir), str(output_dir)]) == 0
    assert (output_dir / "note.md").read_text() == "# Note\n"


def test_render_into_nested_output_exits_two(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    nested_output = input_dir / "out"
    nested_output.mkdir(parents=True)

    assert main(["render", str(input_dir), str(nested_output)]) == 2


def test_render_accepts_an_explicit_timeout(tmp_path: Path) -> None:
    input_dir, output_dir = _dirs(tmp_path)
    (input_dir / "note.md").write_text("# Note\n")

    assert main(["render", str(input_dir), str(output_dir), "--timeout", "2.5"]) == 0
    assert (output_dir / "note.md").read_text() == "# Note\n"


def test_non_numeric_timeout_exits_two(tmp_path: Path) -> None:
    input_dir, output_dir = _dirs(tmp_path)
    assert main(["render", str(input_dir), str(output_dir), "--timeout", "soon"]) == 2


def test_non_positive_timeout_exits_two(tmp_path: Path) -> None:
    input_dir, output_dir = _dirs(tmp_path)
    assert main(["render", str(input_dir), str(output_dir), "--timeout", "0"]) == 2


def test_unknown_flag_exits_two(tmp_path: Path) -> None:
    input_dir, output_dir = _dirs(tmp_path)
    assert main(["render", str(input_dir), str(output_dir), "--parallel"]) == 2


def test_watch_flag_keeps_rendering_after_the_first_pass(tmp_path: Path) -> None:
    input_dir, output_dir = _dirs(tmp_path)
    (input_dir / "note.md").write_text("original\n")
    rendered = output_dir / "note.md"

    # --watch never returns, so drive the real CLI out-of-process and kill it.
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "documator",
            "render",
            str(input_dir),
            str(output_dir),
            "--watch",
        ]
    )

    def edit() -> None:
        (input_dir / "note.md").write_text("edited\n")

    try:
        # The first pass runs before the watcher arms, so wait it out before editing;
        # only a re-render can turn the output into "edited" afterwards.
        _wait_for(lambda: rendered.is_file() and rendered.read_text() == "original\n")
        _wait_for(lambda: rendered.read_text() == "edited\n", edit)
    finally:
        process.terminate()
        process.wait(timeout=WATCH_DEADLINE_SECONDS)
