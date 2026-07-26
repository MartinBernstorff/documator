from pathlib import Path

from documator.tree_layout import TreeLayout, build_tree


def test_creates_files_with_contents(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("note.md | # Note\\n"))

    assert (tmp_path / "note.md").read_text() == "# Note\n"


def test_creates_directory_for_a_name_without_a_suffix(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("sub"))

    assert (tmp_path / "sub").is_dir()


def test_creates_empty_file_for_a_suffixed_name_without_a_separator(
    tmp_path: Path,
) -> None:
    build_tree(tmp_path, TreeLayout("note.md"))

    assert (tmp_path / "note.md").read_text() == ""


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
    assert (tmp_path / "note.md" / "inner.md").read_text() == "inner\n"


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

    assert (tmp_path / "in" / "note.md").read_text() == "# Note\n"
    assert (tmp_path / "in" / "sub" / "nested.md").read_text() == "nested\n"
    assert (tmp_path / "in" / "sub" / "data.csv").read_text() == "a,b\n1,2\n"
    assert (tmp_path / "out" / "stale.md").read_text() == "stale\n"


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

    assert (tmp_path / "in" / "sub" / "deep.md").read_text() == "deep\n"
    assert (tmp_path / "in" / "shallow.md").read_text() == "shallow\n"


def test_creates_empty_file_for_empty_contents(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("empty.md |"))

    assert (tmp_path / "empty.md").read_text() == ""
