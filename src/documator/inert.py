from enum import StrEnum, auto
from pathlib import Path
from typing import NewType

from iterpy import Arr

from documator.domain import RelativePath


# Authors keep drafts, shared partials and tool droppings beside their templates, so a
# prefix on any path segment opts that path out. `render` still copies them: see README.
class PathClass(StrEnum):
    OPEN = auto()
    # `_`-prefixed: emits nothing, but stays readable as a `![[transclusion]]` target.
    INERT = auto()
    # `.`-prefixed: never walked, never read, never an error.
    INVISIBLE = auto()


Stem = NewType("Stem", str)


# A prefix is input-side vocabulary about what a note is, so it is stripped from every
# name a reader ever sees.
def stem(path: RelativePath) -> Stem:
    return Stem(path.stem.removeprefix("_").removeprefix("@"))


# Mirroring keeps the tree but not the vocabulary, so the mark comes off every segment.
def unmarked(path: RelativePath) -> RelativePath:
    return RelativePath(Path(*(part.removeprefix("@") for part in path.parts)))


# `@` marks one node, unlike the prefixes above, which any segment can carry: a folder
# holding a SKILL.md wears it for the folder, a lone note wears it for itself.
def skill_name(path: RelativePath) -> Stem | None:
    marked = path.parent.name if path.name == "SKILL.md" else path.stem
    return Stem(marked.removeprefix("@")) if marked.startswith("@") else None


def classify(path: RelativePath) -> PathClass:
    segments = Arr(path.parts)
    if segments.any(lambda segment: segment.startswith(".")):
        return PathClass.INVISIBLE
    if segments.any(lambda segment: segment.startswith("_")):
        return PathClass.INERT
    return PathClass.OPEN
