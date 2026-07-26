from pathlib import Path
from typing import NewType

TreeLayout = NewType("TreeLayout", str)

CONTENT_SEPARATOR = "|"


def _unescape(content: str) -> str:
    return content.replace("\\n", "\n").replace("\\t", "\t")


def build_tree(base: Path, layout: TreeLayout) -> None:
    parents: list[tuple[int, Path]] = [(-1, base)]
    for line in layout.splitlines():
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip(" "))
        while parents[-1][0] >= indent:
            parents.pop()
        name, separator, content = line.strip().partition(CONTENT_SEPARATOR)
        target = parents[-1][1] / name.strip()
        if separator:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_unescape(content.removeprefix(" ")))
            continue
        target.mkdir(parents=True, exist_ok=True)
        parents.append((indent, target))
