"""Discovery of Narodne novine acts via the cascading sitemap.

Root:    /sitemap.xml                          → index of per-issue sitemaps
Issue:   /sitemap_{PART}_{YYYY}_{ISSUE}.xml    → per-act URLs with <lastmod>

Part codes: 1 = Službeni dio (primary legislation), 2 = Međunarodni dio (treaties),
3 = Oglasni dio (announcements/tenders — out of scope for v1).

Yielded norm_ids are the canonical HR-NN identifiers:
    'HR-NN-2022-151-2343'
This matches NormMetadata.identifier, so the generic pipeline's existence
check (safe_id(norm_id) == identifier) is a cheap local string op. The
client translates HR-NN → ELI URI internally for HTTP fetches.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from datetime import date
from xml.etree import ElementTree as ET

from legalize.fetcher.base import LegislativeClient, NormDiscovery
from legalize.fetcher.hr.client import NarodneNovineClient

logger = logging.getLogger(__name__)

_SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

# Sub-sitemap filename: sitemap_{PART}_{YYYY}_{ISSUE}.xml
_SUB_SITEMAP_RE = re.compile(r"/sitemap_(\d+)_(\d{4})_(\d+)\.xml$")

# Per-act URL (HTML form): /clanci/sluzbeni/{YYYY}_{MM}_{ISSUE}_{ACT}.html
_ACT_URL_RE = re.compile(r"/clanci/sluzbeni/(\d{4})_(\d{2})_(\d+)_(\d+)\.html$")

# discover_daily walks issues newest-first and stops once an issue's
# publication_date is this many days before the target. NN occasionally
# publishes back-dated supplementary issues (e.g. NN 91A appearing after
# NN 92), so the margin is non-zero. 14 days has comfortable headroom
# without scanning the whole year.
_DAILY_STOP_MARGIN_DAYS = 14


class NarodneNovineDiscovery(NormDiscovery):
    """Discovers all Narodne novine acts via the public sitemap."""

    def __init__(self, *, parts: tuple[int, ...] = (1,), year_start: int | None = None) -> None:
        self._parts = parts
        self._year_start = year_start

    @classmethod
    def create(cls, source: dict) -> NarodneNovineDiscovery:
        parts = tuple(source.get("parts", (1,)))
        year_start = source.get("year_start")
        return cls(parts=parts, year_start=year_start)

    def discover_all(self, client: LegislativeClient, **kwargs) -> Iterator[str]:
        """Yield HR-NN norm_ids for every act in the configured parts."""
        assert isinstance(client, NarodneNovineClient)
        for sub_url, _part, year, _issue in self._enumerate_sub_sitemaps(client):
            if self._year_start is not None and year < self._year_start:
                continue
            try:
                yield from self._parse_sub_sitemap(client, sub_url)
            except ET.ParseError:
                logger.warning("Malformed sub-sitemap: %s", sub_url)
                continue

    def discover_daily(
        self, client: LegislativeClient, target_date: date, **kwargs
    ) -> Iterator[str]:
        """Yield HR-NN norm_ids for acts whose date_publication matches target_date.

        NN's sitemap does not populate the ``<lastmod>`` element — every
        entry has an empty value — so we cannot filter on it. Instead we
        walk the target year's sub-sitemaps newest-issue first, probe
        the first act of each issue for its JSON-LD ``date_publication``,
        and yield every act from issues that match ``target_date``. Walk
        stops once an issue is dated more than ``_DAILY_STOP_MARGIN_DAYS``
        before the target (later/lower-numbered issues cannot be newer).

        NN publishes 0–3 issues per weekday and ~50–200 acts per issue,
        so the cost is ~1 metadata fetch per recent issue scanned. At
        the configured 1.5 r/s rate, scanning 5 recent issues costs
        ~5 seconds — comparable to the previous (broken) implementation.
        """
        from datetime import timedelta

        from legalize.fetcher.hr.parser import NarodneNovineMetadataParser

        assert isinstance(client, NarodneNovineClient)
        meta_parser = NarodneNovineMetadataParser()

        # Collect this year's sub-sitemaps; walk newest issue first.
        issues: list[tuple[int, str]] = []
        for sub_url, _part, year, issue_num in self._enumerate_sub_sitemaps(client):
            if year == target_date.year:
                issues.append((issue_num, sub_url))
        issues.sort(reverse=True)

        for issue_num, sub_url in issues:
            try:
                act_ids = list(self._parse_sub_sitemap(client, sub_url))
            except ET.ParseError:
                logger.warning("Malformed sub-sitemap: %s", sub_url)
                continue
            if not act_ids:
                continue

            # Probe the first act to learn the issue's publication date.
            probe = act_ids[0]
            try:
                meta_data = client.get_metadata(probe)
                metadata = meta_parser.parse(meta_data, probe)
                issue_date = metadata.publication_date
            except Exception as exc:
                logger.warning(
                    "Could not probe issue %d publication date via %s: %s",
                    issue_num, probe, exc,
                )
                continue

            if issue_date == target_date:
                yield from act_ids
            elif issue_date < target_date - timedelta(days=_DAILY_STOP_MARGIN_DAYS):
                # Earlier issues can only have earlier dates — stop walking.
                logger.debug(
                    "Stopping daily walk at issue %d (%s, %d+ days before target)",
                    issue_num, issue_date, _DAILY_STOP_MARGIN_DAYS,
                )
                return

    def _enumerate_sub_sitemaps(
        self, client: NarodneNovineClient
    ) -> Iterator[tuple[str, int, int, int]]:
        """Yield (sub_sitemap_url, part, year, issue) from the root sitemap."""
        try:
            root_xml = client.get_sitemap("/sitemap.xml")
        except Exception as exc:
            logger.error("Failed to fetch root sitemap: %s", exc)
            return
        try:
            root = ET.fromstring(root_xml.lstrip())
        except ET.ParseError as exc:
            logger.error("Malformed root sitemap: %s", exc)
            return

        for sm_el in root.findall("sm:sitemap", _SITEMAP_NS):
            loc = (sm_el.findtext("sm:loc", default="", namespaces=_SITEMAP_NS) or "").strip()
            m = _SUB_SITEMAP_RE.search(loc)
            if not m:
                continue
            part, year, issue = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if part not in self._parts:
                continue
            yield loc, part, year, issue

    def _parse_sub_sitemap(
        self, client: NarodneNovineClient, url: str
    ) -> Iterator[str]:
        """Parse a per-issue sitemap and yield HR-NN norm_ids."""
        raw = client.get_sitemap(url)
        root = ET.fromstring(raw.lstrip())
        for url_el in root.findall("sm:url", _SITEMAP_NS):
            loc = (url_el.findtext("sm:loc", default="", namespaces=_SITEMAP_NS) or "").strip()
            norm_id = self._url_to_norm_id(loc)
            if norm_id:
                yield norm_id

    @staticmethod
    def _url_to_norm_id(loc: str) -> str | None:
        """Convert a sitemap <loc> (per-act HTML URL) to an HR-NN norm_id."""
        m = _ACT_URL_RE.search(loc)
        if not m:
            return None
        year, _month, issue, act = m.groups()
        return f"HR-NN-{year}-{int(issue)}-{int(act)}"
