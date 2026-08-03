from dataclasses import dataclass
from pathlib import Path
from typing import NewType

TreeLayout = NewType("TreeLayout", str)


@dataclass(frozen=True)
class TreeEntry:
    path: Path
    content: str | None


def _unescape(content: str) -> str:
    return content.replace("\\n", "\n").replace("\\t", "\t")


def _parse(layout: TreeLayout) -> list[TreeEntry]:
    lines = [
        (len(line) - len(line.lstrip(" ")), line.strip())
        for line in layout.splitlines()
        if line.strip()
    ]
    parents: list[tuple[int, Path]] = [(-1, Path())]
    entries: list[TreeEntry] = []
    for position, (indent, line) in enumerate(lines):
        while parents[-1][0] >= indent:
            parents.pop()
        name, separator, content = line.partition("|")
        relative = parents[-1][1] / name.strip()
        nests_children = position + 1 < len(lines) and lines[position + 1][0] > indent
        if separator or (Path(name.strip()).suffix and not nests_children):
            entries.append(TreeEntry(relative, _unescape(content.removeprefix(" "))))
            continue
        entries.append(TreeEntry(relative, None))
        parents.append((indent, relative))
    return entries


def build_tree(base: Path, layout: TreeLayout) -> None:
    for entry in _parse(layout):
        target = base / entry.path
        if entry.content is None:
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(entry.content)


# The manifest is bookkeeping, not output: spelling it into every expected tree would
# bury what each test is actually about. `test_manifest.py` asserts it directly.
def _describe(base: Path) -> dict[Path, str | None]:
    return {
        path.relative_to(base): None if path.is_dir() else path.read_text()
        for path in base.rglob("*")
        if path.name != ".documator-manifest.json"
    }


def assert_tree(base: Path, layout: TreeLayout) -> None:
    expected = {entry.path: entry.content for entry in _parse(layout)}
    assert _describe(base) == expected
