import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import NewType

from iterpy import Arr

VariableName = NewType("VariableName", str)
VariableValue = NewType("VariableValue", str)
Interpolable = NewType("Interpolable", str)

# Tight braces around a bare identifier only, so a Go template — `{{.State.Running}}`,
# `{{range .items}}`, `{{ end }}` — passes through a command untouched.
_REFERENCE = re.compile(r"\{\{([A-Za-z_][A-Za-z0-9_]*)\}\}")


@dataclass(frozen=True, slots=True)
class Undefined:
    name: VariableName

    def __str__(self) -> str:
        return f"undefined variable {self.name}"


@dataclass(frozen=True, slots=True)
class Redeclared:
    name: VariableName

    def __str__(self) -> str:
        return f"variable {self.name} is already declared"


type DeclarationFailure = Undefined | Redeclared


# One note's bindings. Nothing carries them across a transclusion, so a note reads the
# same wherever it is included.
@dataclass(frozen=True, slots=True)
class Scope:
    bindings: Mapping[VariableName, VariableValue]

    @classmethod
    def empty(cls) -> Scope:
        return cls({})

    def declare(
        self, name: VariableName, value: VariableValue
    ) -> Scope | DeclarationFailure:
        if name in self.bindings:
            return Redeclared(name)
        expanded = self.expand(Interpolable(value))
        if isinstance(expanded, Undefined):
            return expanded
        return Scope({**self.bindings, name: VariableValue(expanded)})

    def expand(self, text: Interpolable) -> Interpolable | Undefined:
        missing = (
            Arr(_REFERENCE.findall(text))
            .map(VariableName)
            .filter(lambda name: name not in self.bindings)
            .to_list()
        )
        if missing:
            return Undefined(missing[0])
        return Interpolable(
            _REFERENCE.sub(lambda hit: self.bindings[VariableName(hit[1])], text)
        )
