"""Croatia-specific daily processing.

Each act published in Narodne novine maps 1:1 to a single .md file in
legalize-hr. Amending acts produce their own file (the amending act's own
text), tagged [reform]; the original law's file is unaffected until NN
publishes a separate pročišćeni tekst (which itself has its own ELI).

This means no reform-disposition resolution is needed (unlike ES/FR) — we
simply discover, fetch, parse, classify, and commit one act at a time.
"""

from __future__ import annotations

import logging
import re
from datetime import date

from rich.console import Console

from legalize.committer.git_ops import GitRepo
from legalize.committer.message import build_commit_info
from legalize.config import Config
from legalize.models import CommitType, NormMetadata, Reform
from legalize.pipeline import finalize_daily
from legalize.state.store import StateStore, resolve_dates_to_process
from legalize.transformer.markdown import render_norm_at_date
from legalize.transformer.slug import norm_to_filepath

console = Console()
logger = logging.getLogger(__name__)


# Title-based classification. Croatian legal titles are highly regular:
#   "Ispravak ..."                         → correction
#   "Zakon o prestanku važenja ..."        → repeal
#   "Odluka o stavljanju izvan snage ..."  → repeal
#   "Zakon o izmjenama i dopunama ..."     → reform
#   "... pročišćeni tekst"                 → reform (consolidated republication)
# Everything else is treated as a brand-new act.
_CORRECTION_RX = re.compile(r"^\s*ispravak\b", re.IGNORECASE)
_REPEAL_RX = re.compile(r"\bprestan|stavlja(?:nj[ue])?\s+izvan\s+snage", re.IGNORECASE)
_REFORM_RX = re.compile(r"\b(izmjen|dopun|pro[cč]i[sš][cć])", re.IGNORECASE)


def _classify(meta: NormMetadata) -> CommitType:
    """Pick a CommitType from the act's title."""
    title = meta.title or ""
    if _CORRECTION_RX.search(title):
        return CommitType.CORRECTION
    if _REPEAL_RX.search(title):
        return CommitType.REPEAL
    if _REFORM_RX.search(title):
        return CommitType.REFORM
    return CommitType.NEW


def daily(
    config: Config,
    target_date: date | None = None,
    dry_run: bool = False,
) -> int:
    """Daily processing for Croatia (Narodne novine)."""
    from legalize.fetcher.hr.client import NarodneNovineClient
    from legalize.fetcher.hr.discovery import NarodneNovineDiscovery
    from legalize.fetcher.hr.parser import (
        NarodneNovineMetadataParser,
        NarodneNovineTextParser,
    )

    cc = config.get_country("hr")
    state = StateStore(cc.state_path)
    state.load()

    dates_to_process = resolve_dates_to_process(
        state,
        cc.repo_path,
        target_date,
        skip_weekdays={5, 6},
    )
    if dates_to_process is None:
        console.print("[yellow]No last date found. Use --date or run bootstrap.[/yellow]")
        return 0
    if not dates_to_process:
        console.print("[green]Nothing to process — up to date[/green]")
        return 0

    console.print(f"[bold]Daily HR — processing {len(dates_to_process)} day(s)[/bold]")

    repo = GitRepo(cc.repo_path, config.git.committer_name, config.git.committer_email)
    commits_created = 0
    errors: list[str] = []

    discovery = NarodneNovineDiscovery.create(cc.source or {})
    text_parser = NarodneNovineTextParser()
    meta_parser = NarodneNovineMetadataParser()

    with NarodneNovineClient.create(cc) as client:
        for current_date in dates_to_process:
            console.print(f"\n  [bold]{current_date}[/bold]")

            try:
                norm_ids = list(discovery.discover_daily(client, current_date))
            except Exception:
                msg = f"Error discovering changes for {current_date}"
                logger.error(msg, exc_info=True)
                errors.append(msg)
                continue

            if not norm_ids:
                console.print("    No new acts found")
                state.last_summary_date = current_date
                continue

            console.print(f"    {len(norm_ids)} act(s) found")

            for norm_id in norm_ids:
                if dry_run:
                    console.print(f"    [dim]{norm_id} — would process[/dim]")
                    continue

                try:
                    meta_data = client.get_metadata(norm_id)
                    metadata = meta_parser.parse(meta_data, norm_id)

                    text_data = client.get_text(norm_id)
                    blocks = text_parser.parse_text(text_data)

                    file_path = norm_to_filepath(metadata)
                    markdown = render_norm_at_date(
                        metadata, blocks, current_date, include_all=True
                    )

                    changed = repo.write_and_add(file_path, markdown)
                    if not changed:
                        console.print(
                            f"    [dim]⏭ {metadata.short_title[:60]} — no changes[/dim]"
                        )
                        continue

                    ctype = _classify(metadata)
                    reform = Reform(
                        date=current_date,
                        norm_id=norm_id,
                        affected_blocks=(),
                    )
                    info = build_commit_info(
                        ctype,
                        metadata,
                        reform,
                        blocks,
                        file_path,
                        markdown,
                    )
                    sha = repo.commit(info)

                    if sha:
                        commits_created += 1
                        console.print(f"    [green]✓[/green] {info.subject}")

                except Exception as e:
                    msg = f"Error processing {norm_id}: {e}"
                    logger.error(msg, exc_info=True)
                    errors.append(msg)

            state.last_summary_date = current_date

    return finalize_daily(
        repo,
        state,
        dates_to_process,
        commits_created,
        errors,
        dry_run=dry_run,
        push=config.git.push,
    )
