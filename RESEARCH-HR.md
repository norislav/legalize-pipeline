# RESEARCH-HR.md — Croatia (Narodne novine)

## §0.1 Source identification

**Portal:** [narodne-novine.nn.hr](https://narodne-novine.nn.hr) — Narodne novine d.d.,
the official gazette of the Republic of Croatia. Sole official publisher of Croatian
legislation. Main search at `/search.aspx`; legislation accessed via per-act pages.

**License justification for redistribution:** Croatian Copyright Act (Zakon o autorskom
pravu i srodnim pravima, NN 111/2021), **Article 18(3)**:

> "Službeni tekstovi iz područja zakonodavstva, uprave i sudstva, kao što su zakoni,
> uredbe, odluke, izvješća, zapisnici, sudske odluke i slično … U trenutku kad budu
> … objavljeni radi službenog informiranja javnosti, prestaju biti zaštićeni
> autorskim pravom."

Translation: "Official texts in legislation, administration, and judiciary (laws,
regulations, decisions, reports, minutes, court decisions, etc.)… once published for
official public information, cease to be protected by copyright."

NN's site-wide footer ("All content is copyright protected") is overbroad relative to
the statutory carve-out. We redistribute only the law text and the metadata strictly
needed to describe it; we do not redistribute NN's editorial annotations, site
chrome, or commercial search services.

**Technical operator:** Narodne novine d.d. (a state-owned joint-stock company).

## §0.1a APIs and data access

### A. Per-act HTML page — primary text source

```
https://narodne-novine.nn.hr/clanci/sluzbeni/{YYYY}_{MM}_{ISSUE}_{ACT}.html
```

Works for all acts from **1990 onward**. Returns a full HTML document containing:
- Law text wrapped in `<div class="articleContent">` … `</div>`
- A `<h3>` heading with the canonical citation: `NN {issue}/{year} ({dd.mm.yyyy.}), {title}`
- A metadata sidebar `<table class="detailsTable">` with 7 key/value rows (see
  §0.3 metadata inventory)
- Site chrome (header, navigation, `Opći uvjeti korištenja` / `Zaštita privatnosti`
  footer `<h2>`s — must be stripped)

### B. ELI URI — parallel identifier

```
https://narodne-novine.nn.hr/eli/sluzbeni/{YYYY}/{ISSUE}/{ACT}
```

Same page as (A). ELI URIs are deterministic and are the preferred canonical form.

### C. ELI JSON-LD — machine-readable relationships (2015+ only)

```
https://narodne-novine.nn.hr/eli/sluzbeni/{YYYY}/{ISSUE}/{ACT}/json-ld
```

Returns RDF JSON-LD per ELI ontology 1.3. Available for acts **from 2015 onward** (mid-
2022 rollout, backfilled to 2015). Pre-2015 returns 404. See §0.3 for the predicates
actually observed.

### D. ELI RDF/XML — same relationships, alternative format

```
https://narodne-novine.nn.hr/eli/sluzbeni/{YYYY}/{ISSUE}/{ACT}/rdf
```

Not used by this fetcher (JSON-LD is sufficient).

### E. Sitemaps — discovery

```
https://narodne-novine.nn.hr/sitemap.xml                 → index of per-issue sitemaps
https://narodne-novine.nn.hr/sitemap_{PART}_{YYYY}_{ISSUE}.xml  → URLs with lastmod
```

Cascading XML sitemaps, standard format. Covers all NN editions.

### F. PDF — alternative format

```
https://narodne-novine.nn.hr/eli/sluzbeni/{YYYY}/{ISSUE}/pdf   → full issue PDF
```

Full-issue PDFs from 2023 onward. Selective issues 1990–2022. Not needed for v1 —
HTML is the primary text and covers everything.

### Licensing / auth / rate limits

- **Auth:** none. Public, anonymous, free.
- **Rate limit:** NN's data-access page states "max 3 queries per second". We respect it.
- **robots.txt** (fetched 2026-04-19): `User-agent: *` with a long list of specific
  per-URL `Disallow:` lines (~180 entries targeting individual `/clanci/sluzbeni/YYYY_MM_II_AAAA.html`
  pages, the entire `/clanci/oglasi/` announcements branch, and one parameterised
  `/search.aspx?kategorija=3` combination). **No blanket disallow of `/clanci/sluzbeni/`**
  and no restriction on `/eli/` or `/sitemap*.xml`. We respect the per-URL exclusions
  by filtering the discovered URL set through the robots.txt block list; the
  sitemap-driven crawl otherwise proceeds freely.
