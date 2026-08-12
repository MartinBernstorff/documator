from pathlib import Path

from inline_snapshot import snapshot

from documator.parsing import Markdown
from documator.sections import section
from documator.transclusion import HeadingPath, HeadingText, NotePath, Target


def test_matches_a_heading_through_its_markup() -> None:
    assert section(
        Markdown("## **Usage**\n\nuse it\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("Usage"),))),
    ) == snapshot("""\
## **Usage**

use it
""")


def test_matches_a_heading_when_the_reference_carries_the_markup() -> None:
    assert section(
        Markdown("## Usage\n\nuse it\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("**Usage**"),))),
    ) == snapshot("""\
## Usage

use it
""")


def test_matches_a_heading_through_a_link() -> None:
    assert section(
        Markdown("## [Docs](https://example.com)\n\nread it\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("Docs"),))),
    ) == snapshot("""\
## [Docs](https://example.com)

read it
""")


def test_matches_a_heading_case_insensitively() -> None:
    assert section(
        Markdown("## Usage\n\nuse it\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("usage"),))),
    ) == snapshot("""\
## Usage

use it
""")


def test_matches_a_closed_heading() -> None:
    assert section(
        Markdown("## Usage ##\n\nuse it\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("Usage"),))),
    ) == snapshot("""\
## Usage ##

use it
""")


def test_matches_a_heading_at_any_depth() -> None:
    assert section(
        Markdown("# Top\n\n#### Usage\n\nuse it\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("Usage"),))),
    ) == snapshot("""\
#### Usage

use it
""")


def test_a_hash_in_frontmatter_is_not_a_heading() -> None:
    assert section(
        Markdown("---\n# a yaml comment\ntitle: Shared\n---\n\n## Usage\n\nuse it\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("Usage"),))),
    ) == snapshot("""\
## Usage

use it
""")


def test_an_underlined_heading_names_a_section() -> None:
    assert section(
        Markdown("Usage\n-----\n\nuse it\n\nNotes\n-----\n\nnope\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("Usage"),))),
    ) == snapshot("""\
Usage
-----

use it
""")


def test_an_underlined_heading_outranks_the_hashed_ones_below_it() -> None:
    assert section(
        Markdown("Title\n=====\n\n## Usage\n\nuse it\n\nOther\n=====\n\nnope\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("Title"),))),
    ) == snapshot("""\
Title
=====

## Usage

use it
""")


def test_a_hash_inside_a_fence_does_not_end_the_section() -> None:
    assert section(
        Markdown(
            "## Usage\n\nrun it:\n\n```sh\n# not a heading\nls\n```\n\n## Notes\n\nnope\n"
        ),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("Usage"),))),
    ) == snapshot("""\
## Usage

run it:

```sh
# not a heading
ls
```
""")


def test_a_rule_below_a_closing_fence_does_not_end_the_section() -> None:
    assert section(
        Markdown("## Usage\n\n```sh\nls\n```\n---\nmore\n\n## Notes\n\nnope\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("Usage"),))),
    ) == snapshot("""\
## Usage

```sh
ls
```
---
more
""")


def test_a_marked_heading_drops_its_section_from_the_whole_note() -> None:
    assert section(
        Markdown("## Usage\n\nuse it\n\n## _Notes\n\nscratch\n"),
        Target.whole(NotePath(Path("Shared.md"))),
    ) == snapshot("""\
## Usage

use it
""")


def test_a_marked_section_named_directly_is_still_lent_out() -> None:
    assert section(
        Markdown("## Usage\n\nuse it\n\n## _Notes\n\nscratch\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("_Notes"),))),
    ) == snapshot("""\
## _Notes

scratch
""")


def test_a_marked_heading_takes_its_subsections_with_it() -> None:
    assert section(
        Markdown(
            "## Usage\n\nuse it\n\n## _Notes\n\nscratch\n\n### Deeper\n\nmore scratch\n"
            "\n## Caveats\n\nmind it\n"
        ),
        Target.whole(NotePath(Path("Shared.md"))),
    ) == snapshot("""\
## Usage

use it

## Caveats

mind it
""")


def test_a_marked_underlined_heading_drops_its_section() -> None:
    assert section(
        Markdown("Usage\n-----\n\nuse it\n\n_Notes\n------\n\nscratch\n"),
        Target.whole(NotePath(Path("Shared.md"))),
    ) == snapshot("""\
Usage
-----

use it
""")


def test_a_marked_heading_nested_under_a_named_section_drops_with_it() -> None:
    assert section(
        Markdown("## Usage\n\nuse it\n\n### _Notes\n\nscratch\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("Usage"),))),
    ) == snapshot("""\
## Usage

use it
""")


def test_a_divider_closes_a_marked_section() -> None:
    assert section(
        Markdown("## _Notes\n\nscratch\n\n---\n\nplain prose\n"),
        Target.whole(NotePath(Path("Shared.md"))),
    ) == snapshot("plain prose\n")


def test_a_divider_inside_a_fence_does_not_close_a_marked_section() -> None:
    assert section(
        Markdown("## _Notes\n\n```\n---\n```\n\nstill scratch\n\n## Usage\n\nuse it\n"),
        Target.whole(NotePath(Path("Shared.md"))),
    ) == snapshot("""\
## Usage

use it
""")


def test_a_rule_underlining_prose_is_a_heading_rather_than_a_divider() -> None:
    assert section(
        Markdown("## _Notes\n\nDeeper\n------\n\nmore scratch\n\n## Usage\n\nuse it\n"),
        Target.whole(NotePath(Path("Shared.md"))),
    ) == snapshot("""\
Deeper
------

more scratch

## Usage

use it
""")


def test_a_divider_closes_a_marked_section_before_the_next_heading() -> None:
    assert section(
        Markdown("## _Notes\n\nscratch\n\n---\n\n## Usage\n\nuse it\n"),
        Target.whole(NotePath(Path("Shared.md"))),
    ) == snapshot("""\
## Usage

use it
""")


def test_a_code_span_heading_does_not_take_the_mark() -> None:
    assert section(
        Markdown("## `_private`\n\ndocumented\n"),
        Target.whole(NotePath(Path("Shared.md"))),
    ) == snapshot("""\
## `_private`

documented
""")


def test_a_hard_line_break_ending_a_section_survives() -> None:
    lent = section(
        Markdown("## Usage\n\nfirst  \n\n\n## Notes\n\nnope\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("Usage"),))),
    )

    assert isinstance(lent, str)
    assert lent.endswith("first  \n")
