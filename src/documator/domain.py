from pathlib import Path
from typing import NewType

InputDir = NewType("InputDir", Path)
OutputDir = NewType("OutputDir", Path)
TimeoutSeconds = NewType("TimeoutSeconds", float)
ExitCode = NewType("ExitCode", int)
