from enum import StrEnum, auto

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


def classify(path: RelativePath) -> PathClass:
    segments = Arr(path.parts)
    if segments.any(lambda segment: segment.startswith(".")):
        return PathClass.INVISIBLE
    if segments.any(lambda segment: segment.startswith("_")):
        return PathClass.INERT
    return PathClass.OPEN
