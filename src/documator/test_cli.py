from pathlib import Path

from documator.cli import main


def test_render_with_valid_args_exits_zero(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"
    assert main(["render", str(input_dir), str(output_dir)]) == 0
