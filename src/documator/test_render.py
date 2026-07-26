import logging
from pathlib import Path

import pytest

from documator.domain import InputDir, OutputDir, TimeoutSeconds
from documator.render import render
from documator.tree_layout import TreeLayout, build_tree

VAULT = TreeLayout("""
    in
      note.md | # Note\\n
      sub
        nested.md | nested\\n
        data.csv | a,b\\n1,2\\n
    out
""")


def _render(input_dir: Path, output_dir: Path) -> int:
    return render(InputDir(input_dir), OutputDir(output_dir), TimeoutSeconds(10.0))


@pytest.fixture
def vault(tmp_path: Path) -> Path:
    build_tree(tmp_path, VAULT)
    return tmp_path


def test_mirrors_input_tree_verbatim(vault: Path) -> None:
    output_dir = vault / "out"

    assert _render(vault / "in", output_dir) == 0

    assert (output_dir / "note.md").read_text() == "# Note\n"
    assert (output_dir / "sub" / "nested.md").read_text() == "nested\n"
    assert (output_dir / "sub" / "data.csv").read_text() == "a,b\n1,2\n"


def test_copies_binary_files_verbatim(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("in\nout"))
    payload = bytes(range(256))
    (tmp_path / "in" / "image.png").write_bytes(payload)

    assert _render(tmp_path / "in", tmp_path / "out") == 0
    assert (tmp_path / "out" / "image.png").read_bytes() == payload


def test_prunes_output_paths_not_produced_by_this_run(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
            out
              gone
                stale.md | stale\\n
        """),
    )
    output_dir = tmp_path / "out"

    assert _render(tmp_path / "in", output_dir) == 0

    assert not (output_dir / "gone").exists()
    assert (output_dir / "note.md").exists()


def test_stale_file_does_not_block_a_path_that_became_a_directory(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md
                inner.md | inner\\n
            out
              note.md | stale\\n
        """),
    )
    output_dir = tmp_path / "out"

    assert _render(tmp_path / "in", output_dir) == 0
    assert (output_dir / "note.md" / "inner.md").read_text() == "inner\n"


def test_stale_directory_does_not_block_a_path_that_became_a_file(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | note\\n
            out
              note.md
                stale.md | stale\\n
        """),
    )
    output_dir = tmp_path / "out"

    assert _render(tmp_path / "in", output_dir) == 0
    assert (output_dir / "note.md").read_text() == "note\n"


def test_copies_file_mode(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              run.sh | #!/bin/sh\\n
            out
        """),
    )
    (tmp_path / "in" / "run.sh").chmod(0o755)

    assert _render(tmp_path / "in", tmp_path / "out") == 0
    assert (tmp_path / "out" / "run.sh").stat().st_mode & 0o777 == 0o755


def test_renders_files_in_sorted_path_order(
    vault: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="documator"):
        assert _render(vault / "in", vault / "out") == 0

    rendered = [
        record.message.removeprefix("rendered ")
        for record in caplog.records
        if record.message.startswith("rendered ")
    ]
    assert rendered == sorted(rendered)
    assert rendered == ["note.md", "sub/data.csv", "sub/nested.md"]


def test_identical_input_and_output_is_an_operational_error(vault: Path) -> None:
    assert _render(vault / "in", vault / "in") == 2


def test_output_nested_in_input_is_an_operational_error(vault: Path) -> None:
    nested = vault / "in" / "sub" / "out"
    nested.mkdir()

    assert _render(vault / "in", nested) == 2


def test_input_nested_in_output_is_an_operational_error(vault: Path) -> None:
    assert _render(vault / "in", vault) == 2


def test_empty_input_directory_exits_zero(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("in\nout"))

    assert _render(tmp_path / "in", tmp_path / "out") == 0
