import re
from dataclasses import dataclass
from pathlib import Path
from typing import NewType, override

from iterpy import Arr
from pydantic import RootModel, field_validator
from pydantic_core import PydanticCustomError

from documator.domain import ExistingFile, InputDir, RelativePath, WorkingDir
from documator.inert import PathClass, classify, skill_name

Reference = NewType("Reference", str)
CanonicalName = NewType("CanonicalName", tuple[str, ...])
HeadingKey = NewType("HeadingKey", str)


# Two spellings of one heading are one heading, so identity is the normalised form
# while the text stays as written: a reference copied out of a heading — markup and
# all — resolves to it, and `#Usage` embedding `#usage` is still a cycle.
class HeadingText(RootModel[str]):
    @override
    def __str__(self) -> str:
        return self.root

    def key(self) -> HeadingKey:
        return HeadingKey(" ".join(_bare(self).split()).casefold())

    @override
    def __eq__(self, other: object) -> bool:
        return isinstance(other, HeadingText) and self.key() == other.key()

    @override
    def __hash__(self) -> int:
        return hash(self.key())


def _bare(text: HeadingText) -> str:
    aliased = re.sub(r"\[\[[^\[\]|]*\|([^\[\]]*)\]\]", r"\1", text.root)
    linked = re.sub(r"\[\[([^\[\]]*)\]\]", r"\1", aliased)
    inlined = re.sub(r"!?\[([^\[\]]*)\]\([^()]*\)", r"\1", linked)
    return re.sub(r"[*_~`]", "", inlined)


HeadingPath = NewType("HeadingPath", tuple[HeadingText, ...])


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

    # Keyed by path in the map of where each attachment landed, so it has to hash.
    @override
    def __hash__(self) -> int:
        return hash(self.root)


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


# The whole note is an empty path rather than a separate case, so a cycle, an origin and
# a working directory all read the same whether or not a section was named.
@dataclass(frozen=True, slots=True)
class Target:
    note: NotePath
    path: HeadingPath

    @classmethod
    def whole(cls, note: NotePath) -> Target:
        return cls(note, HeadingPath(()))

    def into(self, segment: HeadingText) -> Target:
        return Target(self.note, HeadingPath((*self.path, segment)))

    def __str__(self) -> str:
        return "#".join((str(self.note), *(str(part) for part in self.path)))


@dataclass(frozen=True, slots=True)
class EmptySection:
    reference: Reference

    def __str__(self) -> str:
        return f'transclusion "{self.reference}" names an empty section'


@dataclass(frozen=True, slots=True)
class BlockReferenceUnsupported:
    reference: Reference

    def __str__(self) -> str:
        return (
            f'transclusion "{self.reference}" names a block reference, '
            "which is unsupported"
        )


@dataclass(frozen=True, slots=True)
class NoSection:
    searched: Target
    wanted: HeadingText
    available: tuple[HeadingText, ...]

    def __str__(self) -> str:
        where = "under" if self.searched.path else "in"
        has = (
            ", ".join(str(heading) for heading in self.available)
            if self.available
            else "nothing nested there"
        )
        return f'no section "{self.wanted}" {where} {self.searched}; it has {has}'


@dataclass(frozen=True, slots=True)
class AmbiguousSection:
    searched: Target
    wanted: HeadingText

    def __str__(self) -> str:
        matched = self.searched.into(self.wanted)
        return f"section {matched} matches more than one heading"


type SectionFailure = NoSection | AmbiguousSection


@dataclass(frozen=True, slots=True)
class Cycle:
    chain: tuple[Target, ...]

    def __str__(self) -> str:
        return "transclusion cycle: " + " -> ".join(
            str(target) for target in self.chain
        )


# An `![[image.png]]` embed is Obsidian's, not ours, so it goes back out as it came in.
@dataclass(frozen=True, slots=True)
class NonNoteEmbed:
    reference: Reference

    def __str__(self) -> str:
        return f"![[{self.reference}]]"


