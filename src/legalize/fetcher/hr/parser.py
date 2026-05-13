"""Parsers for Narodne novine HTML text and ELI JSON-LD metadata.

Text source: per-act HTML page (`<div class="articleContent">` …), or a PDF
document at the same ELI URL for State Budget and similar large acts.
Metadata: ELI JSON-LD (2015+) with HTML fallback (detailsTable sidebar + <h3>).

See RESEARCH-HR.md §0.3 and §0.4 for the inventory driving this parser.
"""

from __future__ import annotations

import io
import json
import logging
import re
from datetime import date, datetime
from html import unescape
from typing import Any
from xml.etree import ElementTree as ET

from legalize.fetcher.base import MetadataParser, TextParser
from legalize.models import (
    Block,
    NormMetadata,
    NormStatus,
    Paragraph,
    Rank,
    Version,
)

logger = logging.getLogger(__name__)

_ARTICLE_CONTENT_RE = re.compile(
    r'<div[^>]*class="[^"]*\barticleContent\b[^"]*"[^>]*>(.*)',
    re.DOTALL,
)
_STYLE_SCRIPT_RE = re.compile(r"<(style|script)\b[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_DETAILS_TABLE_RE = re.compile(
    r'<table[^>]*class="[^"]*\bdetailsTable\b[^"]*"[^>]*>.*?</table>',
    re.DOTALL | re.IGNORECASE,
)
_META_TABLE_RE = re.compile(
    r'<table[^>]*class="[^"]*\bmetaTable\b[^"]*"[^>]*>.*?</table>',
    re.DOTALL | re.IGNORECASE,
)
_CHROME_H2_RE = re.compile(
    r"<h2\b[^>]*>\s*(Op\u0107i uvjeti kori\u0161tenja|Za\u0161tita privatnosti)\s*</h2>",
    re.IGNORECASE,
)
# NN wraps the page-chrome title in <div id="sticky" class="title">…</div> and
# the citation line in <span class="title-for-print">…</span>. Both duplicate
# the frontmatter title and NN-issue breadcrumb, so strip them from the body
# before paragraph extraction.
_CHROME_TITLE_DIV_RE = re.compile(
    r'<div\b[^>]*\bclass="[^"]*\btitle\b[^"]*"[^>]*>.*?</div>',
    re.DOTALL | re.IGNORECASE,
)
_CHROME_TITLE_SPAN_RE = re.compile(
    r'<span\b[^>]*\bclass="[^"]*\btitle-for-print\b[^"]*"[^>]*>.*?</span>',
    re.DOTALL | re.IGNORECASE,
)
_H3_CITATION_RE = re.compile(
    r"<h3[^>]*>\s*NN\s+(\d+)/(\d{2,4})\s+"
    r"\((\d{1,2})\.(\d{1,2})\.(\d{4})\.\)\s*,\s*(.+?)\s*</h3>",
    re.DOTALL,
)

# Croatian rank mapping from `type_document` / `Vrsta dokumenta`.
# "OSTALO" is a catch-all; final rank resolved from title prefix.
_TYPE_TO_RANK: dict[str, str] = {
    "USTAV": "ustav",
    "ZAKON": "zakon",
    "UREDBA": "uredba",
    "PRAVILNIK": "pravilnik",
    "ODLUKA": "odluka",
    "NAREDBA": "naredba",
    "RJEŠENJE": "rjesenje",
    "RJESENJE": "rjesenje",
}

_TITLE_PREFIX_TO_RANK: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"^\s*Ustav\b", re.IGNORECASE), "ustav"),
    (re.compile(r"^\s*Zakon(ik)?\b", re.IGNORECASE), "zakon"),
    (re.compile(r"^\s*Uredba\b", re.IGNORECASE), "uredba"),
    (re.compile(r"^\s*Pravilnik\b", re.IGNORECASE), "pravilnik"),
    (re.compile(r"^\s*Odluka\b", re.IGNORECASE), "odluka"),
    (re.compile(r"^\s*Naredba\b", re.IGNORECASE), "naredba"),
    (re.compile(r"^\s*Rje\u0161enje\b", re.IGNORECASE), "rjesenje"),
)


