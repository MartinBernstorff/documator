from documator.execution import Command
from documator.parsing import (
    CommandWithOtherContent,
    ExecutableBlock,
    Markdown,
    MultipleCommands,
    PassthroughBlock,
    StructuralErrorBlock,
    UnterminatedFence,
    parse,
)


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
    assert parse(source) == [ExecutableBlock(Command("echo hi"))]


def test_info_string_does_not_prevent_execution() -> None:
    source = Markdown("""```sh
!echo hi
```
""")
    assert parse(source) == [ExecutableBlock(Command("echo hi"))]


def test_tilde_fence_is_executable() -> None:
    source = Markdown("""~~~
!echo hi
~~~
""")
    assert parse(source) == [ExecutableBlock(Command("echo hi"))]


def test_surrounding_prose_is_preserved_around_an_executable_block() -> None:
    source = Markdown("""before

```
!echo hi
```

after
""")
    assert parse(source) == [
        PassthroughBlock(Markdown("before\n\n")),
        ExecutableBlock(Command("echo hi")),
        PassthroughBlock(Markdown("\nafter\n")),
    ]


def test_blank_lines_inside_an_executable_fence_are_tolerated() -> None:
    source = Markdown("""```

!echo hi

```
""")
    assert parse(source) == [ExecutableBlock(Command("echo hi"))]


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
        ExecutableBlock(Command("echo one")),
        PassthroughBlock(Markdown("text\n")),
        ExecutableBlock(Command("echo two")),
    ]


def test_document_without_trailing_newline_round_trips() -> None:
    source = Markdown("prose")
    assert parse(source) == [PassthroughBlock(Markdown("prose"))]


def test_empty_document_yields_no_blocks() -> None:
    assert parse(Markdown("")) == []