type TransclusionFailure = (
    NoMatch
    | Ambiguous
    | EmptySection
    | BlockReferenceUnsupported
    | SectionFailure
    | Cycle
)
type Resolution = Target | NonNoteEmbed | TransclusionFailure


@dataclass(frozen=True, slots=True)
class Vault:
    root: Path
    notes: tuple[NotePath, ...]
    attachments: tuple[AttachmentPath, ...]

    # Indexing and reading are separate steps, so joining is where a note that left
    # the vault mid-run stops being a guess.
    def source(self, note: VaultPath) -> ExistingFile:
        return ExistingFile(self.root / note.root)

    def read(self, note: NotePath) -> str:
        return self.source(note).root.read_text(encoding="utf-8")

    def read_bytes(self, attachment: AttachmentPath) -> bytes:
        return self.source(attachment).root.read_bytes()

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


def _invisible(note: NotePath) -> bool:
    return classify(RelativePath(note.root)) is PathClass.INVISIBLE


# Attachments stay indexed: an `![[image.png]]` embed passes through unread, so dropping
# an invisible one would turn it into the very error an invisible path must never be.
def without_invisible_notes(vault: Vault) -> Vault:
    return Vault(
        vault.root,
        tuple(Arr(vault.notes).filter(lambda note: not _invisible(note)).to_list()),
        vault.attachments,
    )


def resolve(
    vault: Vault, reference: Reference, entered: tuple[Target, ...]
) -> Resolution:
    addressed = _addressed(reference)
    wanted = _canonical(addressed.named)
    if not wanted:
        return NoMatch(reference)
    candidates = Arr(vault.notes).filter(lambda note: _matches(note, wanted)).to_list()
    if len(candidates) > 1:
        return Ambiguous(reference, tuple(candidates))
    if not candidates:
        # An attachment's fragment is Obsidian's to read — a PDF page, say — so it is
        # never judged as a heading path, whatever shape it has.
        if _attached(vault, addressed.named):
            return NonNoteEmbed(reference)
        return NoMatch(reference)
    unsupported = _unsupported(reference, addressed.path)
    if unsupported is not None:
        return unsupported
    target = Target(candidates[0], addressed.path)
    return Cycle((*entered, target)) if target in entered else target


def _unsupported(
    reference: Reference, path: HeadingPath
) -> BlockReferenceUnsupported | EmptySection | None:
    # A caret is only a block id when it is the whole fragment; inside a path it is just
    # a segment that will miss, because Obsidian has no nested block reference either.
    if len(path) == 1 and str(path[0]).startswith("^"):
        return BlockReferenceUnsupported(reference)
    if not all(str(segment) for segment in path):
        return EmptySection(reference)
    return None


@dataclass(frozen=True, slots=True)
class _Address:
    named: Reference
    path: HeadingPath


# Split on every `#`, so a heading path reaches nested sections the way Obsidian's does.
# The price is Obsidian's own: a heading whose text contains a `#` is unreachable.
def _addressed(reference: Reference) -> _Address:
    # An embed renders the target, never its alias, so the display text is dropped
    # rather than left to poison the heading it is glued to.
    segments = reference.split("|")[0].split("#")
    return _Address(
        Reference(segments[0]),
        HeadingPath(tuple(HeadingText(segment.strip()) for segment in segments[1:])),
    )


# Only an attachment that really exists earns a passthrough; otherwise a dotted note
# name would silently swallow the reference instead of reporting the miss.
def _attached(vault: Vault, reference: Reference) -> bool:
    wanted = _segments(reference)
    return Arr(vault.attachments).any(
        lambda path: _segments(Reference(str(path)))[-len(wanted) :] == wanted
    )


@dataclass(frozen=True, slots=True)
class NoLinkTarget:
    reference: Reference

    def __str__(self) -> str:
        return f'no note matches link "{self.reference}"'


