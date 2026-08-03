from pathlib import Path

from inline_snapshot import snapshot

from documator.domain import RelativePath
from documator.frontmatter import DeclaredLine, SkillName, Template
from documator.parsing import Markdown
from documator.structural import invalid_name, report, unusable


def test_only_lowercase_dashed_names_are_valid() -> None:
    candidates = [
        "code-review",
        "a1",
        "1",
        "Foo",
        "foo_bar",
        "-foo",
        "foo-",
        "foo--bar",
        "foo bar",
        "café",
        "",
        "a" * 64,
        "a" * 65,
    ]

    assert {
        name: invalid_name(RelativePath(Path("in.md")), SkillName(name)) is None
        for name in candidates
    } == snapshot(
        {
            "code-review": True,
            "a1": True,
            "1": True,
            "Foo": False,
            "foo_bar": False,
            "-foo": False,
            "foo-": False,
            "foo--bar": False,
            "foo bar": False,
            "café": False,
            "": False,
            "a" * 64: True,
            "a" * 65: False,
        }
    )


def test_an_invalid_name_is_reported_verbatim() -> None:
    error = invalid_name(
        RelativePath(Path("a/Code Review.md")), SkillName("Code Review")
    )

    assert str(error) == snapshot(
        'a/Code Review.md: "Code Review" is not a valid skill name'
    )


def test_a_body_of_only_whitespace_is_empty() -> None:
    error = unusable(
        RelativePath(Path("foo.md")),
        Template((DeclaredLine("description: real"),), Markdown("\n \t\n")),
    )

    assert str(error) == snapshot("foo.md: the template is empty")


def test_a_declared_name_is_unusable_even_when_it_matches_the_stem() -> None:
    error = unusable(
        RelativePath(Path("foo.md")),
        Template((DeclaredLine("name: foo"),), Markdown("body\n")),
    )

    assert str(error) == snapshot(
        "foo.md: the template declares name, which the compiler sets"
    )


def test_an_explicitly_empty_description_is_unusable() -> None:
    error = unusable(
        RelativePath(Path("foo.md")),
        Template((DeclaredLine("description:  "),), Markdown("body\n")),
    )

    assert str(error) == snapshot("foo.md: the template declares an empty description")


def test_a_usable_template_has_no_error() -> None:
    assert (
        unusable(
            RelativePath(Path("foo.md")),
            Template((DeclaredLine("description: real"),), Markdown("body\n")),
        )
        is None
    )


def test_the_report_lists_every_reason() -> None:
    errors = [
        invalid_name(RelativePath(Path("Foo.md")), SkillName("Foo")),
        unusable(RelativePath(Path("bar.md")), Template((), Markdown("\n"))),
    ]

    assert report([error for error in errors if error is not None]) == snapshot("""\
# documator errors

- Foo.md: "Foo" is not a valid skill name
- bar.md: the template is empty
""")
