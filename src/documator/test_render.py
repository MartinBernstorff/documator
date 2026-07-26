import logging
from pathlib import Path

import pytest
from inline_snapshot import snapshot

from documator.domain import InputDir, OutputDir, TimeoutSeconds
from documator.engine import ConflictReason
from documator.render import render
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


def test_executable_block_is_replaced_by_its_output(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | # Note\\n\\n```\\n!echo hi\\n```\\n\\nafter\\n
            out
        """),
    )

    assert _render(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "note.md").read_text() == (
        "# Note\n\n```\nhi\n```\n\nafter\n"
    )


def test_block_runs_beside_its_own_file(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              sub
                note.md | ```\\n!cat sibling.txt\\n```\\n
                sibling.txt | neighbour\\n
            out
        """),
    )

    assert _render(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "sub" / "note.md").read_text() == snapshot("""\
```
neighbour
```
""")


def test_non_markdown_file_is_copied_without_executing_its_blocks(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              recipe.txt | ```\\n!echo hi\\n```\\n
            out
        """),
    )

    assert _render(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "recipe.txt").read_text() == "```\n!echo hi\n```\n"


def test_failing_block_embeds_its_output_and_the_run_continues(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              a.md | ```\\n!echo partial; exit 3\\n```\\n
              b.md | ```\\n!echo second\\n```\\n
            out
        """),
    )

    assert _render(tmp_path / "in", tmp_path / "out") == 1

    assert (tmp_path / "out" / "a.md").read_text() == (
        "```\npartial\n[documator: exit 3]\n```\n"
    )
    assert (tmp_path / "out" / "b.md").read_text() == "```\nsecond\n```\n"


def test_timeout_bounds_every_block(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | ```\\n!sleep 5\\n```\\n
            out
        """),
    )

    exit_code = render(
        InputDir(tmp_path / "in"), OutputDir(tmp_path / "out"), TimeoutSeconds(0.3)
    )

    assert exit_code == 1
    assert "timed out" in (tmp_path / "out" / "note.md").read_text()


def test_structural_error_is_marked_in_place_and_fails_the_run(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | ```\\n!echo one\\n!echo two\\n```\\n
            out
        """),
    )

    assert _render(tmp_path / "in", tmp_path / "out") == 1

    rendered = (tmp_path / "out" / "note.md").read_text()
    assert "!echo one" in rendered
    assert "more than one command line in a single block" in rendered


def test_embedded_output_cannot_inject_links_or_tags(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | ```\\n!echo '![[Note]] [[Other]] #tag'\\n```\\n
            out
        """),
    )

    assert _render(tmp_path / "in", tmp_path / "out") == 0

    rendered = (tmp_path / "out" / "note.md").read_text()
    assert "[[" not in rendered
    assert "]]" not in rendered
    assert "#tag" not in rendered
    assert "Note" in rendered


def test_non_ascii_content_round_trips(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("in\nout"))
    (tmp_path / "in" / "note.md").write_text("blåbær — 日本\n", encoding="utf-8")

    assert _render(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "note.md").read_text(encoding="utf-8") == (
        "blåbær — 日本\n"
    )


def test_undecodable_command_output_does_not_abort_the_render(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | ```\\n!printf '\\\\xff'; echo ok\\n```\\n
            out
        """),
    )

    assert _render(tmp_path / "in", tmp_path / "out") == 0

    assert "ok" in (tmp_path / "out" / "note.md").read_text(encoding="utf-8")


def test_uppercase_markdown_extension_is_parsed(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              NOTE.MD | ```\\n!echo hi\\n```\\n
            out
        """),
    )

    assert _render(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "NOTE.MD").read_text() == "```\nhi\n```\n"


def test_logs_each_executed_block_with_its_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              sub
                note.md | ```\\n!echo hi\\n```\\n
            out
        """),
    )

    with caplog.at_level(logging.INFO, logger="documator"):
        assert _render(tmp_path / "in", tmp_path / "out") == 0

    assert "executing echo hi in sub/note.md" in caplog.text
    assert "rendered sub/note.md" in caplog.text


def test_logs_a_failing_block_where_it_arises(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              note.md | ```\\n!exit 3\\n```\\n
            out
        """),
    )

    with caplog.at_level(logging.ERROR, logger="documator"):
        assert _render(tmp_path / "in", tmp_path / "out") == 1

    assert "note.md" in caplog.text
    assert "exit 3" in caplog.text