@dataclass(frozen=True, slots=True)
class AmbiguousLink:
    reference: Reference
    candidates: tuple[VaultPath, ...]

    def __str__(self) -> str:
        named = ", ".join(str(candidate) for candidate in self.candidates)
        return f'link "{self.reference}" matches {named}'


Alias = NewType("Alias", str)
Fragment = NewType("Fragment", str)


# Everything the author wrote around the target: both parts survive resolution and shape
# the emitted text, so they travel as one value rather than as a pair of arguments.
@dataclass(frozen=True, slots=True)
class Wording:
    fragment: Fragment
    alias: Alias


@dataclass(frozen=True, slots=True)
class LinkedNote:
    note: NotePath
    wording: Wording


@dataclass(frozen=True, slots=True)
class LinkedAttachment:
    attachment: AttachmentPath
    wording: Wording


type LinkFailure = NoLinkTarget | AmbiguousLink
type LinkResolution = LinkedNote | LinkedAttachment | LinkFailure


# A link names a thing rather than lending its text, so it resolves to the target alone:
# no chain and no cycle.
def resolve_link(vault: Vault, reference: Reference) -> LinkResolution:
    named, alias = _aliased(reference)
    addressed, fragment = _fragmented(named)
    wording = Wording(fragment, alias)
    wanted = _canonical(addressed)
    if not wanted:
        return NoLinkTarget(reference)
    candidates = (
        Arr(vault.notes)
        .filter(lambda note: _matches(note, wanted) or _marked(note, wanted))
        .to_list()
    )
    if len(candidates) > 1:
        return AmbiguousLink(reference, tuple(candidates))
    if not candidates:
        return _attachment(vault, reference, addressed, wording)
    return LinkedNote(candidates[0], wording)


# An attachment is matched on its literal name: unlike a note, its suffix is part of
# what the author wrote rather than a spelling of it.
def _attachment(
    vault: Vault, reference: Reference, addressed: Reference, wording: Wording
) -> LinkedAttachment | LinkFailure:
    wanted = _segments(addressed)
    found = (
        Arr(vault.attachments)
        .filter(lambda path: _segments(Reference(str(path)))[-len(wanted) :] == wanted)
        .to_list()
    )
    if len(found) > 1:
        return AmbiguousLink(reference, tuple(found))
    if not found:
        return NoLinkTarget(reference)
    return LinkedAttachment(found[0], wording)


# An embed drops the alias because it renders the target; a link keeps it, because the
# alias is the text the sentence needs.
def _aliased(reference: Reference) -> tuple[Reference, Alias]:
    named, _, alias = reference.partition("|")
    return Reference(named), Alias(alias.strip())


# Kept whole rather than split into a heading path: a link carries its fragment to the
# reader instead of walking it, so a `#` inside a heading costs nothing here.
def _fragmented(reference: Reference) -> tuple[Reference, Fragment]:
    addressed, _, fragment = reference.partition("#")
    return Reference(addressed), Fragment(fragment.strip())


def _matches(note: NotePath, wanted: CanonicalName) -> bool:
    return _canonical(Reference(str(note)))[-len(wanted) :] == wanted


# A folder skill is named by its folder, so nothing in the vault is spelled the way the
# link is. Matching the mark itself is the only way `[[@plan]]` can reach plan/SKILL.md.
def _marked(note: NotePath, wanted: CanonicalName) -> bool:
    named = skill_name(RelativePath(note.root))
    return named is not None and wanted == (f"@{named}".lower(),)


def _canonical(reference: Reference) -> CanonicalName:
    return _segments(Reference(re.sub(r"\.md$", "", reference, flags=re.IGNORECASE)))


def _segments(reference: Reference) -> CanonicalName:
    lowered = reference.strip().replace("\\", "/").lower()
    return CanonicalName(tuple(part for part in lowered.split("/") if part))
