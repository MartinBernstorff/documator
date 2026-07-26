import logging
from pathlib import Path

import pytest

from documator.domain import InputDir, OutputDir, TimeoutSeconds
from documator.render import ConflictReason, render
from documator.tree_layout import TreeLayout, assert_tree, build_tree


def _render(input_dir: Path, output_dir: Path) -> int:
    return render(InputDir(input_dir), OutputDir(output_dir), TimeoutSeconds(10.0))


def test_mirrors_input_tree_verbatim(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
              sub
                nested.md | nested\\n
                data.csv | a,b\\n1,2\\n
            out
        """),
    )

    assert _render(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(
        tmp_path / "out",
        TreeLayout("""
            note.md | # Note\\n
            sub
              nested.md | nested\\n
              data.csv | a,b\\n1,2\\n
        """),
    )


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

    assert _render(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(tmp_path / "out", TreeLayout("note.md | # Note\\n"))


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

    assert _render(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(
        tmp_path / "out",
        TreeLayout("""
            note.md
              inner.md | inner\\n
        """),
    )


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

    assert _render(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(tmp_path / "out", TreeLayout("note.md | note\\n"))


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

    assert_tree(tmp_path / "out", TreeLayout("run.sh | #!/bin/sh\\n"))
    assert (tmp_path / "out" / "run.sh").stat().st_mode & 0o777 == 0o755


def test_renders_files_in_sorted_path_order(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
              sub
                nested.md | nested\\n
                data.csv | a,b\\n1,2\\n
            out
        """),
    )

    with caplog.at_level(logging.INFO, logger="documator"):
        assert _render(tmp_path / "in", tmp_path / "out") == 0

    rendered = [
        record.message.removeprefix("rendered ")
        for record in caplog.records
        if record.message.startswith("rendered ")
    ]
    assert rendered == sorted(rendered)
    assert rendered == ["note.md", "sub/data.csv", "sub/nested.md"]


def test_identical_input_and_output_leaves_the_tree_untouched(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
        """),
    )

    with caplog.at_level(logging.ERROR, logger="documator"):
        assert _render(tmp_path / "in", tmp_path / "in") == 2

    assert ConflictReason.IDENTICAL in caplog.text
    assert_tree(tmp_path / "in", TreeLayout("note.md | # Note\\n"))


def test_output_nested_in_input_leaves_the_tree_untouched(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
              out
        """),
    )

    with caplog.at_level(logging.ERROR, logger="documator"):
        assert _render(tmp_path / "in", tmp_path / "in" / "out") == 2

    assert ConflictReason.OUTPUT_NESTED_IN_INPUT in caplog.text
    assert_tree(
        tmp_path / "in",
        TreeLayout("""
            note.md | # Note\\n
            out
        """),
    )


def test_input_nested_in_output_leaves_the_tree_untouched(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
        """),
    )

    with caplog.at_level(logging.ERROR, logger="documator"):
        assert _render(tmp_path / "in", tmp_path) == 2

    assert ConflictReason.INPUT_NESTED_IN_OUTPUT in caplog.text
    assert_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
        """),
    )


def test_empty_input_directory_produces_an_empty_output(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("in\nout"))

    assert _render(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(tmp_path / "out", TreeLayout(""))
