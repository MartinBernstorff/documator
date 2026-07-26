from documator.execution import Command
from documator.parsing import (
    ExecutableBlock,
    Markdown,
    PassthroughBlock,
    StructuralError,
    StructuralErrorBlock,
    parse,
)


def test_prose_only_document_is_a_single_passthrough_block() -> None:
    source = Markdown("# Title\n\nSome prose.\n")
    assert parse(source) == [PassthroughBlock(Markdown(source))]


def test_fence_with_single_bang_line_is_executable() -> None:
    source = Markdown("```\n!echo hi\n```\n")
    assert parse(source) == [ExecutableBlock(Command("echo hi"))]


def test_info_string_does_not_prevent_execution() -> None:
    source = Markdown("```sh\n!echo hi\n```\n")
    assert parse(source) == [ExecutableBlock(Command("echo hi"))]


def test_tilde_fence_is_executable() -> None:
    source = Markdown("~~~\n!echo hi\n~~~\n")
    assert parse(source) == [ExecutableBlock(Command("echo hi"))]


def test_surrounding_prose_is_preserved_around_an_executable_block() -> None:
    source = Markdown("before\n\n```\n!echo hi\n```\n\nafter\n")
    assert parse(source) == [
        PassthroughBlock(Markdown("before\n\n")),
        ExecutableBlock(Command("echo hi")),
        PassthroughBlock(Markdown("\nafter\n")),
    ]


def test_blank_lines_inside_an_executable_fence_are_tolerated() -> None:
    source = Markdown("```\n\n!echo hi\n\n```\n")
    assert parse(source) == [ExecutableBlock(Command("echo hi"))]


def test_double_bang_escapes_to_a_literal_bang_and_does_not_execute() -> None:
    source = Markdown("```\n!!echo hi\n```\n")
    assert parse(source) == [PassthroughBlock(Markdown("```\n!echo hi\n```\n"))]


def test_non_executable_fence_passes_through_unchanged() -> None:
    source = Markdown("```python\nprint('hi')\n```\n")
    assert parse(source) == [PassthroughBlock(Markdown(source))]


def test_indented_fence_is_not_top_level_and_passes_through() -> None:
    source = Markdown("    ```\n    !echo hi\n    ```\n")
    assert parse(source) == [PassthroughBlock(Markdown(source))]


def test_shorter_fence_does_not_close_a_longer_one() -> None:
    source = Markdown("````\n```\nprint('hi')\n```\n````\n")
    assert parse(source) == [PassthroughBlock(Markdown(source))]


def test_two_command_lines_are_a_structural_error() -> None:
    source = Markdown("```\n!echo one\n!echo two\n```\n")
    assert parse(source) == [
        StructuralErrorBlock(Markdown(source), StructuralError.MULTIPLE_COMMANDS)
    ]


def test_command_mixed_with_other_content_is_a_structural_error() -> None:
    source = Markdown("```\n!echo hi\nprint('hi')\n```\n")
    assert parse(source) == [
        StructuralErrorBlock(
            Markdown(source), StructuralError.COMMAND_WITH_OTHER_CONTENT
        )
    ]


def test_unterminated_fence_is_a_structural_error() -> None:
    source = Markdown("```\n!echo hi\n")
    assert parse(source) == [
        StructuralErrorBlock(Markdown(source), StructuralError.UNTERMINATED_FENCE)
    ]


def test_multiple_executable_blocks_are_classified_independently() -> None:
    source = Markdown("```\n!echo one\n```\ntext\n```\n!echo two\n```\n")
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
