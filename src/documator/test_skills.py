import logging
from pathlib import Path

import pytest
from inline_snapshot import snapshot

from documator.domain import InputDir, OutputDir, TimeoutSeconds
from documator.engine import ConflictReason
from documator.skills import skills
from documator.tree_layout import TreeLayout, assert_tree, build_tree


def _skills(input_dir: Path, output_dir: Path) -> int:
    return skills(InputDir(input_dir), OutputDir(output_dir), TimeoutSeconds(10.0))


def test_nesting_never_appears_in_the_name_or_the_output_path(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              a
                b
                  foo.md | # Foo\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(
        tmp_path / "out",
        TreeLayout("""
            foo
              SKILL.md | ---\\nname: foo\\ndescription: foo\\n---\\n# Foo\\n
        """),
    )


def test_command_blocks_execute_beside_their_own_template(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              sub
                foo.md | ```\\n!cat sibling.txt\\n```\\n
                sibling.txt | neighbour\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "foo" / "SKILL.md").read_text() == snapshot("""\
---
name: foo
description: foo
---
```
neighbour
```
""")


def test_transclusions_inline(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | before ![[Shared]] after\\n
              parts
                Shared.md | inlined
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "foo" / "SKILL.md").read_text() == snapshot("""\
---
name: foo
description: foo
---
before inlined after
""")


def test_declared_description_overrides_the_derived_one(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | ---\\ndescription: does a thing\\nmodel: opus\\n---\\n\\n# Foo\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "foo" / "SKILL.md").read_text() == snapshot("""\
---
name: foo
description: does a thing
model: opus
---

# Foo
""")


def test_frontmatter_cannot_come_from_a_command_block(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | ```\\n!cat injected.txt\\n```\\n
              injected.txt | ---\\ndescription: injected\\n---\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "foo" / "SKILL.md").read_text() == snapshot("""\
---
name: foo
description: foo
---
```
---
description: injected
---
```
""")


def test_frontmatter_is_not_inherited_from_a_transclusion(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | ![[Shared]]
              Shared.md | ---\\ndescription: inherited\\n---\\nshared body\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "foo" / "SKILL.md").read_text() == snapshot("""\
---
name: foo
description: foo
---
---
description: inherited
---
shared body
""")


def test_output_not_produced_by_this_run_is_pruned(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | # Foo\\n
            out
              gone
                SKILL.md | stale\\n
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(
        tmp_path / "out",
        TreeLayout("""
            foo
              SKILL.md | ---\\nname: foo\\ndescription: foo\\n---\\n# Foo\\n
        """),
    )


def test_a_failing_block_still_compiles_and_prunes_the_rest(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              a.md | ```\\n!echo partial; exit 3\\n```\\n
              b.md | ```\\n!echo second\\n```\\n
            out
              gone
                SKILL.md | stale\\n
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 1

    assert not (tmp_path / "out" / "gone").exists()
    assert (tmp_path / "out" / "a" / "SKILL.md").read_text() == snapshot("""\
---
name: a
description: a
---
```
partial
[documator: exit 3]
```
""")
    assert (tmp_path / "out" / "b" / "SKILL.md").read_text() == snapshot("""\
---
name: b
description: b
---
```
second
```
""")


def test_a_folder_holding_skill_md_compiles_under_its_folder_name(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              guides
                plan
                  SKILL.md | # Body\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(
        tmp_path / "out",
        TreeLayout("""
            plan
              SKILL.md | ---\\nname: plan\\ndescription: plan\\n---\\n# Body\\n
        """),
    )


def test_the_whole_subtree_is_bundled_with_its_structure_preserved(
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

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(
        tmp_path / "out",
        TreeLayout("""
            plan
              SKILL.md | ---\\nname: plan\\ndescription: plan\\n---\\n# Body\\n
              references
                spec.pdf | %PDF-fake\\n
        """),
    )


def test_an_inert_or_invisible_path_inside_a_skill_folder_is_not_bundled(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo
                SKILL.md | # Foo\\n
                _draft.md | # Draft\\n
                .cache
                  junk.txt | junk\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(
        tmp_path / "out",
        TreeLayout("""
            foo
              SKILL.md | ---\\nname: foo\\ndescription: foo\\n---\\n# Foo\\n
        """),
    )


def test_an_undecodable_bundled_file_survives_byte_for_byte(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo
                SKILL.md | # Foo\\n
            out
        """),
    )
    (tmp_path / "in" / "foo" / "logo.png").write_bytes(b"\x89PNG\r\n\x1a\n\xff\xfe\x00")

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "foo" / "logo.png").read_bytes() == snapshot(
        b"\x89PNG\r\n\x1a\n\xff\xfe\x00"
    )


# On a case-insensitive filesystem a lowercase manifest must not be mistaken for
# SKILL.md, or the folder skill would be bundled over its own output.
def test_a_lowercase_skill_md_does_not_make_a_skill_folder(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo
                skill.md | # Lower\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(
        tmp_path / "out",
        TreeLayout("""
            skill
              SKILL.md | ---\\nname: skill\\ndescription: skill\\n---\\n# Lower\\n
        """),
    )


