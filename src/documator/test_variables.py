from inline_snapshot import snapshot

from documator.variables import (
    Interpolable,
    Redeclared,
    Scope,
    Undefined,
    VariableName,
    VariableValue,
)


def test_reference_expands_to_its_value() -> None:
    scope = Scope.empty().declare(
        VariableName("dpy"), VariableValue("uv run documator python")
    )
    assert isinstance(scope, Scope)
    assert scope.expand(Interpolable("{{dpy}} list")) == snapshot(
        "uv run documator python list"
    )


def test_reference_concatenates_without_a_separator() -> None:
    scope = Scope.empty().declare(VariableName("bin"), VariableValue("/usr/bin"))
    assert isinstance(scope, Scope)
    assert scope.expand(Interpolable("{{bin}}/ls")) == snapshot("/usr/bin/ls")


def test_declaration_expands_an_earlier_variable() -> None:
    base = Scope.empty().declare(
        VariableName("base"), VariableValue("uv run documator")
    )
    assert isinstance(base, Scope)
    scope = base.declare(VariableName("dpy"), VariableValue("{{base}} python"))
    assert isinstance(scope, Scope)
    assert scope.expand(Interpolable("{{dpy}}")) == snapshot("uv run documator python")


def test_undefined_reference_is_reported() -> None:
    failure = Scope.empty().expand(Interpolable("echo {{dyp}}"))
    assert isinstance(failure, Undefined)
    assert str(failure) == snapshot("undefined variable dyp")


def test_undefined_reference_in_a_declaration_is_reported() -> None:
    failure = Scope.empty().declare(
        VariableName("dpy"), VariableValue("{{missing}} python")
    )
    assert isinstance(failure, Undefined)
    assert str(failure) == snapshot("undefined variable missing")


def test_redeclaring_a_name_is_reported() -> None:
    scope = Scope.empty().declare(VariableName("dpy"), VariableValue("one"))
    assert isinstance(scope, Scope)
    failure = scope.declare(VariableName("dpy"), VariableValue("two"))
    assert isinstance(failure, Redeclared)
    assert str(failure) == snapshot("variable dpy is already declared")


def test_go_template_passes_through_untouched() -> None:
    scope = Scope.empty().declare(VariableName("name"), VariableValue("substituted"))
    assert isinstance(scope, Scope)
    template = Interpolable(
        "docker inspect -f '{{.Name}}{{range .items}}{{ end }}{{ name }}'"
    )
    assert scope.expand(template) == snapshot(
        "docker inspect -f '{{.Name}}{{range .items}}{{ end }}{{ name }}'"
    )


def test_shell_variable_is_left_to_the_shell() -> None:
    assert Scope.empty().expand(Interpolable("echo $HOME $(pwd) $1")) == snapshot(
        "echo $HOME $(pwd) $1"
    )
