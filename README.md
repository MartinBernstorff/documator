# documator

A documentation CLI.

## Install

```
uv sync
```

## Usage

```
documator render INPUT_DIR OUTPUT_DIR [--watch] [--timeout SECONDS]
```

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
