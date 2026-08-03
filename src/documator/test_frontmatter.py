from inline_snapshot import snapshot

from documator.frontmatter import (
    DeclaredLine,
    SkillName,
    compose,
    declares_empty_description,
    declares_name,
    split,
)
from documator.parsing import Markdown


def test_template_without_frontmatter_is_all_body() -> None:
    template = split(Markdown("# Note\n\nbody\n"))

    assert (template.declared, template.body) == snapshot(((), "# Note\n\nbody\n"))


def test_frontmatter_is_lifted_out_of_the_body() -> None:
    template = split(Markdown("---\ndescription: does a thing\n---\n\n# Note\n"))

    assert (template.declared, template.body) == snapshot(
        (
            ("description: does a thing",),
            "\n# Note\n",
        )
    )


def test_empty_frontmatter_block_leaves_no_declared_keys() -> None:
    template = split(Markdown("---\n---\nbody\n"))

    assert (template.declared, template.body) == snapshot(((), "body\n"))


def test_a_later_horizontal_rule_does_not_close_a_frontmatter_that_never_opened() -> (
    None
):
    template = split(Markdown("# Note\n\n---\n\nafter\n"))

    assert (template.declared, template.body) == snapshot(
        (
            (),
            "# Note\n\n---\n\nafter\n",
        )
    )


def test_unterminated_opening_fence_is_body() -> None:
    template = split(Markdown("---\ndescription: dangling\n"))

    assert (template.declared, template.body) == snapshot(
        (
            (),
            "---\ndescription: dangling\n",
        )
    )


def test_composed_frontmatter_derives_a_description_from_the_name() -> None:
    composed = compose(SkillName("code-review"), (), Markdown("\n# Body\n"))

    assert composed == snapshot("""\
---
name: code-review
description: code-review
---

# Body
""")


def test_declared_description_wins_over_the_derived_one() -> None:
    composed = compose(
        SkillName("code-review"),
        (DeclaredLine("description: reviews code"),),
        Markdown("body\n"),
    )

    assert composed == snapshot("""\
---
name: code-review
description: reviews code
---
body
""")


def test_a_declared_name_is_spotted_whatever_its_spacing() -> None:
    assert {
        line: declares_name((DeclaredLine(line),))
        for line in [
            "name: other",
            "name : other",
            "name:",
            "nameless: yes",
            "model: x",
        ]
    } == snapshot(
        {
            "name: other": True,
            "name : other": True,
            "name:": True,
            "nameless: yes": False,
            "model: x": False,
        }
    )


def test_only_a_valueless_description_counts_as_empty() -> None:
    assert {
        line: declares_empty_description((DeclaredLine(line),))
        for line in ["description:", "description: ", "description:  x", "description"]
    } == snapshot(
        {
            "description:": True,
            "description: ": True,
            "description:  x": False,
            "description": False,
        }
    )


def test_declared_keys_pass_through_verbatim() -> None:
    composed = compose(
        SkillName("deploy"),
        (
            DeclaredLine("allowed-tools: Bash(git:*)"),
            DeclaredLine("model: opus"),
            DeclaredLine("unknown-key: [1, 2]"),
        ),
        Markdown("body\n"),
    )

    assert composed == snapshot("""\
---
name: deploy
description: deploy
allowed-tools: Bash(git:*)
model: opus
unknown-key: [1, 2]
---
body
""")
