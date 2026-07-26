from inline_snapshot import snapshot

from documator.frontmatter import DeclaredLine, SkillName, compose, split
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
