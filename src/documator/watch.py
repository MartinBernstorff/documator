from documator.domain import ExitCode, InputDir, OutputDir, TimeoutSeconds


def watch(
    input_dir: InputDir, output_dir: OutputDir, timeout: TimeoutSeconds
) -> ExitCode:
    raise NotImplementedError
