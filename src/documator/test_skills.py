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