def test_a_bundled_markdown_file_renders_without_generated_frontmatter(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo
                SKILL.md | # Foo\\n
                notes.md | ---\\ndescription: mine\\n---\\n```\\n!echo bundled\\n```\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "foo" / "notes.md").read_text() == snapshot("""\
---
description: mine
---
```
bundled
```
""")


def test_a_deeper_skill_md_is_bundled_rather_than_producing_a_second_skill(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              outer
                SKILL.md | # Outer\\n
                example
                  SKILL.md | # Example\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(
        tmp_path / "out",
        TreeLayout("""
            outer
              SKILL.md | ---\\nname: outer\\ndescription: outer\\n---\\n# Outer\\n
              example
                SKILL.md | # Example\\n
        """),
    )


def test_a_bare_markdown_file_inside_a_skill_folder_is_not_its_own_skill(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              outer
                SKILL.md | # Outer\\n
                helper.md | # Helper\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert not (tmp_path / "out" / "helper").exists()


def test_a_folder_without_skill_md_produces_nothing(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              organisational
                notes.txt | loose\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(tmp_path / "out", TreeLayout(""))


def test_logs_each_bundled_file(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              outer
                SKILL.md | # Outer\\n
                example
                  SKILL.md | # Example\\n
            out
        """),
    )

    with caplog.at_level(logging.INFO, logger="documator"):
        assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert "bundled outer/example/SKILL.md into outer/example/SKILL.md" in caplog.text


def test_non_markdown_files_are_not_skills(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              notes.txt | not a skill\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(tmp_path / "out", TreeLayout(""))


def test_dot_prefixed_paths_are_invisible(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | # Foo\\n
              .hidden.md | # Hidden\\n
              .obsidian
                workspace.md | # Workspace\\n
                app.json | {}\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(
        tmp_path / "out",
        TreeLayout("""
            foo
              SKILL.md | ---\\nname: foo\\ndescription: foo\\n---\\n# Foo\\n
        """),
    )


def test_an_invisible_note_is_not_a_transclusion_target(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | ![[Secret]]
              .hidden
                Secret.md | secret\\n
            out
        """),
    )

    with caplog.at_level(logging.ERROR, logger="documator"):
        assert _skills(tmp_path / "in", tmp_path / "out") == 2

    assert caplog.messages == snapshot(
        ['no note matches transclusion "Secret" in foo.md']
    )


def test_an_invisible_attachment_embed_still_passes_through(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | ![[diagram.png]]\\n
              .assets
                diagram.png | binary\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert (tmp_path / "out" / "foo" / "SKILL.md").read_text() == snapshot("""\
---
name: foo
description: foo
---
![[diagram.png]]
""")


def test_underscore_prefixed_paths_emit_nothing_but_still_transclude(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | ![[Partial]]
              _draft.md | # Draft\\n
              _parts
                Partial.md | inlined\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(
        tmp_path / "out",
        TreeLayout("""
            foo
              SKILL.md | ---\\nname: foo\\ndescription: foo\\n---\\ninlined\\n
        """),
    )


def test_an_inert_segment_anywhere_on_the_path_produces_no_skill(
    tmp_path: Path,
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              a
                _shared
                  b
                    foo.md | # Foo\\n
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert_tree(tmp_path / "out", TreeLayout(""))


def test_an_ignored_loose_file_is_logged_at_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | # Foo\\n
              helper.py | print("hi")\\n
            out
        """),
    )

    with caplog.at_level(logging.INFO, logger="documator"):
        assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert [
        (record.levelname, record.message) for record in caplog.records
    ] == snapshot(
        [
            (
                "WARNING",
                "ignored helper.py: move it into a SKILL.md folder to bundle it",
            ),
            ("INFO", "compiled foo.md into foo/SKILL.md"),
        ]
    )


def test_an_ignored_inert_path_is_logged_at_info(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              .DS_Store | junk\\n
              _notes
                todo.txt | later\\n
            out
        """),
    )

    with caplog.at_level(logging.INFO, logger="documator"):
        assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert [
        (record.levelname, record.message) for record in caplog.records
    ] == snapshot(
        [
            ("INFO", "ignored .DS_Store"),
            ("INFO", "ignored _notes/todo.txt"),
        ]
    )


def test_unresolvable_transclusion_is_an_operational_error(tmp_path: Path) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | ![[Missing]]
            out
        """),
    )

    assert _skills(tmp_path / "in", tmp_path / "out") == 2


def test_identical_input_and_output_leaves_the_tree_untouched(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              foo.md | # Foo\\n
        """),
    )

    with caplog.at_level(logging.ERROR, logger="documator"):
        assert _skills(tmp_path / "in", tmp_path / "in") == 2

    assert ConflictReason.IDENTICAL in caplog.text
    assert_tree(tmp_path / "in", TreeLayout("foo.md | # Foo\\n"))


def test_logs_each_compiled_skill(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    build_tree(
        tmp_path,
        TreeLayout("""
            in
              deep
                foo.md | # Foo\\n
            out
        """),
    )

    with caplog.at_level(logging.INFO, logger="documator"):
        assert _skills(tmp_path / "in", tmp_path / "out") == 0

    assert "compiled deep/foo.md into foo/SKILL.md" in caplog.text
