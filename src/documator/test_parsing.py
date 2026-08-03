from documator.execution import Command
from documator.parsing import (
    CommandWithOtherContent,
    DeclarationBlock,
    DeclarationWithoutValue,
    ExecutableBlock,
    Markdown,
    MultipleCommands,
    PassthroughBlock,
    StructuralErrorBlock,
    TransclusionBlock,
    UnterminatedFence,
    parse,
)
from documator.transclusion import Reference
from documator.variables import VariableName, VariableValue


def test_prose_only_document_is_a_single_passthrough_block() -> None:
    source = Markdown("""# Title

Some prose.
""")
    assert parse(source) == [PassthroughBlock(Markdown(source))]


def test_fence_with_single_bang_line_is_executable() -> None:
    source = Markdown("""```
!echo hi
```
""")
    assert parse(source) == [ExecutableBlock(Markdown(source), Command("echo hi"))]


def test_info_string_does_not_prevent_execution() -> None:
    source = Markdown("""```sh
!echo hi
```
""")
    assert parse(source) == [ExecutableBlock(Markdown(source), Command("echo hi"))]


def test_tilde_fence_is_executable() -> None:
    source = Markdown("""~~~
!echo hi
~~~
""")
    assert parse(source) == [ExecutableBlock(Markdown(source), Command("echo hi"))]


def test_surrounding_prose_is_preserved_around_an_executable_block() -> None:
    source = Markdown("""before

```
!echo hi
```

after
""")
    assert parse(source) == [
        PassthroughBlock(Markdown("before\n\n")),
        ExecutableBlock(Markdown("```\n!echo hi\n```\n"), Command("echo hi")),
        PassthroughBlock(Markdown("\nafter\n")),
    ]


def test_blank_lines_inside_an_executable_fence_are_tolerated() -> None:
    source = Markdown("""```

!echo hi

```
""")
    assert parse(source) == [ExecutableBlock(Markdown(source), Command("echo hi"))]


def test_double_bang_escapes_to_a_literal_bang_and_does_not_execute() -> None:
    source = Markdown("""```
!!echo hi
```
""")
    assert parse(source) == [
        PassthroughBlock(
            Markdown("""```
!echo hi
```
""")
        )
    ]


def test_non_executable_fence_passes_through_unchanged() -> None:
    source = Markdown("""```python
print('hi')
```
""")
    assert parse(source) == [PassthroughBlock(Markdown(source))]


def test_only_a_fence_at_column_zero_is_top_level() -> None:
    source = Markdown("""    ```
    !echo hi
    ```
""")
    assert parse(source) == [PassthroughBlock(Markdown(source))]


def test_escaped_bang_alongside_a_command_is_a_structural_error() -> None:
    source = Markdown("""```
!echo hi
!!echo literal
```
""")
    assert parse(source) == [
        StructuralErrorBlock(Markdown(source), CommandWithOtherContent)
    ]


def test_shorter_fence_does_not_close_a_longer_one() -> None:
    source = Markdown("""````
```
print('hi')
```
````
""")
    assert parse(source) == [PassthroughBlock(Markdown(source))]


def test_two_command_lines_are_a_structural_error() -> None:
    source = Markdown("""```
!echo one
!echo two
```
""")
    assert parse(source) == [StructuralErrorBlock(Markdown(source), MultipleCommands)]


def test_command_mixed_with_other_content_is_a_structural_error() -> None:
    source = Markdown("""```
!echo hi
print('hi')
```
""")
    assert parse(source) == [
        StructuralErrorBlock(Markdown(source), CommandWithOtherContent)
    ]


def test_unterminated_fence_is_a_structural_error() -> None:
    source = Markdown("""```
!echo hi
""")
    assert parse(source) == [StructuralErrorBlock(Markdown(source), UnterminatedFence)]


def test_multiple_executable_blocks_are_classified_independently() -> None:
    source = Markdown("""```
!echo one
```
text
```
!echo two
```
""")
    assert parse(source) == [
        ExecutableBlock(Markdown("```\n!echo one\n```\n"), Command("echo one")),
        PassthroughBlock(Markdown("text\n")),
        ExecutableBlock(Markdown("```\n!echo two\n```\n"), Command("echo two")),
    ]


def test_document_without_trailing_newline_round_trips() -> None:
    source = Markdown("prose")
    assert parse(source) == [PassthroughBlock(Markdown("prose"))]


def test_empty_document_yields_no_blocks() -> None:
    assert parse(Markdown("")) == []


def test_embed_in_prose_splits_into_a_transclusion_block() -> None:
    assert parse(Markdown("before ![[Note]] after\n")) == [
        PassthroughBlock(Markdown("before ")),
        TransclusionBlock(Reference("Note")),
        PassthroughBlock(Markdown(" after\n")),
    ]


def test_embed_spanning_a_line_break_is_not_a_transclusion() -> None:
    source = Markdown("![[Note\n]]\n")
    assert parse(source) == [PassthroughBlock(source)]


def test_var_line_is_a_declaration() -> None:
    source = Markdown("""```
!var dpy = uv run documator python
```
""")
    assert parse(source) == [
        DeclarationBlock(
            Markdown(source),
            VariableName("dpy"),
            VariableValue("uv run documator python"),
        )
    ]


def test_declaration_value_keeps_later_equals_signs() -> None:
    source = Markdown("""```
!var q = awk -F= '{print $2}'
```
""")
    assert parse(source) == [
        DeclarationBlock(
            Markdown(source), VariableName("q"), VariableValue("awk -F= '{print $2}'")
        )
    ]


def test_var_without_an_equals_sign_stays_a_command() -> None:
    source = Markdown("""```
!var --help
```
""")
    assert parse(source) == [ExecutableBlock(Markdown(source), Command("var --help"))]


def test_declaration_without_a_value_is_a_structural_error() -> None:
    source = Markdown("""```
!var dpy =
```
""")
    assert parse(source) == [
        StructuralErrorBlock(Markdown(source), DeclarationWithoutValue)
    ]


def test_two_declarations_in_one_fence_are_multiple_commands() -> None:
    source = Markdown("""```
!var a = one
!var b = two
```
""")
    assert parse(source) == [StructuralErrorBlock(Markdown(source), MultipleCommands)]


def test_declaration_beside_prose_is_command_with_other_content() -> None:
    source = Markdown("""```
!var a = one
prose
```
""")
    assert parse(source) == [
        StructuralErrorBlock(Markdown(source), CommandWithOtherContent)
    ]
