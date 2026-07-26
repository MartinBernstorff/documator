from pathlib import Path

from documator.cli import main


def test_render_with_valid_args_exits_zero(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()
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
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "note.md").write_text("# Note\n")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    assert main(["render", str(input_dir), str(output_dir)]) == 0
    assert (output_dir / "note.md").read_text() == "# Note\n"


def test_render_with_a_failing_block_exits_one(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "note.md").write_text("```\n!exit 3\n```\n")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    assert main(["render", str(input_dir), str(output_dir)]) == 1


def test_timeout_flag_bounds_a_block(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "note.md").write_text("```\n!sleep 5\n```\n")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    assert main(["render", str(input_dir), str(output_dir), "--timeout", "0.3"]) == 1
    assert "timed out after 0.3s" in (output_dir / "note.md").read_text()


def test_default_timeout_lets_a_short_command_finish(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "note.md").write_text("```\n!sleep 0.5; echo done\n```\n")
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    assert main(["render", str(input_dir), str(output_dir)]) == 0
    assert (output_dir / "note.md").read_text() == "```\ndone\n```\n"


def test_render_with_a_non_numeric_timeout_exits_two(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    assert main(["render", str(input_dir), str(output_dir), "--timeout", "soon"]) == 2


def test_render_with_a_non_positive_timeout_exits_two(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    assert main(["render", str(input_dir), str(output_dir), "--timeout", "0"]) == 2


def test_render_into_nested_output_exits_two(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    nested_output = input_dir / "out"
    nested_output.mkdir(parents=True)

    assert main(["render", str(input_dir), str(nested_output)]) == 2
