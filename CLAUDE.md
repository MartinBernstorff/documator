# documator

A documentation CLI. Python 3.14, packaged with `uv` (src layout), tasks orchestrated by moonrepo.

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
- Pre-commit runs `moon ci` via lefthook. Run `lefthook install` after cloning.
