# documator

A documentation CLI. This readme is itself rendered from `templates/README.md` into the repository root by the `documator render` command.

## Install

```
uv sync
```

## Usage

```
documator render INPUT_DIR OUTPUT_DIR [--watch] [--timeout SECONDS]
documator skills INPUT_DIR OUTPUT_DIR [--watch] [--timeout SECONDS]
```

`render` mirrors the input tree. 

```
!uv run documator render --help
```

`skills` compiles the same templates into the flat `<skill-name>/SKILL.md` layout Claude's skill loader expects: nesting in the input tree is organisational only, the filename stem becomes the skill name, and the frontmatter is generated — any keys the template declares pass through, and a declared `description` wins over the name-derived placeholder.

An example tree might look like:

```
my-templates/
├── foo.md
├── bar/
│   └── SKILL.md
├── _hidden.md
```

and would result in:

```
.skills/
├── foo/
│   └── SKILL.md
├── bar/
│   └── SKILL.md
```

```
!uv run documator skills --help
```

### Try it

```sh
mkdir -p docs/guides/plan/references out compiled
printf '# Review\n\nRead the diff before the description.\n' > docs/guides/review.md
printf -- '---\ndescription: Plan a change\n---\n# Plan\n' > docs/guides/plan/SKILL.md
echo '# Spec' > docs/guides/plan/references/spec.md
uv run documator render docs out
uv run documator skills docs compiled
```

Two layouts over one tree. `render` mirrors it into `out/`, so `guides/review.md` stays `guides/review.md`. `skills` flattens it into `compiled/`: the bare `guides/review.md` becomes `review/SKILL.md` with a name-derived `description`, and the `guides/plan/` folder becomes `plan/SKILL.md` — carrying its declared `description` through — with `references/spec.md` bundled beside it as `plan/references/spec.md`.

This block is extracted verbatim and run by `test_readme.py`.
