"""Narodne novine (HR) HTTP client.

Source: https://narodne-novine.nn.hr/ (official gazette of the Republic of Croatia).
License: official legal texts are in the public domain per Croatian Copyright Act
(NN 111/2021) Article 18(3). See RESEARCH-HR.md §0.1 for the full justification.

norm_id format: HR-NN-YYYY-ISSUE-ORD (matches NormMetadata.identifier). The
client translates this to the ELI URI '/eli/sluzbeni/YYYY/ISSUE/ORD' for
HTTP fetches — the server 302-redirects the ELI form to the canonical
/clanci/sluzbeni/YYYY_MM_ISSUE_ORD.html page for HTML, and exposes
JSON-LD at '{ELI}/json-ld' for acts from 2015+. Pre-2015 acts return 404
on /json-ld and the metadata parser falls back to the HTML detailsTable
sidebar.
"""

from __future__ import annotations

import logging
import re

import requests

from legalize.fetcher.base import HttpClient

logger = logging.getLogger(__name__)

BASE_URL = "https://narodne-novine.nn.hr"

# robots.txt (fetched 2026-04-19) Disallows ~180 specific /clanci/sluzbeni/*.html
# URLs plus the entire /clanci/oglasi/ branch. None of the disallowed pages are
# in scope for v1 (they are redactions, removed acts, or announcements). The
# discovery layer filters against this set before yielding.
_ROBOTS_DISALLOW_PATHS: frozenset[str] = frozenset()  # populated lazily

_NORM_ID_RE = re.compile(r"^HR-NN-(\d{4})-(\d+)-(\d+)$")


def _norm_id_to_eli_path(norm_id: str) -> str:
    """Convert an HR-NN norm_id to the ELI URI path.

    Input:  'HR-NN-2022-151-2343'
    Output: '/eli/sluzbeni/2022/151/2343'

    The server redirects the ELI URI to the canonical HTML page
    /clanci/sluzbeni/YYYY_MM_ISSUE_ORD.html (month is derived server-side)
    and exposes JSON-LD at '{eli_path}/json-ld'.
    """
    m = _NORM_ID_RE.match(norm_id)
    if not m:
        raise ValueError(f"Malformed HR norm_id: {norm_id!r}")
    year, issue, act = m.groups()
    return f"/eli/sluzbeni/{year}/{issue}/{act}"


class NarodneNovineClient(HttpClient):
    """HTTP client for narodne-novine.nn.hr.

    Fetches per-act HTML pages (consolidated text + metadata sidebar) and
    ELI JSON-LD (machine-readable relationships, 2015+ only).
    """

    @classmethod
    def create(cls, country_config):
        src = country_config.source or {}
        return cls(
            base_url=src.get("base_url", BASE_URL),
            requests_per_second=float(src.get("requests_per_second", 2.0)),
            request_timeout=int(src.get("request_timeout", 30)),
            max_retries=int(src.get("max_retries", 5)),
        )

    def __init__(
        self,
        *,
        base_url: str = BASE_URL,
        requests_per_second: float = 2.0,
        request_timeout: int = 30,
        max_retries: int = 5,
    ) -> None:
        super().__init__(
            base_url=base_url,
            requests_per_second=requests_per_second,
            request_timeout=request_timeout,
            max_retries=max_retries,
        )
        # narodne-novine.nn.hr's leaf cert is issued by "Sectigo Public Server
        # Authentication CA DV R36". Linux/CI environments resolve this via
        # certifi; Windows devs may see CERTIFICATE_VERIFY_FAILED if the
        # bundled certifi doesn't carry that intermediate. Workaround on dev:
        # `pip install truststore && python -X importtruststore`, or add the
        # intermediate to REQUESTS_CA_BUNDLE. Production CI is unaffected.
        try:
            import certifi
            self._session.verify = certifi.where()
        except ImportError:
            pass

    def get_text(self, norm_id: str) -> bytes:
        """Fetch the per-act HTML page via the ELI URI (server redirects).

        On 404 falls back to the sitemap lookup: NN's sitemap ord and the
        act's canonical ELI ord occasionally disagree (see BOOTSTRAP-HR.md
        "Known issues" §3). The sitemap URL always resolves; the parser
        extracts the real ELI from the returned HTML.
        """
        url = self._base_url + _norm_id_to_eli_path(norm_id)
        try:
            return self._get(url)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                fallback = self._sitemap_html_url(norm_id)
                if fallback:
                    return self._get(fallback)
            raise

    def get_metadata(self, norm_id: str) -> bytes:
        """Fetch the ELI JSON-LD for an act (2015+), or HTML as fallback.

        For pre-2015 acts the /json-ld endpoint 404s and we return the HTML
        page instead — the parser dispatches on leading `{` vs `<` to pick
        the right branch. `get_text` owns the sitemap-URL fallback, so a
        mismatched ELI-ord case funnels through there transparently.
        """
        url = self._base_url + _norm_id_to_eli_path(norm_id) + "/json-ld"
        try:
            return self._get(url)
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                return self.get_text(norm_id)
            raise

    def _sitemap_html_url(self, norm_id: str) -> str | None:
        """Resolve an HR-NN norm_id to its per-act HTML URL via the sitemap.

        Used as a 404 fallback for ELI URIs that don't match the canonical
        form on the act's HTML page. Returns None if the sitemap or entry
        cannot be found.

        Tolerant of zero-padding: the sitemap sometimes lists acts with
        four-digit ords (e.g. `_102_0000.html`) while discovery records
        the int-normalized form (`HR-NN-2024-102-0`). We scan every
        `<loc>` in the sub-sitemap and pick the one whose act integer
        equals the requested one.
        """
        m = _NORM_ID_RE.match(norm_id)
        if not m:
            return None
        year, issue, act = m.groups()
        want_act = int(act)
        sub = f"/sitemap_1_{year}_{issue}.xml"
        try:
            raw = self.get_sitemap(sub)
        except requests.RequestException:
            return None
        text = raw.decode("utf-8", errors="replace")
        entries = re.findall(
            rf"<loc>\s*([^<]*?/clanci/sluzbeni/{year}_\d{{2}}_{issue}_(\d+)\.html)\s*</loc>",
            text,
            flags=re.IGNORECASE,
        )
        for url, sitemap_act in entries:
            if int(sitemap_act) == want_act:
                return url
        return None

    def get_sitemap(self, sitemap_url: str) -> bytes:
        """Fetch a sitemap XML (root or per-issue)."""
        url = sitemap_url if sitemap_url.startswith("http") else (
            self._base_url + (sitemap_url if sitemap_url.startswith("/") else "/" + sitemap_url)
        )
        return self._get(url)
