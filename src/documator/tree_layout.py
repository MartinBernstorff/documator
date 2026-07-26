from pathlib import Path
from typing import NewType

TreeLayout = NewType("TreeLayout", str)


def _unescape(content: str) -> str:
    return content.replace("\\n", "\n").replace("\\t", "\t")


def build_tree(base: Path, layout: TreeLayout) -> None:
    entries = [
        (len(line) - len(line.lstrip(" ")), line.strip())
        for line in layout.splitlines()
        if line.strip()
    ]
    parents: list[tuple[int, Path]] = [(-1, base)]
    for position, (indent, entry) in enumerate(entries):
        while parents[-1][0] >= indent:
            parents.pop()
        name, separator, content = entry.partition("|")
        target = parents[-1][1] / name.strip()
        nests_children = (
            position + 1 < len(entries) and entries[position + 1][0] > indent
        )
        if separator or (Path(name.strip()).suffix and not nests_children):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(_unescape(content.removeprefix(" ")))
            continue
        target.mkdir(parents=True, exist_ok=True)
        parents.append((indent, target))
