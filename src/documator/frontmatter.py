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
    # A declared name would land second in the block and win under YAML's last-key rule,
    # so it is dropped rather than passed through: the stem is the name, always.
    passed_through = (
        Arr(declared).filter(lambda line: not _opens(line, "name")).to_list()
    )
    described = (
        passed_through
        if Arr(passed_through).any(lambda line: _opens(line, "description"))
        else [DeclaredLine(f"description: {name}"), *passed_through]
    )
    lines = Arr([DeclaredLine(f"name: {name}"), *described]).map(
        lambda line: line + "\n"
    )
    return Markdown(f"---\n{''.join(lines)}---\n{body}")


def _opens(line: DeclaredLine, key: str) -> bool:
    return re.match(rf"{key}[ \t]*:", line) is not None
