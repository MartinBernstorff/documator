import logging
from pathlib import Path

import pytest

from documator.domain import InputDir, OutputDir
from documator.render import DEFAULT_TIMEOUT, render


def _render(input_dir: Path, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    return render(InputDir(input_dir), OutputDir(output_dir), DEFAULT_TIMEOUT)


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    input_dir = tmp_path / "in"
    (input_dir / "sub").mkdir(parents=True)
    (input_dir / "note.md").write_text("# Note\n")
    (input_dir / "sub" / "nested.md").write_text("nested\n")
    (input_dir / "sub" / "data.csv").write_text("a,b\n1,2\n")
    return input_dir


def test_mirrors_input_tree_verbatim(vault: Path, tmp_path: Path) -> None:
    output_dir = tmp_path / "out"

    assert _render(vault, output_dir) == 0

    assert (output_dir / "note.md").read_text() == "# Note\n"
    assert (output_dir / "sub" / "nested.md").read_text() == "nested\n"
    assert (output_dir / "sub" / "data.csv").read_text() == "a,b\n1,2\n"


def test_copies_binary_files_verbatim(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    payload = bytes(range(256))
    (input_dir / "image.png").write_bytes(payload)
    output_dir = tmp_path / "out"

    assert _render(input_dir, output_dir) == 0
    assert (output_dir / "image.png").read_bytes() == payload


def test_prunes_output_paths_not_produced_by_this_run(
    vault: Path, tmp_path: Path
) -> None:
    output_dir = tmp_path / "out"
    (output_dir / "gone").mkdir(parents=True)
    (output_dir / "gone" / "stale.md").write_text("stale\n")

    assert _render(vault, output_dir) == 0

    assert not (output_dir / "gone").exists()
    assert (output_dir / "note.md").exists()


def test_stale_file_does_not_block_a_path_that_became_a_directory(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "in"
    (input_dir / "note.md").mkdir(parents=True)
    (input_dir / "note.md" / "inner.md").write_text("inner\n")
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "note.md").write_text("stale\n")

    assert _render(input_dir, output_dir) == 0
    assert (output_dir / "note.md" / "inner.md").read_text() == "inner\n"


def test_stale_directory_does_not_block_a_path_that_became_a_file(
    tmp_path: Path,
) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    (input_dir / "note.md").write_text("note\n")
    output_dir = tmp_path / "out"
    (output_dir / "note.md").mkdir(parents=True)
    (output_dir / "note.md" / "stale.md").write_text("stale\n")

    assert _render(input_dir, output_dir) == 0
    assert (output_dir / "note.md").read_text() == "note\n"


def test_copies_file_mode(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    script = input_dir / "run.sh"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    output_dir = tmp_path / "out"

    assert _render(input_dir, output_dir) == 0
    assert (output_dir / "run.sh").stat().st_mode & 0o777 == 0o755


def test_renders_files_in_sorted_path_order(
    vault: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="documator"):
        assert _render(vault, tmp_path / "out") == 0

    rendered = [
        record.message.removeprefix("rendered ")
        for record in caplog.records
        if record.message.startswith("rendered ")
    ]
    assert rendered == sorted(rendered)
    assert rendered == ["note.md", "sub/data.csv", "sub/nested.md"]


def test_identical_input_and_output_is_an_operational_error(vault: Path) -> None:
    assert _render(vault, vault) == 2


def test_output_nested_in_input_is_an_operational_error(vault: Path) -> None:
    assert _render(vault, vault / "sub" / "out") == 2


def test_input_nested_in_output_is_an_operational_error(
    vault: Path, tmp_path: Path
) -> None:
    assert _render(vault, tmp_path) == 2


def test_empty_input_directory_exits_zero(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()

    assert _render(input_dir, tmp_path / "out") == 0