- **User-Agent:** send a polite UA — `legalize-bot/1.0 (+https://github.com/legalize-dev/legalize)`.

## §0.1b Estimated scope and cadence

Estimated v1 norm count (Ustav + Zakoni + Uredbe): **~3,000–5,000 acts**. Refined in §0.6.

Daily cadence: NN publishes typically 3–7 issues per week, each issue containing
5–200 acts (many are appointments, tenders, and court decisions that fall outside v1
scope). Expected new primary-legislation events per week: 5–30.

## §0.2 Fixtures saved

Seven fixtures at `tests/fixtures/hr/`:

| Slug | NN | Role |
|---|---|---|
| `sample-constitution-procisceni-2010` | 85/2010 | Ustav consolidated text, pre-2015, preamble-chain test |
| `sample-code-obvezni-odnosi-2005` | 35/2005 | Law of Obligations — large code (1 MB), pre-2015 |
| `sample-zakon-radu-2014` | 93/2014 | Labour Act (original), pre-2015, amended post-2015 |
| `sample-amendment-radu-2022` | 151/2022 | Labour Act amendment, post-2015 with JSON-LD |
| `sample-autorsko-pravo-2021` | 111/2021 | Copyright Act, post-2015, EU-directive transposition |
| `sample-uredba-radnih-mjesta-2023` | 26/2023 | Uredba example, post-2015 |
| `sample-pdv-2013` | 73/2013 | VAT Act, pre-2015, has 42-row tariff table |

Each fixture has a `.html` file; post-2015 acts additionally have a `.json-ld` file.
`_fetch_log.json` records fetch status. `_fetch_fixtures.py` regenerates the set.

## §0.3 Metadata inventory

### From ELI JSON-LD (post-2015 only, predicates under `http://data.europa.eu/eli/ontology#`)

| Predicate | Example | Maps to | Notes |
|---|---|---|---|
| `title` | "Zakon o izmjenama i dopunama Zakona o radu" | `NormMetadata.title` | |
| `number` | "2343" | `extra.act_number` | within-issue sequence |
| `type_document` | "ZAKON" / "UREDBA" / "OSTALO" | `NormMetadata.rank` | enum; see list below |
| `date_document` | "2022-12-16" | `extra.date_signed` | date adopted by Sabor |
| `date_publication` | "2022-12-22" | `NormMetadata.publication_date` | NN gazette date, authoritative |
| `passed_by` | "Hrvatski sabor" / "Vlada RH" | `NormMetadata.issuing_body` | |
| `publisher` | "Narodne novine" | (fixed) | skip |
| `language` | "hrv" | `NormMetadata.language` | ISO 639-3 |
| `amends` | ELI URI of base act | `extra.amends` (list) | per-act |
| `changes` | ELI URI (duplicate of `amends` in practice) | `extra.changes` | usually same as amends |
| `repeals` | ELI URI | `extra.repeals` | |
| `related_to` | ELI URI | `extra.related_to` | weak link |
| `basis_for` | ELI URI (of implementing reg) | `extra.basis_for` | forward |
| `is_about` | concept URI | `extra.subjects` | Eurovoc-like |
| `transposes` | EU directive URI | `extra.transposes_eu_directive` | nice-to-have |
| `transposed_by` | EU directive URI | `extra.transposed_by` | |
| `format` / `embodies` / `is_embodied_by` / `realizes` / `is_realized_by` | (FRBR plumbing) | skip | ELI FRBR structure |

### NOT populated by NN (documented but absent in practice)

- `consolidates` / `consolidated_by` — pročišćeni tekst acts are not linked back to
  their constituents via ELI. Confirmed with Labour Act and Copyright Act tests.
- `amended_by` / `changed_by` / `repealed_by` / `corrects` / `corrected_by` — inverse
  relations not observed on 3 post-2015 acts. Discovery must walk forward edges only.
- `first_date_entry_in_force` — NN's own docs flag this as "pending".

### From HTML `<h3>` heading (works 1990+)

```
<h3>NN 93/2014 (30.7.2014.), Zakon o radu</h3>
```

Regex `NN (\d+)/(\d{2,4}) \((\d{1,2})\.(\d{1,2})\.(\d{4})\.\), (.+)` gives issue, year,
publication day/month/year, and title. Authoritative and universal.

### From HTML `<table class="detailsTable">` sidebar (works 1990+)

Every NN page has a 7-row key/value table:

