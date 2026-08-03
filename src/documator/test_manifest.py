from pathlib import Path

from inline_snapshot import snapshot

from documator.domain import InputDir, OutputDir, TimeoutSeconds
from documator.render import render
from documator.skills import skills
from documator.tree_layout import TreeLayout, assert_tree, build_tree


def _manifest(output_dir: Path) -> str:
    return (output_dir / ".documator-manifest.json").read_text()


def test_render_records_every_file_it_wrote(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
              sub
                data.csv | a,b\\n
            out
        """),
    )

    assert (
        render(
            InputDir(tmp_path / "in"), OutputDir(tmp_path / "out"), TimeoutSeconds(10.0)
        )
        == 0
    )

    assert _manifest(tmp_path / "out") == snapshot("""\
{
  "note.md": "note.md",
  "sub/data.csv": "sub/data.csv"
}
""")


def test_skills_records_the_template_against_its_flattened_destination(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              guides
                plan
                  SKILL.md | # Body\\n
                  references
                    spec.pdf | %PDF-fake\\n
            out
        """),
    )

    assert (
        skills(
            InputDir(tmp_path / "in"), OutputDir(tmp_path / "out"), TimeoutSeconds(10.0)
        )
        == 0
    )

    assert _manifest(tmp_path / "out") == snapshot("""\
{
  "guides/plan/SKILL.md": "plan/SKILL.md",
  "guides/plan/references/spec.pdf": "plan/references/spec.pdf"
}
""")


def test_a_blocked_write_is_never_recorded(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
            out
              note.md | mine\\n
        """),
    )

    assert (
        render(
            InputDir(tmp_path / "in"), OutputDir(tmp_path / "out"), TimeoutSeconds(10.0)
        )
        == 2
    )

    assert "note.md" not in _manifest(tmp_path / "out")


def test_an_input_named_like_the_manifest_neither_lands_nor_is_claimed(
    tmp_path: Path,
) -> None:
    build_tree(tmp_path, TreeLayout("in\nout"))
    (tmp_path / "in" / ".documator-manifest.json").write_text("mine\n")

    assert (
        render(
            InputDir(tmp_path / "in"), OutputDir(tmp_path / "out"), TimeoutSeconds(10.0)
        )
        == 2
    )

    assert _manifest(tmp_path / "out") == snapshot("""\
{}
""")


def test_the_errors_report_is_tracked_like_any_other_output(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              Foo.md | # Foo\\n
            out
        """),
    )

    assert (
        skills(
            InputDir(tmp_path / "in"), OutputDir(tmp_path / "out"), TimeoutSeconds(10.0)
        )
        == 1
    )

    assert _manifest(tmp_path / "out") == snapshot("""\
{
  "documator-errors.md": "documator-errors.md"
}
""")


# Were a refused path recorded, the next run would read it as ours and delete it.
def test_a_file_a_refused_run_left_alone_survives_the_following_run(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
            out
              note.md | mine\\n
        """),
    )

    assert (
        render(
            InputDir(tmp_path / "in"), OutputDir(tmp_path / "out"), TimeoutSeconds(10.0)
        )
        == 2
    )
    (tmp_path / "in" / "note.md").unlink()

    assert (
        render(
            InputDir(tmp_path / "in"), OutputDir(tmp_path / "out"), TimeoutSeconds(10.0)
        )
        == 0
    )

    assert_tree(tmp_path / "out", TreeLayout("note.md | mine\\n"))


def test_an_unreadable_manifest_deletes_nothing(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n
            out
              stale.md | stale\\n
              .documator-manifest.json | not json at all\\n
        """),
    )

    assert (
        render(
            InputDir(tmp_path / "in"), OutputDir(tmp_path / "out"), TimeoutSeconds(10.0)
        )
        == 0
    )

    assert (tmp_path / "out" / "stale.md").read_text() == "stale\n"
