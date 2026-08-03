import re
from dataclasses import dataclass
from typing import NewType

from iterpy import Arr

from documator.domain import RelativePath
from documator.frontmatter import (
    SkillName,
    Template,
    declares_empty_description,
    declares_name,
)
from documator.parsing import Markdown

Reason = NewType("Reason", str)


# The name is a public identifier, so it is validated and reported verbatim: renaming
# it silently would be a breaking change at a distance.
@dataclass(frozen=True, slots=True)
class InvalidName:
    source: RelativePath
    name: SkillName

    def __str__(self) -> str:
        return f'{self.source}: "{self.name}" is not a valid skill name'


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
    source: RelativePath

    def __str__(self) -> str:
        return f"{self.source}: the template is empty"


@dataclass(frozen=True, slots=True)
class DeclaredName:
    source: RelativePath

    def __str__(self) -> str:
        return f"{self.source}: the template declares name, which the compiler sets"


@dataclass(frozen=True, slots=True)
class EmptyDescription:
    source: RelativePath

    def __str__(self) -> str:
        return f"{self.source}: the template declares an empty description"


@dataclass(frozen=True, slots=True)
class Unreadable:
    source: RelativePath
    reason: Reason

    def __str__(self) -> str:
        return f"{self.source}: the template cannot be read: {self.reason}"


type UnusableSource = EmptyTemplate | DeclaredName | EmptyDescription
type StructuralError = InvalidName | Collision | UnusableSource | Unreadable


def invalid_name(source: RelativePath, name: SkillName) -> InvalidName | None:
    legal = re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name) is not None
    return None if legal and len(name) <= 64 else InvalidName(source, name)


def collision(name: SkillName, sources: tuple[RelativePath, ...]) -> Collision | None:
    return Collision(name, sources) if len(sources) > 1 else None


# Emptiness is measured on the stripped source: judging the render would make structural
# validity depend on subprocess output, and skills would blink in and out under --watch.
def unusable(source: RelativePath, template: Template) -> UnusableSource | None:
    if declares_name(template.declared):
        return DeclaredName(source)
    if declares_empty_description(template.declared):
        return EmptyDescription(source)
    if not template.body.strip():
        return EmptyTemplate(source)
    return None


def report(errors: list[StructuralError]) -> Markdown:
    reasons = Arr(errors).map(lambda error: f"- {error}\n").to_list()
    return Markdown(f"# documator errors\n\n{''.join(reasons)}")
