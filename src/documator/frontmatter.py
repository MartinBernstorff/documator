import re
from dataclasses import dataclass
from typing import NewType

from iterpy import Arr

from documator.parsing import Markdown

SkillName = NewType("SkillName", str)
DeclaredLine = NewType("DeclaredLine", str)


# Declared keys are kept as raw lines: the loader is the authority on their shape, so
# nothing here needs to understand YAML beyond spotting which key a line opens.
@dataclass(frozen=True, slots=True)
class Template:
    declared: tuple[DeclaredLine, ...]
    body: Markdown


def split(source: Markdown) -> Template:
    block = re.match(
        r"---[ \t]*\n(?P<declared>.*?)^---[ \t]*(?:\n|\Z)",
        source,
        re.DOTALL | re.MULTILINE,
    )
    if block is None:
        return Template((), source)
    declared = Arr(block["declared"].splitlines()).map(DeclaredLine).to_list()
    return Template(tuple(declared), Markdown(source[block.end() :]))


def compose(
    name: SkillName, declared: tuple[DeclaredLine, ...], body: Markdown
) -> Markdown:
    described = (
        declared
        if Arr(declared).any(_opens_description)
        else (DeclaredLine(f"description: {name}"), *declared)
    )
    lines = Arr((DeclaredLine(f"name: {name}"), *described)).map(
        lambda line: line + "\n"
    )
    return Markdown(f"---\n{''.join(lines)}---\n{body}")


def _opens_description(line: DeclaredLine) -> bool:
    return re.match(r"description[ \t]*:", line) is not None
