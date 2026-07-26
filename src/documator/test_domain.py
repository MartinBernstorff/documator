from pathlib import Path

import pytest
from pydantic import ValidationError

from documator.domain import ExistingPath, InputDir, OutputDir, TimeoutSeconds
from documator.tree_layout import TreeLayout, build_tree


def test_existing_path_accepts_existing_path(tmp_path: Path) -> None:
    assert ExistingPath(tmp_path).root == tmp_path


def test_existing_path_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ExistingPath(tmp_path / "nope")


def test_input_dir_rejects_file(tmp_path: Path) -> None:
    build_tree(tmp_path, TreeLayout("note.md |"))

    with pytest.raises(ValidationError):
        InputDir(tmp_path / "note.md")


def test_output_dir_accepts_existing_dir(tmp_path: Path) -> None:
    assert OutputDir(tmp_path).root == tmp_path


def test_output_dir_rejects_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        OutputDir(tmp_path / "nope")


def test_timeout_seconds_accepts_a_positive_number() -> None:
    assert TimeoutSeconds(2.5).root == 2.5


@pytest.mark.parametrize("seconds", [0.0, -1.0])
def test_timeout_seconds_rejects_non_positive(seconds: float) -> None:
    with pytest.raises(ValidationError):
        TimeoutSeconds(seconds)


def test_timeout_seconds_parses_a_numeric_string() -> None:
    assert TimeoutSeconds.model_validate("2.5").root == 2.5


def test_timeout_seconds_rejects_a_non_numeric_string() -> None:
    with pytest.raises(ValidationError):
        TimeoutSeconds.model_validate("soon")
