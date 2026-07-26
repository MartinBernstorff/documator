import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="documator")
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    parser.parse_args(argv)
    print("Hello from documator!")
    return 0
