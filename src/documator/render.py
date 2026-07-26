from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds

DEFAULT_TIMEOUT = TimeoutSeconds(10.0)


def render(
    input_dir: InputDir, output_dir: OutputDir, timeout: TimeoutSeconds
) -> ExitCode:
    return ExitCode(0)
