# documator

A documentation CLI. This readme is itself rendered from `templates/README.md` to `output/README.md` by the `documator render` command.

## Install

```
uv sync
```

## Usage

```
documator render INPUT_DIR OUTPUT_DIR [--watch] [--timeout SECONDS]
documator skills INPUT_DIR OUTPUT_DIR [--timeout SECONDS]
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
mkdir -p docs out
echo '# Title' > docs/index.md
uv run documator render docs out
```

This block is extracted verbatim and run by `test_readme.py`.