def _parse_date(s: str) -> date | None:
    """Parse ISO YYYY-MM-DD or Croatian DD.MM.YYYY. (with trailing dot)."""
    if not s:
        return None
    s = s.strip().rstrip(".")
    for fmt in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _uri_tail(s: str) -> str:
    """If s looks like a URI, return the final path segment; else return s."""
    if not s:
        return ""
    if "://" in s or s.startswith("http"):
        return s.rstrip("/").rsplit("/", 1)[-1]
    return s


def _strip_nn_host(s: str) -> str:
    """Reduce an NN ELI URI to its bare 'eli/...' path.

    Handles the single-slash scheme NN emits ('https:/narodne-novine.nn.hr/...')
    as well as proper URIs. Non-NN URIs (e.g. CELEX links) pass through.
    """
    if not s:
        return s
    m = re.search(r"narodne-novine\.nn\.hr/(eli/.+)$", s)
    if m:
        return m.group(1)
    return s


def _rank_from_type_and_title(type_document: str, title: str) -> Rank:
    """Resolve a rank from (type_document, title) with title fallback for OSTALO."""
    key = _uri_tail((type_document or "").strip()).upper()
    mapped = _TYPE_TO_RANK.get(key)
    if mapped and mapped != "":
        return Rank(mapped)
    for pat, rank in _TITLE_PREFIX_TO_RANK:
        if pat.search(title or ""):
            return Rank(rank)
    return Rank("otro")


_HR_NORM_ID_RE = re.compile(r"^HR-NN-(\d{4})-(\d+)-(\d+)$")
_ELI_URI_RE = re.compile(r"/eli/sluzbeni/(\d{4})/(\d+)/(\d+)(?:/|$)")
_ELI_HTML_ANCHOR_RE = re.compile(
    r"<span\s+class=['\"]key['\"]>\s*ELI\s*:\s*</span>\s*"
    r"<a[^>]*href=['\"][^'\"]*?/eli/sluzbeni/(\d{4})/(\d+)/(\d+)['\"]",
    re.IGNORECASE,
)


def _norm_id_to_eli_path(norm_id: str) -> str:
    """Return '/eli/sluzbeni/YYYY/ISSUE/ORD' for an HR-NN norm_id.

    Used to construct source URLs and to match JSON-LD @ids (which use
    the ELI URI form). Legacy 'eli/...' inputs pass through unchanged so
    older discovery caches and third-party callers keep working.
    """
    if norm_id.startswith("eli/"):
        return "/" + norm_id
    m = _HR_NORM_ID_RE.match(norm_id)
    if not m:
        return "/" + norm_id.lstrip("/")
    year, issue, act = m.groups()
    return f"/eli/sluzbeni/{year}/{issue}/{act}"


def _norm_id_to_identifier(norm_id: str) -> str:
    """Return the canonical HR-NN identifier for a norm_id.

    New norm_ids already arrive in HR-NN form; the legacy 'eli/...' form
    is accepted for back-compat with tests and older discovery caches.
    """
    if _HR_NORM_ID_RE.match(norm_id):
        return norm_id
    parts = norm_id.strip("/").split("/")
    if len(parts) >= 5 and parts[0] == "eli":
        return f"HR-NN-{parts[2]}-{parts[3]}-{parts[4]}"
    return f"HR-{norm_id.strip('/').replace('/', '-')}"


def _eli_path_to_hr_nn(path: str) -> str:
    """Convert a bare ELI path to an HR-NN identifier (non-matching paths pass through)."""
    parts = path.strip("/").split("/")
    if len(parts) >= 5 and parts[0] == "eli":
        return f"HR-NN-{parts[2]}-{parts[3]}-{parts[4]}"
    return path


def _extract_eli_from_jsonld(graph: list) -> str | None:
    """Return the first ELI path found as a Work-node @id, or None.

    Prefers a node that carries Work-level predicates (date_publication /
    type_document); falls back to any /eli/sluzbeni/Y/I/O @id in the graph.
    """
    fallback: str | None = None
    for node in graph:
        if not isinstance(node, dict):
            continue
        nid = str(node.get("@id", ""))
        m = _ELI_URI_RE.search(nid)
        if not m:
            continue
        # Skip Expression nodes (language-tagged URI ends with /hrv).
        if nid.rstrip("/").endswith("/hrv"):
            continue
        year, issue, act = m.groups()
        path = f"eli/sluzbeni/{year}/{issue}/{act}"
        if any(k.endswith("#date_publication") or k.endswith("#type_document") for k in node):
            return path
        fallback = fallback or path
    return fallback


