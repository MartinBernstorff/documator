import json
import logging
from pathlib import Path
from typing import NewType

from pydantic import RootModel, ValidationError

from documator.domain import OutputDir, RelativePath

log = logging.getLogger("documator")

# The two files documator keeps for itself in the output tree.
BookkeepingPath = NewType("BookkeepingPath", Path)

TemplatePath = NewType("TemplatePath", RelativePath)
DestinationPath = NewType("DestinationPath", RelativePath)


# Ownership is recorded, never inferred: a file the manifest does not name is somebody
# else's, so the run leaves it where it is rather than pruning or overwriting it.
class Manifest(RootModel[dict[TemplatePath, DestinationPath]]):
    def destinations(self) -> set[DestinationPath]:
        return set(self.root.values())


def manifest_path(output_dir: OutputDir) -> BookkeepingPath:
    return BookkeepingPath(output_dir.root / ".documator-manifest.json")


# What a run means to write, kept apart from what it has written: a claim is enough to
# overwrite a path, never enough to delete one. Only the manifest — written after the
# fact — grants that, so a claim the run never reached cannot cost anybody a file.
def claims_path(output_dir: OutputDir) -> BookkeepingPath:
    return BookkeepingPath(output_dir.root / ".documator-claims.json")


# The run's own bookkeeping, so no artifact may land on top of either file.
def reserved() -> set[DestinationPath]:
    return {
        DestinationPath(RelativePath(Path(".documator-manifest.json"))),
        DestinationPath(RelativePath(Path(".documator-claims.json"))),
    }


# An unreadable manifest reads as "nothing is tracked", which deletes nothing — but it
# also disowns every file the run before it wrote, and the next run refuses each one as
# somebody else's. Said out loud, because that failure otherwise surfaces a run later
# with nothing pointing back at its cause.
def read_manifest(output_dir: OutputDir) -> Manifest:
    return _read(manifest_path(output_dir))


def read_claims(output_dir: OutputDir) -> Manifest:
    return _read(claims_path(output_dir))


def _read(path: BookkeepingPath) -> Manifest:
    if not path.is_file():
        return Manifest({})
    try:
        return Manifest.model_validate_json(path.read_text(encoding="utf-8"))
    except ValidationError, UnicodeDecodeError:
        log.warning(
            "%s is unreadable: nothing counts as documator's own until a run reclaims"
            " it with --adopt",
            path.name,
        )
        return Manifest({})


def write_manifest(output_dir: OutputDir, manifest: Manifest) -> None:
    _write(manifest_path(output_dir), manifest)


def write_claims(output_dir: OutputDir, claims: Manifest) -> None:
    _write(claims_path(output_dir), claims)


# A run that reached its own end has a manifest saying what it wrote, so its claims have
# nothing left to say: the ones that outlive a run are a crash to recover from.
def clear_claims(output_dir: OutputDir) -> None:
    claims_path(output_dir).unlink(missing_ok=True)


def _write(path: BookkeepingPath, manifest: Manifest) -> None:
    payload = {
        str(template): str(destination)
        for template, destination in manifest.root.items()
    }
    # Swapped into place in one step, because a file truncated halfway reads as "nothing
    # is tracked", which disowns everything the run has already written.
    scratch = path.with_suffix(".tmp")
    scratch.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    scratch.replace(path)
