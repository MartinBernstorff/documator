import logging
from pathlib import Path

import pytest

from documator.domain import InputDir, OutputDir
from documator.render import DEFAULT_TIMEOUT, MANIFEST_NAME, render


def _render(input_dir: Path, output_dir: Path) -> int:
    return render(InputDir(input_dir), OutputDir(output_dir), DEFAULT_TIMEOUT)


def _write_tree(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return root


def _mirrored(output_dir: Path) -> set[str]:
    return {
        p.relative_to(output_dir).as_posix()
        for p in output_dir.rglob("*")
        if p.is_file() and p.name != MANIFEST_NAME
    }


def test_mirrors_input_tree_verbatim(tmp_path: Path) -> None:
    input_dir = _write_tree(
        tmp_path / "in",
        {
            "note.md": "# Note\n",
            "sub/nested.md": "nested\n",
            "assets/data.csv": "a,b\n1,2\n",
        },
    )
    output_dir = tmp_path / "out"

    assert _render(input_dir, output_dir) == 0
    assert _mirrored(output_dir) == {"note.md", "sub/nested.md", "assets/data.csv"}
    assert (output_dir / "note.md").read_text() == "# Note\n"
    assert (output_dir / "sub/nested.md").read_text() == "nested\n"
    assert (output_dir / "assets/data.csv").read_text() == "a,b\n1,2\n"


def test_renders_files_in_sorted_path_order(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    input_dir = _write_tree(
        tmp_path / "in", {"b.md": "b\n", "a.md": "a\n", "sub/c.md": "c\n"}
    )

    with caplog.at_level(logging.INFO, logger="documator"):
        assert _render(input_dir, tmp_path / "out") == 0

    logged = [r.message for r in caplog.records]
    assert logged.index("rendering a.md") < logged.index("rendering b.md")
    assert logged.index("rendering b.md") < logged.index("rendering sub/c.md")


def test_prunes_paths_produced_by_an_earlier_run(tmp_path: Path) -> None:
    input_dir = _write_tree(
        tmp_path / "in", {"kept.md": "kept\n", "gone/deep/dropped.md": "dropped\n"}
    )
    output_dir = tmp_path / "out"
    assert _render(input_dir, output_dir) == 0

    (input_dir / "gone/deep/dropped.md").unlink()
    (input_dir / "added.md").write_text("added\n")

    assert _render(input_dir, output_dir) == 0
    assert _mirrored(output_dir) == {"kept.md", "added.md"}
    assert not (output_dir / "gone").exists()


def test_does_not_prune_files_it_never_produced(tmp_path: Path) -> None:
    input_dir = _write_tree(tmp_path / "in", {"note.md": "note\n"})
    output_dir = _write_tree(
        tmp_path / "out",
        {"handwritten.md": "mine\n", ".obsidian/app.json": "{}\n"},
    )

    assert _render(input_dir, output_dir) == 0
    assert (output_dir / "handwritten.md").read_text() == "mine\n"
    assert (output_dir / ".obsidian/app.json").read_text() == "{}\n"


def test_rendering_twice_is_idempotent(tmp_path: Path) -> None:
    input_dir = _write_tree(tmp_path / "in", {"note.md": "note\n", "sub/a.md": "a\n"})
    output_dir = tmp_path / "out"

    assert _render(input_dir, output_dir) == 0
    first = _mirrored(output_dir)
    assert _render(input_dir, output_dir) == 0
    assert _mirrored(output_dir) == first


def test_pruning_does_not_wipe_the_output_directory_itself(tmp_path: Path) -> None:
    input_dir = _write_tree(tmp_path / "in", {"note.md": "note\n"})
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    assert _render(input_dir, output_dir) == 0
    assert output_dir.is_dir()


def test_identical_input_and_output_is_operational_error(tmp_path: Path) -> None:
    shared = _write_tree(tmp_path / "vault", {"note.md": "note\n"})

    assert _render(shared, shared) == 2
    assert (shared / "note.md").read_text() == "note\n"


def test_output_nested_in_input_is_operational_error(tmp_path: Path) -> None:
    input_dir = _write_tree(tmp_path / "in", {"note.md": "note\n"})

    assert _render(input_dir, input_dir / "out") == 2
    assert not (input_dir / "out").exists()


def test_input_nested_in_output_is_operational_error(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    input_dir = _write_tree(output_dir / "in", {"note.md": "note\n"})

    assert _render(input_dir, output_dir) == 2


def test_missing_input_directory_is_operational_error(tmp_path: Path) -> None:
    assert _render(tmp_path / "absent", tmp_path / "out") == 2
    assert not (tmp_path / "out").exists()


def test_output_path_that_is_a_file_is_operational_error(tmp_path: Path) -> None:
    input_dir = _write_tree(tmp_path / "in", {"note.md": "note\n"})
    output_file = tmp_path / "out.md"
    output_file.write_text("not a directory\n")

    assert _render(input_dir, output_file) == 2
    assert output_file.read_text() == "not a directory\n"


def test_empty_input_produces_empty_output(tmp_path: Path) -> None:
    input_dir = tmp_path / "in"
    input_dir.mkdir()
    output_dir = tmp_path / "out"

    assert _render(input_dir, output_dir) == 0
    assert _mirrored(output_dir) == set()