def _extract_eli_from_html(html: str) -> str | None:
    """Return the ELI path from the detailsTable 'ELI:' anchor, or None."""
    m = _ELI_HTML_ANCHOR_RE.search(html)
    if not m:
        return None
    year, issue, act = m.groups()
    return f"eli/sluzbeni/{year}/{issue}/{act}"


# ─────────────────────────────────────────────
# Metadata parser
# ─────────────────────────────────────────────


class NarodneNovineMetadataParser(MetadataParser):
    """Parses ELI JSON-LD (2015+) with HTML detailsTable fallback (pre-2015).

    Caller convention: `data` is the JSON-LD bytes when available, or the
    HTML bytes when `get_metadata` returned b"" (pre-2015) and the fetcher
    falls back to the text response.
    """

    def parse(self, data: bytes, norm_id: str) -> NormMetadata:
        text = data.decode("utf-8", errors="replace").lstrip()
        if text.startswith("{") or text.startswith("["):
            return self._parse_jsonld(text, norm_id)
        return self._parse_html(text, norm_id)

    # ── JSON-LD branch ──

    def _parse_jsonld(self, text: str, norm_id: str) -> NormMetadata:
        payload = json.loads(text)
        graph = payload.get("@graph") if isinstance(payload, dict) else payload
        if graph is None and isinstance(payload, dict):
            graph = [payload]
        elif graph is None:
            graph = []

        # The act's canonical ELI comes from the content, not the input
        # norm_id — NN's sitemap ord occasionally disagrees with the ELI
        # ord on the act's own page.
        extracted_eli = _extract_eli_from_jsonld(graph)
        effective_norm_id = _eli_path_to_hr_nn(extracted_eli) if extracted_eli else norm_id

        work = self._primary_node(graph, effective_norm_id)
        expression = self._expression_node(graph, effective_norm_id)

        def _get(prop: str) -> Any:
            return work.get(prop) if isinstance(work, dict) else None

        def _get_expr(prop: str) -> Any:
            return expression.get(prop) if isinstance(expression, dict) else None

        # ELI uses FRBR: title lives on the Expression (Work + language),
        # temporal and relationship predicates live on the Work.
        title = _value(_get_expr("http://data.europa.eu/eli/ontology#title"))
        type_doc_raw = _value(_get("http://data.europa.eu/eli/ontology#type_document"))
        type_doc = _uri_tail(type_doc_raw)
        pub = _parse_date(_value(_get("http://data.europa.eu/eli/ontology#date_publication")))
        signed = _parse_date(_value(_get("http://data.europa.eu/eli/ontology#date_document")))
        # `passed_by` is a URI reference to a vocabulary node. The human name
        # (e.g. "Hrvatski sabor") lives on that node's rdfs:label, which NN
        # generally doesn't inline. Leave department blank when we only have
        # an opaque institution URI — the HTML detailsTable branch handles
        # this for pre-2015 acts, and downstream consumers can resolve the
        # URI if needed.
        passed_by_raw = _value(_get("http://data.europa.eu/eli/ontology#passed_by"))
        passed_by = "" if ("://" in passed_by_raw or passed_by_raw.startswith("http")) else passed_by_raw
        number = _value(_get("http://data.europa.eu/eli/ontology#number"))

        rank = _rank_from_type_and_title(type_doc, title or "")
        source_url = f"https://narodne-novine.nn.hr{_norm_id_to_eli_path(effective_norm_id)}"

        extra: list[tuple[str, str]] = []
        if number:
            extra.append(("act_number", str(number)))
        if signed:
            extra.append(("date_signed", signed.isoformat()))
        if type_doc:
            extra.append(("type_document", type_doc))
        # Preserve the raw institution URI so callers can resolve it later.
        if passed_by_raw and not passed_by:
            extra.append(("passed_by_uri", passed_by_raw))

        for prop, key in (
            ("amends", "amends"),
            ("changes", "changes"),
            ("repeals", "repeals"),
            ("basis_for", "basis_for"),
            ("transposes", "transposes_eu_directive"),
            ("is_about", "subjects"),
        ):
            vals = _values(_get(f"http://data.europa.eu/eli/ontology#{prop}"))
            if vals:
                # Normalize cross-references to canonical HR-NN identifiers so
                # they match NormMetadata.identifier of the target norm.
                #   https:/narodne-novine.nn.hr/eli/sluzbeni/2014/93/1872
                #     → HR-NN-2014-93-1872
                cleaned = [_eli_path_to_hr_nn(_strip_nn_host(v)) for v in vals]
                extra.append((key, "; ".join(cleaned)))

        resolved_title = (title or "").strip()
        return NormMetadata(
            title=resolved_title,
            short_title=resolved_title,
            identifier=_norm_id_to_identifier(effective_norm_id),
            country="hr",
            rank=rank,
            publication_date=pub or date(1900, 1, 1),
            status=NormStatus.IN_FORCE,
            department=passed_by or "",
            source=source_url,
            extra=tuple(extra),
        )

    @staticmethod
    def _primary_node(graph: list, norm_id: str) -> dict:
        """Pick the Work node whose @id ends with the norm's ELI path.

        ELI publishers sometimes emit @ids with a single-slash scheme
        ('https:/narodne-novine.nn.hr/...') rather than '//', so match
        tolerantly on the trailing path.
        """
        target = _norm_id_to_eli_path(norm_id).lstrip("/").rstrip("/")
        best: dict = {}
        for node in graph:
            if not isinstance(node, dict):
                continue
            nid = str(node.get("@id", "")).rstrip("/")
            if nid.endswith("/" + target) or nid.endswith(target):
                # Prefer the node that carries Work-level predicates.
                if any(k.endswith("#date_publication") or k.endswith("#type_document")
                       for k in node):
                    return node
                best = node or best
        return best

    @staticmethod
    def _expression_node(graph: list, norm_id: str) -> dict:
        """Pick the Expression node — Work @id + language suffix (e.g. /hrv)."""
        target = _norm_id_to_eli_path(norm_id).lstrip("/").rstrip("/")
        for node in graph:
            if not isinstance(node, dict):
                continue
            nid = str(node.get("@id", "")).rstrip("/")
            # Expression URIs add a language tag: .../ACT/hrv
            if (nid.endswith("/" + target + "/hrv") or nid.endswith(target + "/hrv")) \
                    and any(k.endswith("#title") for k in node):
                return node
        # Fallback: any node carrying #title
        for node in graph:
            if isinstance(node, dict) and any(
                k.endswith("#title") for k in node
            ):
                return node
        return {}

    # ── HTML branch (pre-2015 fallback) ──

    def _parse_html(self, html: str, norm_id: str) -> NormMetadata:
        details = _extract_details_table(html)
        h3 = _H3_CITATION_RE.search(html)
        if h3:
            _issue, _year, dd, mm, yy, title = h3.groups()
            publication = _parse_date(f"{dd}.{mm}.{yy}") or date(1900, 1, 1)
        else:
            title = details.get("Vrsta dokumenta", "").strip()
            publication = _parse_date(details.get("Datum tiskanog izdanja", ""))
            publication = publication or date(1900, 1, 1)

        # Prefer the ELI anchor from the detailsTable over the input
        # norm_id — see the JSON-LD branch for rationale.
        extracted_eli = _extract_eli_from_html(html)
        effective_norm_id = _eli_path_to_hr_nn(extracted_eli) if extracted_eli else norm_id

        type_doc = details.get("Vrsta dokumenta", "").strip()
        issuer = details.get("Donositelj", "").strip()
        rank = _rank_from_type_and_title(type_doc, title)
        source_url = f"https://narodne-novine.nn.hr{_norm_id_to_eli_path(effective_norm_id)}"

        extra: list[tuple[str, str]] = []
        act_number = details.get("Broj dokumenta u izdanju", "").strip()
        if act_number:
            extra.append(("act_number", act_number))
        if type_doc:
            extra.append(("type_document", type_doc.upper()))
        izdanje = details.get("Izdanje", "").strip()
        if izdanje:
            extra.append(("nn_issue", izdanje))

        resolved_title = (title or "").strip()
        return NormMetadata(
            title=resolved_title,
            short_title=resolved_title,
            identifier=_norm_id_to_identifier(effective_norm_id),
            country="hr",
            rank=rank,
            publication_date=publication,
            status=NormStatus.IN_FORCE,
            department=issuer,
            source=source_url,
            extra=tuple(extra),
        )


