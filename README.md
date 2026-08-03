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

A template takes one of two forms. A bare `foo.md` becomes `foo/SKILL.md`. A folder
holding a `SKILL.md` becomes `<folder-name>/SKILL.md`, and the folder's whole subtree is
bundled alongside it with its internal structure preserved — flattening applies only to
the path *above* the folder, so `guides/plan/references/spec.pdf` lands at
`plan/references/spec.pdf`. Bundled files follow `render`'s extension rule: `.md` gets
the full pipeline, everything else is copied verbatim. Only `SKILL.md` gets generated
frontmatter; a bundled `.md` is a document, not a skill.

Such a folder is a hard leaf, so skills cannot nest: a deeper `SKILL.md` is bundled as an
ordinary file rather than compiling to a second skill. That leaves room for a skill that
ships an example skill as a reference file, and each bundled file is logged so the
swallowing stays visible in run output.

A path segment's prefix decides whether `skills` sees it:

- `.`-prefixed — invisible. Not walked, not emitted, not readable, never an error, so
  `.obsidian/` and `.DS_Store` can live in the tree.
- `_`-prefixed — inert but readable. Emits no skill, yet stays a valid
  `![[transclusion]]` target: the escape hatch for shared partials and drafts.

A bare `.md` compiles to a skill only when no `.` or `_` segment sits anywhere on its
path. Any other loose file is ignored rather than an error — the flat layout gives it no
destination — and logged: `warning` for an ordinary file, `info` for a `.`/`_` path. To
get a file bundled, move it into a `SKILL.md` folder.

Malformed input compiles what compiles. A **structural** failure skips only its own
skill — every other skill in the run still compiles, the failing skill's
previously-compiled copy is pruned, and the reasons aggregate into a
`documator-errors.md` at the output root, which itself disappears on the next clean run.
Any structural failure exits 1; 2 stays reserved for the run being impossible. The
class is whatever is decidable from the tree and the template source, before any
`!command` block runs:

- a stem that is not already `^[a-z0-9]+(-[a-z0-9]+)*$` and ≤64 chars — names are
  validated, never normalised, because renaming a public identifier is a breaking change
  at a distance;
- a name claimed twice. One global namespace spans both template forms, so `foo.md`
  beside `foo/SKILL.md` collides; neither side is emitted and the error names both paths;
- an empty template — frontmatter and whitespace stripped leaves nothing. Measured on the
  source, so an empty `SKILL.md` fails even when its folder bundles files, and a body that
  merely *renders* empty stays a content failure;
- a `name` key in template frontmatter, even one that matches the derived name, or an
  explicitly empty `description:`;
- a template that cannot be read or decoded.

`render` deliberately keeps its copy-everything walk and mirrors `.obsidian/` and
`.DS_Store` into its output. The two walks are not meant to agree.

## Commands

A `!`-prefixed line inside a fence at column zero is a command: the whole fence is
replaced by a fenced block holding the command's output.

A command also works inline, in a code span, so a value can sit in the middle of a
sentence — `` `!git rev-parse --short HEAD` `` becomes `` `a1b2c3d` ``. The span's
delimiter may be any number of backticks, closed by a run of the same length on the same
line, so a command containing a backtick is written with more of them. Everything after
the `!` is the command; there is no info string to skip.

Inline output is a code span too, widened past any backticks it contains. A code span
cannot hold a line break, so output that spans several lines is promoted to an ordinary
fence on its own line and the sentence resumes after it — write the fenced form directly
when that is what you want. Output that is empty becomes
`` `[documator: no output]` `` rather than an invisible hole, and a command that fails
or times out carries its marker inside the backticks.

`{{name}}` references expand in an inline command exactly as in a fenced one, against the
same file-scoped bindings, so a `!var` declared in a fence is usable mid-sentence.
An undefined reference hands the span's source back followed by its marker, keeping the
failure on one line. A declaration itself has no inline form: `` `!var a = b` `` is a
command named `var`, and fails as one.

`!!` escapes in both forms, so `` `!!important` `` renders as `` `!important` ``. A span
holding nothing but `!` is left alone, and a leading `![[` stays an embed rather than
becoming a command.

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