| Croatian key | English | Example |
|---|---|---|
| Dio NN | NN part | Službeni / Međunarodni |
| Vrsta dokumenta | Document type | Zakon / Uredba / Pravilnik / Odluka / Rješenje |
| Izdanje | Issue | NN 93/2014 |
| Broj dokumenta u izdanju | Document number in issue | 1872 |
| Donositelj | Issuer | Hrvatski sabor / Vlada RH / ministry / ... |
| Datum tiskanog izdanja | Publication date | 30.7.2014. |
| ELI | ELI URI | /eli/sluzbeni/2014/93/1872 |

**This is the canonical fallback metadata source for pre-2015 acts.** Parse it as the
primary metadata source and cross-check against JSON-LD when available.

### Document-type (`Vrsta dokumenta` / `type_document`) values observed

`ZAKON`, `UREDBA`, `OSTALO` (catch-all for pravilnici, odluke, naredbe, rješenja).
Finer distinction comes from the title prefix (`Pravilnik o…`, `Odluka o…`,
`Rješenje…`, `Naredba o…`).

Croatian legal hierarchy used for `NormMetadata.rank`:

| rank value | Croatian type | Issuer |
|---|---|---|
| `ustav` | Ustav | Sabor (constitutional amendment) |
| `zakon` | Zakon / Zakonik / Kodeks | Hrvatski sabor |
| `uredba` | Uredba | Vlada RH (government) |
| `pravilnik` | Pravilnik | ministry |
| `odluka` | Odluka | various |
| `naredba` | Naredba | various |
| `rjesenje` | Rješenje | various |

v1 scope = `ustav` + `zakon` + `uredba`.

## §0.4 Formatting inventory

Observed across the 7 fixtures:

- [x] **Article markers** — every law uses `Članak N` as article-heading text.
      Classes observed: `clanak`, `clanak-`. 1,165 occurrences in the Obligations
      Act alone. **Must be preserved as a Markdown heading** (e.g., `### Članak N`).
- [x] **Article sub-titles** — italics (`<i>…</i>`) above articles in newer drafting
      style (e.g., "Predmet Zakona", "Rodna jednakost" in the Labour Act).
      Preserve as `*italic*` in output.
- [x] **Tables** — rare in primary legislation (Labour Act, Obligations Act, Ustav
      all have zero content tables) but PRESENT in tax/tariff codes (VAT Act has
      a 42-row KN-classification table). **Must render as Markdown pipe tables.**
      Pattern: `<table>` without `class="detailsTable"` or `class="metaTable"` is
      content; with those classes is chrome (to skip).
- [x] **Bold** — sparingly used (`<b>` 3–13 per act, often article numbers). Preserve
      as `**bold**`.
- [x] **Italic** — heavy use (`<i>`: up to 229 in Labour Act). Preserve as `*italic*`.
- [x] **Glagoljica** — a CSS class `glagoljica` appears; NN uses this for headings
      printed in Glagolitic script in certain ceremonial acts (e.g., the Ustav
      preamble). Represent as the displayed text only (NN's Glagolitic is decorative).
- [ ] **Lists** — `<ol>/<ul>` zero occurrences. Enumerated items are rendered as
      plain paragraphs with inline numbering (e.g., "1. …", "(a) …"). Preserve
      literal numbering in the text.
- [ ] **Images** — 7–11 `<img>` per page, **all site chrome** (logos, icons). Drop;
      count for `extra.images_dropped = 0` (no content images expected).
- [ ] **Footnotes** — not observed in the sample. May appear in annexes; revisit
      during parser work.
- [x] **Cross-references / Links** — inline text like "članka 4. ovoga Zakona" or
      links to other NN URIs. Preserve link text; in-law references stay as plain
      text (they target structure within the same document).
- [x] **Blockquotes for amended text** — an amending act typically renders the
      new/replaced text inline without explicit blockquote markup. Matches Belgium
      more than Spain. To verify in parser phase.
- [ ] **Formulas** — not observed in the 7-fixture sample. Croatian tax, environmental,
      and labour regulations occasionally render formulas (e.g., indexation factors
      in pension law) as inline text with `×`, `÷`, Greek letters rather than MathML
      or images. Treat as plain text until a counter-example surfaces; revisit in
      parser phase if broken-out formulas appear.
- [ ] **Attachments / annexes (Prilog / Dodatak)** — not hit in the 7-fixture sample,
      but NN acts routinely have an "Obrazac" (form) or "Prilog" (annex) section
      appended. These may include tables, diagrams (as `<img>`, which we skip), or
      coded enumerations. The parser must preserve `<h2>/<h3>` Prilog headings as
      regular sub-sections and keep annex tables in Markdown. Confirm during 50-law
      benchmark in Step 8.
- [ ] **Signatories** — every act ends with a signature block: issuing body + name +
      place/date. Example: "Predsjednik / Hrvatskoga sabora / Gordan Jandroković, v. r.
      / Klasa: …, Urbroj: …, Zagreb, 22. prosinca 2022." The `v. r.` marker ("vlastoručno",
      i.e., "signed personally") is the canonical end-of-act signal. Render plainly;
      no distinct CSS class observed, so detect via text pattern (`v\.\s*r\.` +
      Klasa/Urbroj lines). No equivalent of the Spanish `firma_rey` class exists.

