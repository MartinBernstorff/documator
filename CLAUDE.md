# documator

A documentation CLI. Python 3.14, packaged with `uv` (src layout), tasks orchestrated by moonrepo.

We use GitHub as an issue tracker.

## Running tasks

Always run tasks through **moon**, never the tool directly. This runs dependencies and caches aggressively.

| Task | Command | Tool |
| --- | --- | --- |
| Tests | `moon run documator:test` | pytest |
| Lint | `moon run documator:lint` | ruff |
| Lint (fix) | `moon run documator:lint-fix` | ruff (`--fix`) |
| Format | `moon run documator:format` | ruff (`--check`) |
| Format (fix) | `moon run documator:format-fix` | ruff |
| Type-check | `moon run documator:typecheck` | pyrefly (`preset = all`) |
| Modularity | `moon run documator:modularity` | tach |
| Record snapshots | `moon run documator:snapshot` | pytest + inline-snapshot |

Run everything at once with `moon ci` — the same affected-only pass CI and the pre-commit hook run. Add `--force` to bypass affected detection and the cache and run every task.

`snapshot` sits outside both, because it **rewrites test sources**. Run it by hand when a `snapshot()` is empty or its expected value changed, then read the diff before committing. It exits non-zero whenever it writes a value.

## Conventions

- Never invoke `pytest`/`ruff`/`pyrefly`/`tach` directly — go through `moon run`.
- When adding a new tool, wire it as a moon task **and** add it to the pre-commit hook (`lefthook.yml`). If the tool can auto-fix, run the fixing variant in the hook rather than the checking one.
- Dependencies are managed with `uv` (`uv add`, `uv add --dev`). The lockfile is `uv.lock`.
- Tool settings live in each tool's own config file (`ruff.toml`, `pyrefly.toml`, `pytest.toml`, `tach.toml`), never in `pyproject.toml`.
- Pre-commit runs the `fix` tasks and then `moon ci` via lefthook, which is a `uv` dev dependency. `.conductor/settings.toml` installs the hooks on workspace creation (`scripts.setup`); outside Conductor, run `uv sync && uv run lefthook install` after cloning.

## Code conventions

- **Never allow primitives as function parameters.** Wrap them in a `NewType` or a pydantic `RootModel` so each value carries its domain meaning — e.g. `UserId = NewType("UserId", int)` rather than a bare `int`.
- **No named constants.** Inline the literal at its point of use. If a value carries domain meaning, give it a type (`NewType`, `RootModel`, or an `Enum` member) rather than a module-level `NAME = value`.
- **Do not maintain a `tests` folder.** Place tests next to the code they test, as `test_<module>.py`.
- **Do not use fixtures or shared constants to set up test data.** Inline the setup in each test so it reads independently.
- **Never maintain a `__all__` list.** Instead, re-export with `from .module import *` in the package's `__init__.py`.
- **Prefer iterators over manual for-loops.** Use `iterpy`: `Arr([1, 2, 3]).map(lambda x: x + 1).filter(lambda x: x > 2).to_list()`.
- **Avoid constants.** Before introducing one, ask whether it should be an argument supplied by the caller instead.
- Commits are automatically validated through pre-commit hooks (lefthook → `moon ci`).

## Testing conventions

- Co-locate tests with implementation as `test_<module>.py`. No `tests` folder.
- Test against the real implementation unless it is too slow or has real-world consequences.
- Avoid spies and mocks. When you must substitute, use a fake — typically a fast in-memory implementation.
- If a fake can drift from the real implementation, add a contract test that runs both against the same expectations.
- Assert expected output with `inline_snapshot.snapshot(...)` rather than a hand-written literal, and record it with `moon run documator:snapshot`. Prefer one whole-value snapshot over several substring assertions. Do not snapshot a value whose point is that something is *absent*, or one carrying invisible characters — assert that directly instead.
