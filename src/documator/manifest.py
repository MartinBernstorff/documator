import json
from pathlib import Path
from typing import NewType

from pydantic import RootModel, ValidationError

from documator.domain import OutputDir, RelativePath

TemplatePath = NewType("TemplatePath", RelativePath)
DestinationPath = NewType("DestinationPath", RelativePath)


# Ownership is recorded, never inferred: a file the manifest does not name is somebody
# else's, so the run leaves it where it is rather than pruning or overwriting it.
class Manifest(RootModel[dict[TemplatePath, DestinationPath]]):
    def destinations(self) -> set[DestinationPath]:
        return set(self.root.values())


def manifest_path(output_dir: OutputDir) -> Path:
    return output_dir.root / ".documator-manifest.json"


# The manifest is the run's own bookkeeping, so no artifact may land on top of it.
def reserved() -> DestinationPath:
    return DestinationPath(RelativePath(Path(".documator-manifest.json")))


# An unreadable manifest reads as "nothing is tracked", which deletes nothing.
def read_manifest(output_dir: OutputDir) -> Manifest:
    path = manifest_path(output_dir)
    if not path.is_file():
        return Manifest({})
    try:
        return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError, UnicodeDecodeError:
        return Manifest({})


def write_manifest(output_dir: OutputDir, manifest: Manifest) -> None:
    payload = {
        str(template): str(destination)
        for template, destination in manifest.root.items()
    }
    # Swapped into place in one step, because a manifest truncated halfway reads as
    # "nothing is tracked", which disowns every file the run has already written.
    scratch = manifest_path(output_dir).with_suffix(".tmp")
    scratch.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    scratch.replace(manifest_path(output_dir))
