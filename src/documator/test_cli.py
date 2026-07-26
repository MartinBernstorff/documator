from documator.cli import main


def test_main_returns_zero() -> None:
    assert main([]) == 0


def test_version_exits_cleanly() -> None:
    assert main(["--version"]) == 0