### Boilerplate to strip (universal)

- `<h2>Opći uvjeti korištenja</h2>` and `<h2>Zaštita privatnosti</h2>` — site footer
- `<table class="detailsTable">` — already extracted for metadata, not re-emitted in body
- Header nav, search bar, logo, breadcrumbs, cookie banners
- `<img>` site chrome

## §0.5 Version history spike

**Gate:** ≥2 versions extracted with dates from one law, before writing parser.
See `tests/fixtures/hr/version-spike.txt` for the literal output.

**Strategy proven:** walk pročišćeni tekst preamble citations (pre-2015 chains) AND
`amends` JSON-LD predicates (2015+ chains). Both resolve to per-act HTML pages whose
`<h3>` heading yields the exact publication date.

**Gate PASS: documented in §0.5b below + version-spike.txt artefact.**

## §0.5a Version history strategy

Per-law history reconstruction:

```
1. Discovery: sitemap enumerates all NN acts 1990+ → filter by `type_document`
   (ZAKON / UREDBA / USTAV) via either JSON-LD (2015+) or detailsTable (pre-2015)

2. For each base act (a ZAKON whose `amends` list is empty, or whose title does
   not start with "Zakon o izmjenama"):
     a. Fetch all post-2015 acts that `amends` this base → direct amendment events
     b. If a pročišćeni tekst exists for this base, parse its preamble to
        enumerate ALL predecessor citations (pre-2015 amendments included)
     c. Union (a) and (b), deduplicate by (year, issue, act_number)

3. For each amendment, fetch its HTML, extract publication date from <h3>,
   extract text diff (if full substitution: new article text; if partial: edit
   markers "U članku N stavku M briše se..." in Croatian — parser applies)

4. Emit commits chronologically, per-file:
   [bootstrap] <title>                     @ original publication date
   [izmjena]   Izmjene i dopune (NN X/YY)  @ amendment publication date
   [ispravak]  Ispravak                    @ correction date
   [prestanak] stavljanje izvan snage      @ repeal date (final, if repealed)
```

### Commit vocabulary (Croatian, from NN's own terminology)

| Event | Tag | NN source term |
|---|---|---|
| Bootstrap (internal) | `[bootstrap]` | — |
| New law | `[novo]` | "Zakon o…" (title prefix only) |
| Amendment | `[izmjena]` | "Zakon o izmjenama i dopunama…" |
| Correction | `[ispravak]` | "Ispravak Zakona o…" |
| Repeal | `[prestanak]` | "Zakon o prestanku važenja…" / "stavlja se izvan snage" |
| Pipeline fix (internal) | `[fix-pipeline]` | — |

### Edge cases

- **Pre-2015 law with no 2015+ amendment AND no pročišćeni tekst:** history reduces
  to single `[bootstrap]` commit. Estimated <5% of active laws; confirm in §0.6.
- **Pročišćeni tekst with noisy preamble:** large codes (Obligations Act: 1 MB)
  cite many other laws in body text. Mitigation: scope citation extraction to the
  first `<p>` paragraph(s) inside `<div class="articleContent">`, before the first
  `<h2>` or `Članak 1` marker. Test in parser phase.
- **Sabor-published vs NN-published pročišćeni tekst:** some are `Urednički pročišćeni
  tekst` (editorial) vs `Pročišćeni tekst` (official). Both list the predecessor
  chain; source distinction goes in `extra.consolidation_source`.

## §0.5b Version spike result

See `tests/fixtures/hr/version-spike.txt` — generated by `_version_spike.py`.

**Law tested:** Ustav Republike Hrvatske.

**Chain recovered from NN 85/2010 (pročišćeni tekst) preamble (12 tuples):**
`56/90, 135/97, 8/98, 113/2000, 124/2000, 28/2001, 41/2001, 55/2001, 76/2010, 2/10,
1/01`, plus the self-reference `85/2010`. Covers every known Ustav amendment from
1990 through 2010.

