import re
from dataclasses import dataclass
from typing import NewType

from iterpy import Arr

from documator.domain import RelativePath
from documator.execution import Emitted, neutralized
from documator.frontmatter import (
    SkillName,
    Template,
    declares_empty_description,
    declares_name,
)
from documator.parsing import Markdown

Reason = NewType("Reason", str)


# Name and source travel together everywhere a skill is judged, and the name is decided
# by the path, so the pair is one value rather than two arguments.
@dataclass(frozen=True, slots=True)
class Derived:
    name: SkillName
    source: RelativePath

    def __str__(self) -> str:
        return f"{self.source} ({self.name})"


# The name is a public identifier, so it is validated and reported verbatim: renaming it
# silently would be a breaking change at a distance.
@dataclass(frozen=True, slots=True)
class InvalidName:
    derived: Derived

    def __str__(self) -> str:
        return f'{self.derived.source}: "{self.derived.name}" is not a valid skill name'


# One global namespace spans both template forms, so the name alone identifies a clash.
@dataclass(frozen=True, slots=True)
class Collision:
    name: SkillName
    sources: tuple[RelativePath, ...]

    def __str__(self) -> str:
        claimants = " and ".join(str(source) for source in self.sources)
        return f'the name "{self.name}" is claimed by {claimants}'


# A skill with a name, a description and no body is worse than an absent one: the loader
# offers it and the agent invokes it for blank instructions.
@dataclass(frozen=True, slots=True)
class EmptyTemplate:
    derived: Derived

    def __str__(self) -> str:
        return f"{self.derived}: the template is empty"


@dataclass(frozen=True, slots=True)
class DeclaredName:
    derived: Derived

    def __str__(self) -> str:
        return f"{self.derived}: the template declares name, which the compiler sets"


@dataclass(frozen=True, slots=True)
class EmptyDescription:
    derived: Derived

    def __str__(self) -> str:
        return f"{self.derived}: the template declares an empty description"


@dataclass(frozen=True, slots=True)
class Unreadable:
    derived: Derived
    reason: Reason

    def __str__(self) -> str:
        return f"{self.derived}: the template cannot be read: {self.reason}"


# The mark says "this is a skill", so a path that cannot become one is the author asking
# for something the compiler will not do, rather than a mark to quietly ignore.
@dataclass(frozen=True, slots=True)
class MarkedAttachment:
    path: RelativePath

    def __str__(self) -> str:
        return f"{self.path}: only a note can be marked as a skill"


@dataclass(frozen=True, slots=True)
class MarkedInsideSkill:
    path: RelativePath

    def __str__(self) -> str:
        return f"{self.path}: already inside a skill, and skills do not nest"


type Misplaced = MarkedAttachment | MarkedInsideSkill
type UnusableSource = EmptyTemplate | DeclaredName | EmptyDescription
type StructuralFailure = (
    InvalidName | Collision | UnusableSource | Unreadable | Misplaced
)


def invalid_name(derived: Derived) -> InvalidName | None:
    legal = re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", derived.name) is not None
    return None if legal and len(derived.name) <= 64 else InvalidName(derived)


# Emptiness is measured on the stripped source: judging the render would make structural
# validity depend on subprocess output, and skills would blink in and out under --watch.
def unusable(derived: Derived, template: Template) -> UnusableSource | None:
    if declares_name(template.declared):
        return DeclaredName(derived)
    if declares_empty_description(template.declared):
        return EmptyDescription(derived)
    if not template.body.strip():
        return EmptyTemplate(derived)
    return None


def _at(failure: StructuralFailure) -> str:
    if isinstance(failure, Collision):
        return str(failure.sources[0])
    if isinstance(failure, MarkedAttachment | MarkedInsideSkill):
        return str(failure.path)
    return str(failure.derived.source)


# Sorted by source path, so re-runs over an unchanged tree are byte-identical, and
# neutralized, because the report lands in the same vault the reader browses.
def report(failures: list[StructuralFailure]) -> Markdown:
    reasons = (
        Arr(sorted(failures, key=_at))
        .map(lambda failure: f"- {neutralized(Emitted(str(failure)))}\n")
        .to_list()
    )
    return Markdown(f"# documator errors\n\n{''.join(reasons)}")
