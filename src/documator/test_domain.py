from pathlib import Path

import pytest
from pydantic import ValidationError

from documator.domain import ExistingPath, InputDir, OutputDir


def test_existing_path_accepts_existing_path(tmp_path: Path) -> None:
    assert ExistingPath(tmp_path).root == tmp_path


def test_existing_path_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ExistingPath(tmp_path / "nope")


def test_input_dir_rejects_file(tmp_path: Path) -> None:
    note = tmp_path / "note.md"
    note.touch()
    with pytest.raises(ValidationError):
        InputDir(note)


def test_output_dir_accepts_existing_dir(tmp_path: Path) -> None:
    assert OutputDir(tmp_path).root == tmp_path


def test_output_dir_rejects_missing_dir(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        OutputDir(tmp_path / "nope")
