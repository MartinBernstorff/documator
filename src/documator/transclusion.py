import re
from dataclasses import dataclass
from pathlib import Path
from typing import NewType, override

from iterpy import Arr
from pydantic import RootModel, field_validator
from pydantic_core import PydanticCustomError

from documator.domain import ExistingFile, InputDir, WorkingDir

Reference = NewType("Reference", str)
CanonicalName = NewType("CanonicalName", tuple[str, ...])


# Held relative to the vault root, so a reference, a cycle chain and an ambiguity
# report all read the same no matter where the vault itself lives.
class VaultPath(RootModel[Path]):
    @field_validator("root")
    @classmethod
    def _path_is_relative(cls, value: Path) -> Path:
        if value.is_absolute():
            raise PydanticCustomError(
                "path_not_relative",
                "path is not relative to the vault: {path}",
                {"path": value},
            )
        return value

    @override
    def __str__(self) -> str:
        return str(self.root)


class NotePath(VaultPath): ...


class AttachmentPath(VaultPath): ...


@dataclass(frozen=True, slots=True)
class NoMatch:
    reference: Reference

    def __str__(self) -> str:
        return f'no note matches transclusion "{self.reference}"'


@dataclass(frozen=True, slots=True)
class Ambiguous:
    reference: Reference
    candidates: tuple[NotePath, ...]

    def __str__(self) -> str:
        named = ", ".join(str(candidate) for candidate in self.candidates)
        return f'transclusion "{self.reference}" matches {named}'


@dataclass(frozen=True, slots=True)
class FragmentUnsupported:
    reference: Reference

    def __str__(self) -> str:
        return f'transclusion "{self.reference}" names a fragment, which is unsupported'


@dataclass(frozen=True, slots=True)
class Cycle:
    chain: tuple[NotePath, ...]

    def __str__(self) -> str:
        return "transclusion cycle: " + " -> ".join(str(note) for note in self.chain)


# An `![[image.png]]` embed is Obsidian's, not ours, so it goes back out as it came in.
@dataclass(frozen=True, slots=True)
class NonNoteEmbed:
    reference: Reference

    def __str__(self) -> str:
        return f"![[{self.reference}]]"


type TransclusionFailure = NoMatch | Ambiguous | FragmentUnsupported | Cycle
type Resolution = NotePath | NonNoteEmbed | TransclusionFailure


@dataclass(frozen=True, slots=True)
class Vault:
    root: Path
    notes: tuple[NotePath, ...]
    attachments: tuple[AttachmentPath, ...]

    # Indexing and reading are separate steps, so joining is where a note that left
    # the vault mid-run stops being a guess.
    def source(self, note: NotePath) -> ExistingFile:
        return ExistingFile(self.root / note.root)

    def read(self, note: NotePath) -> str:
        return self.source(note).root.read_text(encoding="utf-8")

    def beside(self, note: NotePath) -> WorkingDir:
        return WorkingDir(self.source(note).root.parent)


def index(input_dir: InputDir) -> Vault:
    files = (
        Arr(input_dir.root.rglob("*"))
        .filter(lambda path: path.is_file())
        .map(lambda path: path.relative_to(input_dir.root))
    )
    markdown = files.filter(lambda path: path.suffix.lower() == ".md")
    other = files.filter(lambda path: path.suffix.lower() != ".md")
    return Vault(
        input_dir.root,
        tuple(sorted((NotePath(path) for path in markdown), key=str)),
        tuple(sorted((AttachmentPath(path) for path in other), key=str)),
    )


def resolve(
    vault: Vault, reference: Reference, entered: tuple[NotePath, ...]
) -> Resolution:
    if "#" in reference:
        return FragmentUnsupported(reference)
    wanted = _canonical(reference)
    if not wanted:
        return NoMatch(reference)
    candidates = Arr(vault.notes).filter(lambda note: _matches(note, wanted)).to_list()
    if len(candidates) > 1:
        return Ambiguous(reference, tuple(candidates))
    if len(candidates) == 1:
        note = candidates[0]
        return Cycle((*entered, note)) if note in entered else note
    if _attached(vault, reference):
        return NonNoteEmbed(reference)
    return NoMatch(reference)


# Only an attachment that really exists earns a passthrough; otherwise a dotted note
# name would silently swallow the reference instead of reporting the miss.
def _attached(vault: Vault, reference: Reference) -> bool:
    wanted = _segments(reference)
    return Arr(vault.attachments).any(
        lambda path: _segments(Reference(str(path)))[-len(wanted) :] == wanted
    )


def _matches(note: NotePath, wanted: CanonicalName) -> bool:
    return _canonical(Reference(str(note)))[-len(wanted) :] == wanted


def _canonical(reference: Reference) -> CanonicalName:
    return _segments(Reference(re.sub(r"\.md$", "", reference, flags=re.IGNORECASE)))


def _segments(reference: Reference) -> CanonicalName:
    lowered = reference.strip().replace("\\", "/").lower()
    return CanonicalName(tuple(part for part in lowered.split("/") if part))