def _extract_details_table(html: str) -> dict[str, str]:
    """Parse the <table class="detailsTable"> sidebar into a dict.

    Structure on narodne-novine.nn.hr: each <tr> has a single <td> whose first
    child is <span class="key">Label:</span> followed by the value text.
    Expected rows: Dio NN, Vrsta dokumenta, Izdanje, Broj dokumenta u izdanju,
    Donositelj, Datum tiskanog izdanja, ELI.
    """
    m = re.search(
        r'<table[^>]*class="[^"]*\bdetailsTable\b[^"]*"[^>]*>(.*?)</table>',
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return {}
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", m.group(1), re.DOTALL | re.IGNORECASE)
    out: dict[str, str] = {}
    for row in rows:
        key_match = re.search(
            r"<span[^>]*class=[\"']?key[\"']?[^>]*>(.*?)</span>",
            row,
            re.DOTALL | re.IGNORECASE,
        )
        if not key_match:
            continue
        key = _strip_tags(key_match.group(1)).strip().rstrip(":")
        # Value is everything after the closing </span> up to </td>.
        rest = row[key_match.end():]
        td_end = re.search(r"</td>", rest, re.IGNORECASE)
        raw_value = rest[: td_end.start()] if td_end else rest
        value = _strip_tags(raw_value).strip()
        if key:
            out[key] = value
    return out


def _value(x: Any) -> str:
    """Extract a JSON-LD scalar value (handles @value wrappers)."""
    if x is None:
        return ""
    if isinstance(x, list):
        return _value(x[0]) if x else ""
    if isinstance(x, dict):
        return str(x.get("@value") or x.get("@id") or "")
    return str(x)


def _values(x: Any) -> list[str]:
    """Extract a list of JSON-LD values (IDs or literals), preserving order."""
    if x is None:
        return []
    if not isinstance(x, list):
        x = [x]
    out: list[str] = []
    for el in x:
        s = _value(el)
        if s:
            out.append(s)
    return out


# ─────────────────────────────────────────────
# Text parser
# ─────────────────────────────────────────────


class NarodneNovineTextParser(TextParser):
    """Parses per-act NN HTML into Block/Version/Paragraph structure.

    Strategy:
      1. Isolate the articleContent div.
      2. Strip chrome: <style>, <script>, detailsTable, metaTable, chrome <h2>s.
      3. Walk top-level elements; convert to Paragraphs with CSS classes derived
         from the source element (p/h1/h2/h3/h4/b/i/table).
      4. Recognise `Članak N` headings to emit new blocks; everything before the
         first such heading becomes a single "preamble" block.

    This is the initial scaffold — tables, bold/italic inlining, and Članak
    splitting are implemented minimally and will be refined during Step 6
    (parser tests against the 7 fixtures) and Step 7 (5/5 AI review pass).
    """

    def parse_text(self, data: bytes) -> list[Any]:
        # Some acts (notably Državni proračun / State Budget and annexes) are
        # served by NN as raw PDF bytes at the same ELI URL where HTML is
        # usually returned. We detect and dispatch by magic bytes.
        if data.startswith(b"%PDF-"):
            return self._parse_pdf(data)

        html = data.decode("utf-8", errors="replace")
        body = self._extract_body(html)
        paragraphs = self._html_to_paragraphs(body)
        paragraphs = self._mark_quoted_amendments(paragraphs)

        pub_date = self._guess_publication_date(html) or date(1900, 1, 1)
        blocks = self._split_into_blocks(paragraphs, pub_date)
        return blocks

    @staticmethod
    def _parse_pdf(data: bytes) -> list[Block]:
        """Extract a PDF-served act into a single preamble block.

        Used for State Budget (`Državni proračun`) and other large NN acts
        that publish as PDF rather than HTML. We don't attempt to detect
        `Članak` structure — budgets are tabular/narrative content without
        formal article numbering. One preamble block with the extracted
        text is honest and keeps the act visible in git history.

        The per-version `publication_date` is a placeholder — the commit
        pipeline synthesizes the bootstrap `Reform` using
        `metadata.publication_date` when `norm.reforms` is empty.
        """
        import pdfplumber

        paragraphs: list[Paragraph] = []
        _PAGE_NUM_RE = re.compile(r"^\s*\d{1,4}\s*$")
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for page in pdf.pages:
                text = page.extract_text() or ""
                for raw_line in text.splitlines():
                    line = raw_line.strip()
                    if not line or _PAGE_NUM_RE.match(line):
                        continue
                    # Collapse internal whitespace (PDF extraction often emits
                    # wide gaps where columns align). Keeps output readable.
                    line = re.sub(r"\s+", " ", line)
                    paragraphs.append(Paragraph(css_class=None, text=line))

        if not paragraphs:
            return []

        version = Version(
            norm_id="",
            publication_date=date(1900, 1, 1),
            effective_date=date(1900, 1, 1),
            paragraphs=tuple(paragraphs),
        )
        return [
            Block(
                id="preambula",
                block_type="preamble",
                title="",
                versions=(version,),
            )
        ]

    # ── quoted amending text → Markdown blockquote ──

    _GLASI_CUE_RE = re.compile(r"\bglasi\s*:\s*$", re.IGNORECASE)
    _QUOTE_OPENERS = ('"', "\u00bb", "\u201c", "\u201e")  # "  »  "  „

    @classmethod
    def _mark_quoted_amendments(cls, paragraphs: list[Paragraph]) -> list[Paragraph]:
        """Prefix quoted amending text with Markdown `> ` blockquotes.

        Croatian statutes introduce inserted text with cues like ``...koji
        glasi:`` / ``...koja glasi:`` followed by the quoted amendment.
        Well-formed sources open the quotation with ``"``, ``»``, or ``„``;
        1990-era OCR'd gazettes commonly render the opening quote as a bare
        ``-``. Both forms get rewritten as Markdown blockquotes so the
        amending text reads distinctly from the surrounding enacting clauses.
        """
        result: list[Paragraph] = []
        prev_text = ""
        for p in paragraphs:
            stripped = p.text.lstrip()
            is_quote = False
            if stripped and stripped[0] in cls._QUOTE_OPENERS:
                is_quote = True
            elif stripped.startswith("-") and cls._GLASI_CUE_RE.search(prev_text):
                is_quote = True

            if is_quote:
                quoted = "\n".join(
                    f"> {ln}" if ln.strip() else ">" for ln in p.text.split("\n")
                )
                result.append(Paragraph(css_class=p.css_class, text=quoted))
            else:
                result.append(p)
            prev_text = p.text
        return result

    # ── body extraction ──

    def _extract_body(self, html: str) -> str:
        m = _ARTICLE_CONTENT_RE.search(html)
        content = m.group(1) if m else html
        content = _STYLE_SCRIPT_RE.sub(" ", content)
        content = _DETAILS_TABLE_RE.sub(" ", content)
        content = _META_TABLE_RE.sub(" ", content)
        content = _CHROME_H2_RE.sub("", content)
        content = _CHROME_TITLE_DIV_RE.sub(" ", content)
        content = _CHROME_TITLE_SPAN_RE.sub(" ", content)
        return content

    @staticmethod
    def _guess_publication_date(html: str) -> date | None:
        m = _H3_CITATION_RE.search(html)
        if not m:
            return None
        _issue, _year, dd, mm, yy, _title = m.groups()
        return _parse_date(f"{dd}.{mm}.{yy}")

    # ── HTML → Paragraph list ──

    @staticmethod
    def _html_to_paragraphs(body: str) -> list[Paragraph]:
        """Scan flat for <p>/<h1-6>/<table> at any nesting depth.

        NN's article body wraps every Članak in its own <p class="clanak-">
        nested inside multiple outer <div>s. A top-level walker misses all of
        them (non-greedy `.*?` matches the wrong </div>). Since <p>/<h*>/<table>
        don't legally nest inside themselves, a flat scan in document order
        yields the correct paragraph stream regardless of outer div depth.
        """
        paragraphs: list[Paragraph] = []
        paragraph_re = re.compile(
            r"<(p|h1|h2|h3|h4|h5|h6|table)\b([^>]*)>(.*?)</\1>",
            re.DOTALL | re.IGNORECASE,
        )
        # Skip <p>/<h*> that are inside a <table>: they're table cell content
        # and will be rendered via _table_to_markdown instead.
        table_spans: list[tuple[int, int]] = []
        for tm in re.finditer(r"<table\b[^>]*>.*?</table>", body, re.DOTALL | re.IGNORECASE):
            table_spans.append(tm.span())

        def _in_table(pos: int) -> bool:
            return any(s <= pos < e for s, e in table_spans)

        for m in paragraph_re.finditer(body):
            tag = m.group(1).lower()
            attrs = m.group(2) or ""
            inner = m.group(3)
            css = _extract_class(attrs) or tag
            if tag == "table":
                md = _table_to_markdown(inner)
                if md:
                    paragraphs.append(Paragraph(css_class="table", text=md))
                continue
            if _in_table(m.start()):
                continue
            text = _inline_to_markdown(inner).strip()
            if not text:
                continue
            paragraphs.append(Paragraph(css_class=css, text=text))
        return paragraphs

    # ── Paragraph list → Block list ──

    @staticmethod
    def _split_into_blocks(paragraphs: list[Paragraph], pub_date: date) -> list[Block]:
        blocks: list[Block] = []
        current_id = "preambula"
        current_title = ""
        current_paras: list[Paragraph] = []

        article_re = re.compile(r"^\s*\u010clanak\s+(\d+[a-z]?)\.?\b", re.IGNORECASE)

        def flush() -> None:
            if not current_paras:
                return
            version = Version(
                norm_id="",
                publication_date=pub_date,
                effective_date=pub_date,
                paragraphs=tuple(current_paras),
            )
            blocks.append(
                Block(
                    id=current_id,
                    block_type="article" if current_id != "preambula" else "preamble",
                    title=current_title,
                    versions=(version,),
                )
            )

        for p in paragraphs:
            m = article_re.match(p.text)
            if m:
                flush()
                # Re-class the "Članak N." marker as an h3 heading so the
                # renderer emits `### Članak N.` instead of a plain paragraph.
                heading = Paragraph(css_class="h3", text=p.text)
                current_paras = [heading]
                current_id = f"clanak-{m.group(1).lower()}"
                current_title = p.text.strip()
            else:
                current_paras.append(p)
        flush()
        return blocks


# ─────────────────────────────────────────────
# Inline + table helpers
# ─────────────────────────────────────────────


def _extract_class(attrs: str) -> str:
    m = re.search(r'class="([^"]+)"', attrs)
    if not m:
        return ""
    return m.group(1).split()[0] if m.group(1).strip() else ""


def _inline_to_markdown(html: str) -> str:
    """Convert inline HTML to Markdown: <b>/<strong> → **, <i>/<em> → *.

    Drops images (we explicitly do not handle binary assets yet).
    Collapses whitespace.
    """
    text = re.sub(r"<img\b[^>]*>", "", html, flags=re.IGNORECASE)
    text = re.sub(r"<(b|strong)\b[^>]*>(.*?)</\1>", r"**\2**", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<(i|em)\b[^>]*>(.*?)</\1>", r"*\2*", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    # Normalise line endings before whitespace collapsing so stray \r from
    # the source HTML doesn't leak into the committed Markdown (Unix-only).
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    # Strip trailing whitespace on each line (Step 7 hygiene check).
    text = re.sub(r"[ \t]+(?=\n)", "", text)
    text = re.sub(r"\n{2,}", "\n\n", text).strip()
    return text


def _table_to_markdown(inner: str) -> str:
    """Convert a <table> body to a Markdown pipe table."""
    rows = re.findall(r"<tr\b[^>]*>(.*?)</tr>", inner, re.DOTALL | re.IGNORECASE)
    parsed: list[list[str]] = []
    for row in rows:
        cells = re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", row, re.DOTALL | re.IGNORECASE)
        parsed_row = [_inline_to_markdown(c).replace("\n", " ").replace("|", "\\|") for c in cells]
        if parsed_row:
            parsed.append(parsed_row)
    if not parsed:
        return ""
    width = max(len(r) for r in parsed)
    for r in parsed:
        while len(r) < width:
            r.append("")
    lines = ["| " + " | ".join(parsed[0]) + " |"]
    lines.append("| " + " | ".join(["---"] * width) + " |")
    for r in parsed[1:]:
        lines.append("| " + " | ".join(r) + " |")
    return "\n".join(lines)


def _strip_tags(html: str) -> str:
    text = re.sub(r"<[^>]+>", " ", html)
    text = unescape(text)
    return re.sub(r"\s+", " ", text).strip()


# Re-export for convenience
__all__ = ["NarodneNovineMetadataParser", "NarodneNovineTextParser"]
