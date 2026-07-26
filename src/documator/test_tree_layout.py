from pathlib import Path

import pytest

from documator.tree_layout import TreeLayout, assert_tree, build_tree


def test_creates_files_with_contents(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("note.md | # Note\\n"))

    assert_tree(tmp_path, TreeLayout("note.md | # Note\\n"))


def test_creates_directory_for_a_name_without_a_suffix(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("sub"))

    assert (tmp_path / "sub").is_dir()
    assert_tree(tmp_path, TreeLayout("sub"))


def test_creates_empty_file_for_a_suffixed_name_without_a_separator(
    tmp_path: Path,
) -> None:
    build_tree(tmp_path, TreeLayout("note.md"))

    assert (tmp_path / "note.md").is_file()
    assert_tree(tmp_path, TreeLayout("note.md"))


def test_creates_directory_for_a_suffixed_name_that_nests_children(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            note.md
              inner.md | inner\\n
        """),
    )

    assert (tmp_path / "note.md").is_dir()
    assert_tree(
        tmp_path,
        TreeLayout("""
            note.md
              inner.md | inner\\n
        """),
    )


def test_nests_entries_by_indentation(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
              sub
                nested.md | nested\\n
                data.csv | a,b\\n1,2\\n
            out
              stale.md | stale\\n
        """),
    )

    assert_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
              sub
                nested.md | nested\\n
                data.csv | a,b\\n1,2\\n
            out
              stale.md | stale\\n
        """),
    )


def test_dedents_back_to_an_outer_level(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              sub
                deep.md | deep\\n
              shallow.md | shallow\\n
        """),
    )

    assert_tree(
        tmp_path,
        TreeLayout("""
            in
              sub
                deep.md | deep\\n
              shallow.md | shallow\\n
        """),
    )


def test_creates_empty_file_for_empty_contents(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("empty.md |"))

    assert_tree(tmp_path, TreeLayout("empty.md |"))


def test_assert_tree_accepts_an_empty_layout_for_an_empty_directory(
    tmp_path: Path,
) -> None:
    assert_tree(tmp_path, TreeLayout(""))


def test_assert_tree_rejects_differing_contents(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("note.md | actual\\n"))

    with pytest.raises(AssertionError):
        assert_tree(tmp_path, TreeLayout("note.md | expected\\n"))


def test_assert_tree_rejects_an_unexpected_path(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            note.md | note\\n
            extra.md | extra\\n
        """),
    )

    with pytest.raises(AssertionError):
        assert_tree(tmp_path, TreeLayout("note.md | note\\n"))


def test_assert_tree_rejects_a_missing_path(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("note.md | note\\n"))

    with pytest.raises(AssertionError):
        assert_tree(
            tmp_path,
            TreeLayout("""
                note.md | note\\n
                missing.md | gone\\n
            """),
        )


def test_assert_tree_rejects_a_file_where_a_directory_is_expected(
    tmp_path: Path,
) -> None:
    build_tree(tmp_path, TreeLayout("note.md"))

    with pytest.raises(AssertionError):
        assert_tree(
            tmp_path,
            TreeLayout("""
                note.md
                  inner.md | inner\\n
            """),
        )
