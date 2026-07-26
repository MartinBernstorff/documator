from pathlib import Path

import pytest
from pydantic import ValidationError

from documator.domain import ExistingPath, InputDir, OutputDir


def test_existing_path_accepts_existing_path(tmp_path: Path) -> None:
    assert ExistingPath(tmp_path).root == tmp_path


def test_existing_path_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        ExistingPath(tmp_path / "nope")


def test_input_dir_rejects_missing_path(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        InputDir(tmp_path / "nope")


def test_output_dir_accepts_missing_path(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    assert OutputDir(missing).root == missing
