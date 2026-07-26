import re
from dataclasses import dataclass
from pathlib import Path
from typing import NewType

from iterpy import Arr

from documator.domain import InputDir

Reference = NewType("Reference", str)
# Relative to the vault root, so a note reads the same from anywhere in the tree.
NotePath = NewType("NotePath", Path)
CanonicalName = NewType("CanonicalName", tuple[str, ...])

EMBED = re.compile(r"!\[\[(?P<reference>[^\[\]\n]*)\]\]")


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


# An `![[image.png]]` embed is Obsidian's, not ours; passing it through keeps the
# rendered file browsable instead of failing on every picture in the vault.
@dataclass(frozen=True, slots=True)
class NonNoteEmbed:
    reference: Reference


type TransclusionFailure = NoMatch | Ambiguous | FragmentUnsupported | Cycle
type Resolution = NotePath | NonNoteEmbed | TransclusionFailure


@dataclass(frozen=True, slots=True)
class Vault:
    root: Path
    notes: tuple[NotePath, ...]


def index(input_dir: InputDir) -> Vault:
    notes = (
        Arr(input_dir.root.rglob("*"))
        .filter(lambda path: path.is_file() and path.suffix.lower() == ".md")
        .map(lambda path: NotePath(path.relative_to(input_dir.root)))
        .to_list()
    )
    return Vault(input_dir.root, tuple(sorted(notes, key=str)))


def resolve(vault: Vault, reference: Reference) -> Resolution:
    if "#" in reference:
        return FragmentUnsupported(reference)
    wanted = _canonical(reference)
    if not wanted:
        return NoMatch(reference)
    candidates = Arr(vault.notes).filter(lambda note: _matches(note, wanted)).to_list()
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        return Ambiguous(reference, tuple(candidates))
    suffix = Path(reference.strip()).suffix.lower()
    if suffix and suffix != ".md":
        return NonNoteEmbed(reference)
    return NoMatch(reference)


def _matches(note: NotePath, wanted: CanonicalName) -> bool:
    return _canonical(str(note))[-len(wanted) :] == wanted


def _canonical(text: str) -> CanonicalName:
    stem = re.sub(r"\.md$", "", text.strip(), flags=re.IGNORECASE)
    return CanonicalName(
        tuple(part for part in stem.replace("\\", "/").lower().split("/") if part)
    )
