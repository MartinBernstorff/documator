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


def test_a_hard_line_break_ending_a_section_survives() -> None:
    lent = section(
        Markdown("## Usage\n\nfirst  \n\n\n## Notes\n\nnope\n"),
        Target(NotePath(Path("Shared.md")), HeadingPath((HeadingText("Usage"),))),
    )

    assert isinstance(lent, str)
    assert lent.endswith("first  \n")
