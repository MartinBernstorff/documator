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

A path segment's prefix decides whether `skills` sees it:

- `.`-prefixed — invisible. Not walked, not emitted, not readable, never an error, so
  `.obsidian/` and `.DS_Store` can live in the tree.
- `_`-prefixed — inert but readable. Emits no skill, yet stays a valid
  `![[transclusion]]` target: the escape hatch for shared partials and drafts.

A bare `.md` compiles to a skill only when no `.` or `_` segment sits anywhere on its
path. Any other loose file is ignored rather than an error — the flat layout gives it no
destination — and logged: `warning` for an ordinary file, `info` for a `.`/`_` path. To
get a file bundled, move it into a `SKILL.md` folder.

`render` deliberately keeps its copy-everything walk and mirrors `.obsidian/` and
`.DS_Store` into its output. The two walks are not meant to agree.

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
