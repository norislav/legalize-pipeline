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
        """Yield HR-NN norm_ids for acts whose sitemap lastmod matches target_date.

        We scan sub-sitemaps for the target year and filter by <lastmod>.
        """
        assert isinstance(client, NarodneNovineClient)
        iso = target_date.isoformat()
        for sub_url, _part, year, _issue in self._enumerate_sub_sitemaps(client):
            if year != target_date.year:
                continue
            try:
                raw = client.get_sitemap(sub_url)
                root = ET.fromstring(raw.lstrip())
            except ET.ParseError:
                continue
            for url_el in root.findall("sm:url", _SITEMAP_NS):
                loc = (url_el.findtext("sm:loc", default="", namespaces=_SITEMAP_NS) or "").strip()
                lastmod = (
                    url_el.findtext("sm:lastmod", default="", namespaces=_SITEMAP_NS) or ""
                ).strip()[:10]
                if lastmod != iso:
                    continue
                norm_id = self._url_to_norm_id(loc)
                if norm_id:
                    yield norm_id

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
