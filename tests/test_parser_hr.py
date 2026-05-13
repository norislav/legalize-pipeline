"""Tests for the Narodne novine (HR) parser.

Fixtures cover the two metadata paths:

- JSON-LD branch (2015+ acts):
    sample-amendment-radu-2022.{html,json-ld}        — Zakon o izmjenama
    sample-autorsko-pravo-2021.{html,json-ld}        — large Zakon
    sample-uredba-radnih-mjesta-2023.{html,json-ld}  — small Uredba

- HTML detailsTable fallback (pre-2015 acts):
    sample-constitution-procisceni-2010.html         — Ustav (pročišćeni)
    sample-code-obvezni-odnosi-2005.html             — ZOO (biggest fixture)
    sample-pdv-2013.html                             — Zakon o PDV
    sample-zakon-radu-2014.html                      — Zakon o radu (original)
    sample-uredba-radna-mjesta-2001.html             — Uredba by Vlada
    sample-act-2010-62-1979.html                     — Pravilnik by a Ministry
    sample-act-2003-167-2399.html                    — 2003 Zakon o autorskom pravu
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from legalize.countries import get_metadata_parser, get_text_parser
from legalize.fetcher.hr.parser import (
    NarodneNovineMetadataParser,
    NarodneNovineTextParser,
)
from legalize.models import NormStatus
from legalize.transformer.markdown import render_norm_at_date


FIXTURES = Path(__file__).parent / "fixtures" / "hr"


def _read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


# ─────────────────────────────────────────────
# JSON-LD branch (2015+)
# ─────────────────────────────────────────────


class TestMetadataAmendmentJsonLd:
    """2022 amendment of Zakon o radu — rich ELI JSON-LD."""

    norm_id = "HR-NN-2022-151-2343"

    @pytest.fixture
    def metadata(self):
        return NarodneNovineMetadataParser().parse(
            _read("sample-amendment-radu-2022.json-ld"), self.norm_id
        )

    def test_identifier(self, metadata):
        assert metadata.identifier == "HR-NN-2022-151-2343"

    def test_country(self, metadata):
        assert metadata.country == "hr"

    def test_title(self, metadata):
        assert metadata.title == "Zakon o izmjenama i dopunama Zakona o radu"

    def test_rank(self, metadata):
        assert metadata.rank == "zakon"

    def test_publication_date(self, metadata):
        assert metadata.publication_date == date(2022, 12, 22)

    def test_status(self, metadata):
        assert metadata.status == NormStatus.IN_FORCE

    def test_source_url(self, metadata):
        assert metadata.source == (
            "https://narodne-novine.nn.hr/eli/sluzbeni/2022/151/2343"
        )

    def test_extra_type_document_stripped_to_token(self, metadata):
        extra = dict(metadata.extra)
        assert extra.get("type_document") == "ZAKON"

    def test_extra_act_number(self, metadata):
        extra = dict(metadata.extra)
        assert extra.get("act_number") == "2343"

    def test_extra_date_signed(self, metadata):
        extra = dict(metadata.extra)
        assert extra.get("date_signed") == "2022-12-16"

    def test_extra_amends_as_hr_nn_identifier(self, metadata):
        extra = dict(metadata.extra)
        assert "HR-NN-2014-93-1872" in (extra.get("amends") or "")

    def test_extra_passed_by_uri_preserved(self, metadata):
        # URI can't be resolved to a human name inline — keep the reference.
        extra = dict(metadata.extra)
        assert "nn-institutions" in (extra.get("passed_by_uri") or "")


class TestMetadataAutorskoPravoJsonLd:
    """Large Zakon with repeals + basis_for + transposes predicates."""

    norm_id = "HR-NN-2021-111-1941"

    @pytest.fixture
    def metadata(self):
        return NarodneNovineMetadataParser().parse(
            _read("sample-autorsko-pravo-2021.json-ld"), self.norm_id
        )

    def test_title(self, metadata):
        assert metadata.title == "Zakon o autorskom pravu i srodnim pravima"

    def test_rank_is_zakon(self, metadata):
        assert metadata.rank == "zakon"

    def test_publication_date(self, metadata):
        assert metadata.publication_date == date(2021, 10, 14)

    def test_repeals_stored_as_hr_nn_identifier(self, metadata):
        extra = dict(metadata.extra)
        assert "HR-NN-2003-167-2399" in (extra.get("repeals") or "")

    def test_basis_for_captured(self, metadata):
        extra = dict(metadata.extra)
        val = extra.get("basis_for") or ""
        assert "HR-NN-2022-" in val

    def test_transposes_eu_directive_captured(self, metadata):
        extra = dict(metadata.extra)
        assert "dir/1993/83" in (extra.get("transposes_eu_directive") or "")


class TestMetadataUredbaJsonLd:
    """Small Uredba — confirms rank=uredba via type_document."""

    norm_id = "HR-NN-2023-26-414"

    @pytest.fixture
    def metadata(self):
        return NarodneNovineMetadataParser().parse(
            _read("sample-uredba-radnih-mjesta-2023.json-ld"), self.norm_id
        )

    def test_rank_is_uredba(self, metadata):
        assert metadata.rank == "uredba"

    def test_type_document_is_uredba(self, metadata):
        extra = dict(metadata.extra)
        assert extra.get("type_document") == "UREDBA"

    def test_publication_date(self, metadata):
        assert metadata.publication_date == date(2023, 3, 3)


# ─────────────────────────────────────────────
# HTML detailsTable fallback (pre-2015)
# ─────────────────────────────────────────────


class TestMetadataZakonORaduHtml:
    """Pre-2015 Zakon o radu — HTML detailsTable fallback."""

    norm_id = "HR-NN-2014-93-1872"

    @pytest.fixture
    def metadata(self):
        return NarodneNovineMetadataParser().parse(
            _read("sample-zakon-radu-2014.html"), self.norm_id
        )

    def test_identifier(self, metadata):
        assert metadata.identifier == "HR-NN-2014-93-1872"

    def test_title_from_h3(self, metadata):
        assert metadata.title == "Zakon o radu"

    def test_rank(self, metadata):
        assert metadata.rank == "zakon"

    def test_publication_from_h3(self, metadata):
        assert metadata.publication_date == date(2014, 7, 30)

    def test_department_from_detailstable(self, metadata):
        assert metadata.department == "Hrvatski sabor"

    def test_extra_nn_issue(self, metadata):
        extra = dict(metadata.extra)
        assert extra.get("nn_issue") == "NN 93/2014"


class TestMetadataUstavHtml:
    """Pre-2015 Ustav pročišćeni tekst — rank via title prefix."""

    norm_id = "HR-NN-2010-85-2422"

    @pytest.fixture
    def metadata(self):
        return NarodneNovineMetadataParser().parse(
            _read("sample-constitution-procisceni-2010.html"), self.norm_id
        )

    def test_rank_is_ustav(self, metadata):
        assert metadata.rank == "ustav"

    def test_title(self, metadata):
        assert metadata.title == "Ustav Republike Hrvatske (pročišćeni tekst)"

    def test_publication(self, metadata):
        assert metadata.publication_date == date(2010, 7, 9)

    def test_department(self, metadata):
        assert "Odbor za Ustav" in metadata.department


class TestMetadataObvezniOdnosiHtml:
    """Zakon o obveznim odnosima 2005 — the largest fixture (~1165 articles)."""

    norm_id = "HR-NN-2005-35-707"

    @pytest.fixture
    def metadata(self):
        return NarodneNovineMetadataParser().parse(
            _read("sample-code-obvezni-odnosi-2005.html"), self.norm_id
        )

    def test_identifier(self, metadata):
        assert metadata.identifier == "HR-NN-2005-35-707"

    def test_title(self, metadata):
        assert metadata.title == "Zakon o obveznim odnosima"

    def test_rank(self, metadata):
        assert metadata.rank == "zakon"

    def test_publication(self, metadata):
        assert metadata.publication_date == date(2005, 3, 17)

    def test_department(self, metadata):
        assert metadata.department == "Hrvatski sabor"

    def test_extra_nn_issue(self, metadata):
        assert dict(metadata.extra).get("nn_issue") == "NN 35/2005"


class TestMetadataPdvHtml:
    """Zakon o PDV 2013 — pre-2015 tax law."""

    norm_id = "HR-NN-2013-73-1451"

    @pytest.fixture
    def metadata(self):
        return NarodneNovineMetadataParser().parse(
            _read("sample-pdv-2013.html"), self.norm_id
        )

    def test_title(self, metadata):
        assert metadata.title == "Zakon o porezu na dodanu vrijednost"

    def test_rank(self, metadata):
        assert metadata.rank == "zakon"

    def test_publication(self, metadata):
        assert metadata.publication_date == date(2013, 6, 18)

    def test_department(self, metadata):
        assert metadata.department == "Hrvatski sabor"


class TestMetadataUredba2001Html:
    """2001 Uredba issued by Vlada — first fixture with non-Sabor department."""

    norm_id = "HR-NN-2001-37-644"

    @pytest.fixture
    def metadata(self):
        return NarodneNovineMetadataParser().parse(
            _read("sample-uredba-radna-mjesta-2001.html"), self.norm_id
        )

    def test_rank_is_uredba(self, metadata):
        assert metadata.rank == "uredba"

    def test_title_starts_with_uredba(self, metadata):
        assert metadata.title.lower().startswith("uredba")

    def test_publication(self, metadata):
        assert metadata.publication_date == date(2001, 4, 25)

    def test_department_is_vlada(self, metadata):
        assert "Vlada" in metadata.department

    def test_extra_type_document(self, metadata):
        assert dict(metadata.extra).get("type_document") == "UREDBA"


class TestMetadataPravilnik2010Html:
    """2010 Pravilnik issued by a Ministry — exercises pravilnik rank."""

    norm_id = "HR-NN-2010-62-1979"

    @pytest.fixture
    def metadata(self):
        return NarodneNovineMetadataParser().parse(
            _read("sample-act-2010-62-1979.html"), self.norm_id
        )

    def test_rank_is_pravilnik(self, metadata):
        assert metadata.rank == "pravilnik"

    def test_title_starts_with_pravilnik(self, metadata):
        assert metadata.title.lower().startswith("pravilnik")

    def test_department_is_ministry(self, metadata):
        assert "MINISTARSTVO" in metadata.department.upper()

    def test_publication(self, metadata):
        assert metadata.publication_date == date(2010, 5, 21)


class TestMetadataAutorskoPravo2003Html:
    """2003 predecessor of the 2021 Copyright Act — repealed by it."""

    norm_id = "HR-NN-2003-167-2399"

    @pytest.fixture
    def metadata(self):
        return NarodneNovineMetadataParser().parse(
            _read("sample-act-2003-167-2399.html"), self.norm_id
        )

    def test_identifier(self, metadata):
        assert metadata.identifier == "HR-NN-2003-167-2399"

    def test_title(self, metadata):
        assert metadata.title == "Zakon o autorskom pravu i srodnim pravima"

    def test_rank(self, metadata):
        assert metadata.rank == "zakon"

    def test_publication(self, metadata):
        assert metadata.publication_date == date(2003, 10, 22)

    def test_department(self, metadata):
        assert metadata.department == "Hrvatski sabor"


# ─────────────────────────────────────────────
# Text structure
# ─────────────────────────────────────────────


class TestTextZakonORadu:
    """Structural parse of Zakon o radu 2014."""

    @pytest.fixture
    def blocks(self):
        return NarodneNovineTextParser().parse_text(
            _read("sample-zakon-radu-2014.html")
        )

    def test_first_block_is_preamble(self, blocks):
        assert blocks[0].block_type == "preamble"

    def test_has_many_articles(self, blocks):
        # Zakon o radu 2014 has 235 Članaks.
        articles = [b for b in blocks if b.block_type == "article"]
        assert len(articles) >= 230

    def test_article_titles_start_with_clanak(self, blocks):
        articles = [b for b in blocks if b.block_type == "article"]
        normalized = articles[0].title.replace("\n", " ").strip()
        assert normalized.startswith("Članak")

    def test_article_ids_are_stable_slugs(self, blocks):
        articles = [b for b in blocks if b.block_type == "article"]
        assert articles[0].id == "clanak-1"

    def test_version_is_publication_dated(self, blocks):
        articles = [b for b in blocks if b.block_type == "article"]
        v = articles[0].versions[0]
        assert v.publication_date == date(2014, 7, 30)
        assert v.effective_date == v.publication_date


class TestTextObvezniOdnosi:
    """Stress test: Zakon o obveznim odnosima — largest fixture (~1165 arts)."""

    @pytest.fixture
    def blocks(self):
        return NarodneNovineTextParser().parse_text(
            _read("sample-code-obvezni-odnosi-2005.html")
        )

    def test_over_thousand_articles(self, blocks):
        articles = [b for b in blocks if b.block_type == "article"]
        assert len(articles) > 1000


class TestTextUstav:
    """Ustav has exactly 152 articles in the 2010 pročišćeni tekst."""

    def test_article_count(self):
        blocks = NarodneNovineTextParser().parse_text(
            _read("sample-constitution-procisceni-2010.html")
        )
        articles = [b for b in blocks if b.block_type == "article"]
        # Allow a small margin — we care that it's not 1 (old bug) and not 0.
        assert 140 <= len(articles) <= 160


class TestTextPdv:
    """Zakon o PDV 2013 — pre-2015 HTML, ~143 articles."""

    def test_article_count(self):
        blocks = NarodneNovineTextParser().parse_text(_read("sample-pdv-2013.html"))
        articles = [b for b in blocks if b.block_type == "article"]
        assert 120 <= len(articles) <= 160


class TestTextUredba2001:
    """2001 Uredba — ~29 articles."""

    def test_parse_yields_articles(self):
        blocks = NarodneNovineTextParser().parse_text(
            _read("sample-uredba-radna-mjesta-2001.html")
        )
        articles = [b for b in blocks if b.block_type == "article"]
        assert 20 <= len(articles) <= 40
        assert blocks[0].block_type == "preamble"


class TestTextAutorskoPravo2003:
    """2003 Copyright Act — 208 articles in original enactment."""

    def test_article_count(self):
        blocks = NarodneNovineTextParser().parse_text(
            _read("sample-act-2003-167-2399.html")
        )
        articles = [b for b in blocks if b.block_type == "article"]
        assert 180 <= len(articles) <= 230


# ─────────────────────────────────────────────
# PDF branch (State Budget acts)
# ─────────────────────────────────────────────


class TestTextPdfBranch:
    """PDF-served acts: parser should detect %PDF- magic bytes and produce a
    single preamble block with the extracted text."""

    def test_pdf_yields_preamble_block(self):
        data = _read("sample-budget-excerpt.pdf")
        assert data.startswith(b"%PDF-")
        blocks = NarodneNovineTextParser().parse_text(data)
        assert len(blocks) == 1
        b = blocks[0]
        assert b.block_type == "preamble"
        assert b.id == "preambula"
        texts = [p.text for p in b.versions[0].paragraphs]
        assert any("DRZAVNI PRORACUN" in t for t in texts)

    def test_pdf_branch_does_not_disturb_html_inputs(self):
        # Sanity: feeding HTML to the same parser still goes through the
        # HTML branch (no PDF magic bytes at the start).
        html = _read("sample-zakon-radu-2014.html")
        assert not html.startswith(b"%PDF-")
        blocks = NarodneNovineTextParser().parse_text(html)
        assert any(b.block_type == "article" for b in blocks)


# ─────────────────────────────────────────────
# Markdown rendering (smoke)
# ─────────────────────────────────────────────


class TestMarkdownRender:
    @pytest.fixture
    def rendered(self):
        norm_id = "HR-NN-2014-93-1872"
        data = _read("sample-zakon-radu-2014.html")
        meta = NarodneNovineMetadataParser().parse(data, norm_id)
        blocks = NarodneNovineTextParser().parse_text(data)
        return render_norm_at_date(
            meta, blocks, date(2014, 7, 30), include_all=True
        )

    def test_frontmatter_present(self, rendered):
        assert rendered.startswith("---\n")
        assert 'country: "hr"' in rendered

    def test_title_h1(self, rendered):
        assert "# Zakon o radu" in rendered

    def test_rank_in_frontmatter(self, rendered):
        assert 'rank: "zakon"' in rendered

    def test_source_url(self, rendered):
        assert "narodne-novine.nn.hr" in rendered

    def test_at_least_one_clanak_in_body(self, rendered):
        assert "Članak 1" in rendered

    def test_no_raw_html_tags_leaked(self, rendered):
        assert "<p class=" not in rendered
        assert "<div" not in rendered
        assert "<style" not in rendered


# ─────────────────────────────────────────────
# Identifier safety
# ─────────────────────────────────────────────


class TestIdentifierFilesystemSafe:
    @pytest.mark.parametrize(
        "norm_id,expected",
        [
            # New canonical form (no-op).
            ("HR-NN-2022-151-2343", "HR-NN-2022-151-2343"),
            # Legacy ELI-path inputs still accepted (back-compat).
            ("eli/sluzbeni/2022/151/2343", "HR-NN-2022-151-2343"),
            ("eli/sluzbeni/2014/93/1872", "HR-NN-2014-93-1872"),
            ("eli/sluzbeni/1990/56/1", "HR-NN-1990-56-1"),
        ],
    )
    def test_identifier_format(self, norm_id, expected):
        from legalize.fetcher.hr.parser import _norm_id_to_identifier

        ident = _norm_id_to_identifier(norm_id)
        assert ident == expected
        assert ":" not in ident
        assert " " not in ident

    def test_content_eli_overrides_input_norm_id(self):
        # When the fixture's embedded ELI disagrees with the input norm_id,
        # the parser trusts the content (the act's own canonical identity).
        data = _read("sample-zakon-radu-2014.html")
        meta = NarodneNovineMetadataParser().parse(data, "HR-NN-9999-0-0")
        assert meta.identifier == "HR-NN-2014-93-1872"


# ─────────────────────────────────────────────
# REGISTRY dispatch
# ─────────────────────────────────────────────


class TestRegistryDispatch:
    def test_text_parser(self):
        parser = get_text_parser("hr")
        assert isinstance(parser, NarodneNovineTextParser)

    def test_metadata_parser(self):
        parser = get_metadata_parser("hr")
        assert isinstance(parser, NarodneNovineMetadataParser)
