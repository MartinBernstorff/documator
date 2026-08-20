import shutil
from dataclasses import dataclass
from pathlib import Path

from iterpy import Arr

from documator.domain import (
    ExitCode,
    InputDir,
    OutputDir,
    RelativePath,
    TimeoutSeconds,
)
from documator.engine import (
    Adoption,
    Allocation,
    Claim,
    Failure,
    Landed,
    Mode,
    Origin,
    Placement,
    adoptable,
    allocate,
    blocked,
    directory_conflict,
    log,
    outdated,
    prune,
    relative_files,
    render_markdown,
    report_conflict,
    report_orphans,
    report_takeover,
    worst,
)
from documator.execution import Annotation
from documator.frontmatter import partition
from documator.inert import unmarked
from documator.manifest import (
    DestinationPath,
    Manifest,
    TemplatePath,
    clear_claims,
    read_claims,
    read_manifest,
    write_claims,
    write_manifest,
)
from documator.notice import annotated
from documator.parsing import Markdown
from documator.sections import emitted
from documator.structural import Misplaced, misplaced
from documator.summary import Errored, Problem, Produced, summarise
from documator.transclusion import NotePath, Target, index


# A non-markdown file has no rendered text of its own: it lands as a verbatim copy of
# its source.
@dataclass(frozen=True, slots=True)
class _Artifact:
    source: Path
    destination: DestinationPath
    text: Markdown | None

    def landed(self) -> Landed:
        if self.text is None:
            return Landed.copied(self.source)
        return Landed.rendered(self.text)


def _mirrored(relative: RelativePath) -> DestinationPath:
    return DestinationPath(unmarked(relative))


def _refused(failure: Misplaced) -> Failure:
    # Filed at the source, because there is no destination: the path never lands.
    reported = Failure(
        DestinationPath(failure.path), Annotation(failure.reason()), ExitCode(1)
    )
    log.error("%s", reported)
    return reported


def _claimed(
    destination: DestinationPath, claimants: tuple[RelativePath, ...]
) -> Failure:
    named = " and ".join(str(claimant) for claimant in claimants)
    failure = Failure(
        destination, Annotation(f"refusing to write: claimed by {named}"), ExitCode(1)
    )
    log.error("%s", failure)
    return failure


def render(
    input_dir: InputDir,
    output_dir: OutputDir,
    timeout: TimeoutSeconds,
    mode: Mode = Mode.WRITE,
    adoption: Adoption = Adoption.REFUSE,
) -> ExitCode:
    conflict = directory_conflict(input_dir, output_dir)
    if conflict is not None:
        return report_conflict(conflict)

    # The mark is one vocabulary across both layouts, so a path that cannot be a skill
    # is refused here too rather than mirrored with the mark quietly stripped off it.
    misplacements = misplaced(relative_files(input_dir))
    rejected = {failure.path for failure in misplacements}

    # Decided before anything is rendered, so a clash costs both sides their blocks as
    # well as their output: an arbitrary winner would make the survivor a tiebreak.
    contenders = (
        Arr(relative_files(input_dir))
        .filter(lambda path: path not in rejected)
        .groupby(lambda path: str(_mirrored(path)))
    ).to_list()
    relative_paths = [
        path for _, claimants in contenders if len(claimants) == 1 for path in claimants
    ]
    tracked = read_manifest(output_dir)
    owned = tracked.destinations() | read_claims(output_dir).destinations()
    produced = {_mirrored(path) for path in relative_paths}
    # Settled before anything else looks at ownership, so a run that adopts differs
    # from one that always owned these paths only in the line it logs. A preview keeps
    # its hands off `owned`, because the refusal is what it has to report.
    adopted = adoptable(output_dir, owned, produced, adoption)
    # Announced before the first byte lands, so the run says what it is about to destroy
    # rather than reporting it afterwards.
    takeover = report_takeover(adopted, mode)
    if mode is Mode.WRITE:
        owned = owned | adopted

    failures: list[Failure] = [
        *(_refused(failure) for failure in misplacements),
        *(
            _claimed(_mirrored(claimants[0]), tuple(claimants))
            for _, claimants in contenders
            if len(claimants) > 1
        ),
    ]
    if mode is Mode.CHECK:
        failures.extend(report_orphans(output_dir, tracked, produced))
    else:
        # Pruned first, so a path this run reclaims is free before anything writes into
        # it. Pruning goes by the manifest alone: a claim a dead run left behind says
        # documator meant to write that path, which is no reason to delete what sits
        # there now.
        prune(output_dir, tracked, produced)

    # Indexed once per run, so every transclusion in the run sees the same vault.
    vault = index(input_dir)
    # The tree is mirrored, so every attachment lands exactly where it was written.
    landed = {
        attachment: _mirrored(RelativePath(attachment.root))
        for attachment in vault.attachments
    }

    # Check mode writes nothing, so it has nothing to claim: it settles every refusal at
    # the site that reports it, one file at a time.
    intended: Allocation | None = None
    if mode is Mode.WRITE:
        intended = allocate(
            output_dir,
            owned,
            [Claim(TemplatePath(path), _mirrored(path)) for path in relative_paths],
        )
        failures.extend(intended.refusals)
        write_claims(output_dir, intended.claimed)

    written: dict[TemplatePath, DestinationPath] = {}
    for relative in relative_paths:
        template = TemplatePath(relative)
        destination = _mirrored(relative)
        if intended is not None and not intended.covers(destination):
            continue
        # Checked before rendering, so a file that cannot land never runs its blocks.
        refused = blocked(
            output_dir, owned | set(written.values()), destination, adoption
        )
        if refused is not None:
            failures.append(refused)
            continue
        source = input_dir.root / relative
        text = None
        if source.suffix.lower() == ".md":
            # Lifted before anything runs, exactly as `skills` does it: a note's
            # frontmatter describes the note, so no block and no link rewrites it.
            authored = partition(Markdown(source.read_text(encoding="utf-8")))
            rendered = render_markdown(
                emitted(authored.body),
                Origin(
                    vault,
                    (Target.whole(NotePath(relative)),),
                    Placement(destination, landed),
                ),
                timeout,
            )
            failures.extend(rendered.failures)
            text = annotated(Markdown(authored.preamble + rendered.text), template)
        failures.extend(_land(mode, output_dir, _Artifact(source, destination, text)))
        written[template] = destination
        log.info("%s %s", "checked" if mode is Mode.CHECK else "rendered", relative)

    if mode is Mode.WRITE:
        # Rewritten last and now only for what really landed, so a run that finishes
        # leaves a manifest that claims no file it refused to write.
        write_manifest(output_dir, Manifest(written))
        clear_claims(output_dir)

    problems: list[Problem] = [*takeover, *(Errored(failure) for failure in failures)]
    summarise(Produced(len(written)), problems)
    return worst(failures)


# The only place the two modes part ways: one makes the output match, the other reports
# that it does not.
def _land(mode: Mode, output_dir: OutputDir, artifact: _Artifact) -> list[Failure]:
    if mode is Mode.CHECK:
        stale = outdated(output_dir, artifact.destination, artifact.landed())
        return [] if stale is None else [stale]
    target = output_dir.root / artifact.destination
    target.parent.mkdir(parents=True, exist_ok=True)
    if artifact.text is None:
        shutil.copy2(artifact.source, target)
    else:
        target.write_text(artifact.text, encoding="utf-8")
    return []