**Resolved versions (full text + dates proven):**

```
version 1: date 1990-12-22, 705 paragraphs  (NN 56/1990, 'Ustav Republike Hrvatske')
version 2: date 2010-06-18, 177 paragraphs  (NN 76/2010, 'Promjena Ustava Republike Hrvatske')
```

Text excerpts are included in the spike output, proving that the per-act HTML's
`articleContent` div yields readable paragraph content (not just heading metadata).
Gate requirement — "≥2 versions with effective date + full text + stable identifier"
— is satisfied for the Ustav chain. **GATE: PASS.**

## §0.6 Scope estimate

**Sitemap-measured counts (fetched 2026-04-19):**

```
Root sitemap.xml   : 9,620 sub-sitemap entries
  part=1 (Službeni dio, official legislation)  : 5,039
  part=2 (Međunarodni dio, international)      :   405
  part=3 (Oglasni dio, announcements/tenders)  : 4,175
Years covered      : 1990 – 2026

Issues per year (Službeni, part=1):
  1990 :  59      2015 : 290       2024 : 267
  2000 : 279      2023 : 276       2025 : 272

Per-issue act count (samples):
  1995/109 : 12 acts     2015/141 : 25 acts     2023/158 : 28 acts
```

**Derived estimates:**

- Total acts ever published in NN Službeni: 5,039 issues × ~20 avg acts/issue
  ≈ **~100,000 historical acts**.
- Primary legislation (Ustav + Zakon + Uredba) is typically 15–25% of Službeni
  content; the rest is appointments, rješenja, judicial publications, tenders
  masquerading as acts.
- **Working v1 scope estimate: ~15,000–25,000 primary-legislation events**
  (bootstrap + amendments + corrections + repeals) → **~3,000–5,000 unique base
  laws** (the number of distinct `.md` files in the output repo).
- Bootstrap runtime projection at 2 workers × 1.5 req/s ≈ 3 req/s effective
  (respects NN's published 3 req/s ceiling): ~20K events × ~2 HTTP requests each
  (HTML + JSON-LD where available) ≈ 40K requests ÷ 3 req/s ≈ **4 hours fetch,
  +1–2 h parse + commits ≈ 5–6 hours total bootstrap**.

Refine these numbers during Step 1 once the client+discovery are wired and we
can run a real counted pass.

## §0.7 Format-coverage table

| Format | Coverage | Unique adds | v1 decision |
|---|---|---|---|
| HTML | 1990+ (~100% of primary legislation) | baseline | **covered** |
| ELI JSON-LD | 2015+ (~10–12 years of legislation) | richer metadata, no new laws | used opportunistically; HTML is truth |
| PDF (issue-level) | 2023+ full; selective earlier | 0 new acts | skipped for v1 |
| RDF/XML | same as JSON-LD | 0 new acts | skipped (JSON-LD suffices) |

**No format contributes >1% of unique laws beyond HTML.** Multi-format dispatch
not required for this country. GATE: PASS.

## Non-trivial decisions for later reference

1. **Which `type_document` → `rank` mapping?** Proposal in §0.3; revisit once we see
   a broader sample during Step 1. "OSTALO" is a dumping ground — detect the real
   rank from title prefix.
2. **Jurisdictional split?** Croatia is a unitary state. County (županija) and city
   ordinances exist but are NOT published in NN; they have their own local gazettes.
   v1 covers state level only → no subdirectory split (flat `hr/` folder, like Austria).
3. **Effective date vs publication date?** NN rarely publishes an entry-into-force
   date as separate metadata. Use `date_publication` (`datum tiskanog izdanja`) as
   `GIT_AUTHOR_DATE` — matches the gazette date, which is the citation-canonical date
   in Croatian legal practice. If a specific entry-into-force date appears in the
   act text (e.g., "ovaj Zakon stupa na snagu …"), capture it to `extra.entry_into_force`
   but still use publication date for the commit timestamp.

## Open questions (to resolve before Step 1)

- How often do Croatian laws use formal footnotes vs inline parentheticals? (Sample
  didn't hit any — re-test with 50-law benchmark in Step 8.)
- Are all amending acts' `amends` targets single (one base) or can one amending act
  amend multiple bases in one go? (Seen: single in the Labour Act fixture. Unknown
  for omnibus amendments.)
- Does NN have any Akoma Ntoso exposure we've missed? (Ran 3 searches, none found.
  Confirmed absent for now.)
