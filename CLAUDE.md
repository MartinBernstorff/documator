# documator

A documentation CLI. Python 3.14, packaged with `uv` (src layout), tasks orchestrated by moonrepo.

We use GitHub as an issue tracker.

## Running tasks

Always run tasks through **moon**, never the tool directly. This runs dependencies and caches aggressively.

| Task | Command | Tool |
| --- | --- | --- |
| Tests | `moon run documator:test` | pytest |
| Lint | `moon run documator:lint` | ruff |
| Format | `moon run documator:format` | ruff (`--check`) |
| Type-check | `moon run documator:typecheck` | pyrefly (`preset = all`) |
| Modularity | `moon run documator:modularity` | tach |

Run everything at once with `moon check --all`, or `moon ci --base main` for the full affected-only CI pass.

## Conventions

- Never invoke `pytest`/`ruff`/`pyrefly`/`tach` directly — go through `moon run`.
- When adding a new tool, wire it as a moon task **and** add it to the pre-commit hook (`lefthook.yml`). If the tool can auto-fix, run the fixing variant in the hook rather than the checking one.
- Dependencies are managed with `uv` (`uv add`, `uv add --dev`). The lockfile is `uv.lock`.
- Tool settings live in each tool's own config file (`ruff.toml`, `pyrefly.toml`, `pytest.toml`, `tach.toml`), never in `pyproject.toml`.
- Pre-commit runs `moon ci` via lefthook, which is a `uv` dev dependency. `.conductor/settings.toml` installs the hooks on workspace creation (`scripts.setup`); outside Conductor, run `uv sync && uv run lefthook install` after cloning.

## Code conventions

- **Never allow primitives as function parameters.** Wrap them in a `NewType` or a pydantic `RootModel` so each value carries its domain meaning — e.g. `UserId = NewType("UserId", int)` rather than a bare `int`.
- **No named constants.** Inline the literal at its point of use. If a value carries domain meaning, give it a type (`NewType`, `RootModel`, or an `Enum` member) rather than a module-level `NAME = value`.
- **Do not maintain a `tests` folder.** Place tests next to the code they test, as `test_<module>.py`.
- **Do not use fixtures or shared constants to set up test data.** Inline the setup in each test so it reads independently.
- **Never maintain a `__all__` list.** Instead, re-export with `from .module import *` in the package's `__init__.py`.
- **Prefer iterators over manual for-loops.** Use `iterpy`: `Arr([1, 2, 3]).map(lambda x: x + 1).filter(lambda x: x > 2).to_list()`.
- Commits are automatically validated through pre-commit hooks (lefthook → `moon ci`).
