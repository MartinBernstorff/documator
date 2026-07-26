# documator

A documentation CLI.

## Install

```
uv sync
```

## Usage

```
documator render INPUT_DIR OUTPUT_DIR [--watch] [--timeout SECONDS]
documator skills INPUT_DIR OUTPUT_DIR [--timeout SECONDS]
```

`render` mirrors the input tree. `skills` compiles the same templates into the flat
`<skill-name>/SKILL.md` layout Claude's skill loader expects: nesting in the input tree
is organisational only, the filename stem becomes the skill name, and the frontmatter is
generated — any keys the template declares pass through, and a declared `description`
wins over the name-derived placeholder.

For the current options, run:

```
uv run documator render --help
```

### Try it

```sh
mkdir -p docs out
echo '# Title' > docs/index.md
uv run documator render docs out
```

This block is extracted verbatim and run by `test_readme.py`.

## Development

See [CLAUDE.md](CLAUDE.md). Tasks run through moon:

```
moon run documator:test
moon ci
```
