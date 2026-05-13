# HR bootstrap — step by step

The pipeline splits bootstrap into three phases that you can run
separately or in one shot:

1. **Discovery** — list every act's norm_id
2. **Fetch** — download each act's HTML + metadata, parse to JSON
3. **Commit** — render Markdown and stream into git via fast-import

Run them one by one while you're learning. Once you trust it, use the
combined `bootstrap` command.

All commands assume `cwd = C:\dev\legalize-pipeline` and these env vars
on Windows (UTF-8 mode + unbuffered output):

```bash
export PYTHONUTF8=1 PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
```

---

## Layout

```
C:\dev\
├── legalize-pipeline\              ← this repo (the engine)
└── countries\
    ├── data-hr\                    ← cache (no git, regenerable)
    │   ├── discovery_ids.txt       ← list of norm_ids
    │   └── json\
    │       └── HR-NN-2026-40-489.json   ← one per act
    └── hr\                         ← the country repo (has .git)
        └── hr\
            └── HR-NN-2026-40-489.md     ← one per act
```

**`data-hr/`** is throwaway — delete and regenerate anytime.
**`hr/`** is the output that gets pushed to `norislav/legalize-hr`.

---

## Phase 1 — Discovery

Goal: produce `../countries/data-hr/discovery_ids.txt`, a list of every
norm_id to fetch.

### Option A: let the engine do it (standard)

```bash
py -3.13 -c "from legalize.cli import cli; cli()" fetch -c hr --all --limit 0
```

`--limit 0` means "discover but don't fetch." The first call enumerates
the full NN sitemap (~56 min at 1.5 r/s — 5,040 sub-sitemaps for Part 1
since 1990) and caches the result in `discovery_ids.txt`. Subsequent
calls reuse the cache (`pipeline.py:333`).

### Option B: use diag_hr.py (fast, partial — good for validation)

```bash
py -3.13 -u diag_hr.py 600
```

Our custom seeder. Takes newest issues first, prints progress every 25
sub-sitemaps, stops at 600 IDs. **Takes ~30s instead of 56 min.** Writes
the same `discovery_ids.txt` the engine reads, so later phases don't
know the difference. Pass a bigger number (e.g. `py -3.13 diag_hr.py 15000`)
for more coverage.

### Verify

```bash
wc -l ../countries/data-hr/discovery_ids.txt
head -3 ../countries/data-hr/discovery_ids.txt
```

Expected:

```
612 ../countries/data-hr/discovery_ids.txt
eli/sluzbeni/2026/41/501
eli/sluzbeni/2026/41/502
eli/sluzbeni/2026/41/503
```

---

## Phase 2 — Fetch

Goal: for each norm_id in the discovery cache, download HTML +
metadata, parse, and save as JSON to `../countries/data-hr/json/`.
Does NOT touch git.

```bash
py -3.13 -c "from legalize.cli import cli; cli()" fetch -c hr --all --limit 500
```

Flags:
- `--limit N` — stop after N norms (for validation runs)
- `--offset N` — skip the first N (for splitting across machines)
- `--force` — re-download even if the JSON exists (otherwise cached)

Throughput: ~45 norms/min with `max_workers=2` and NN's 1.5 r/s limit
(each norm = 2 HTTP calls, so effective rate is ~1.5 r/s per worker ×
2 workers = 3 r/s, but the rate limiter shares across workers).

Progress lines look like:

```
  Processing eli/sluzbeni/2026/40/489...
  ✓ Pravilnik o izmjenama i dopuni Pravilnika o izobrazbi: 10 blocks, 1 versions
  [500/500] 500 OK, 0 errors
```

### Verify

```bash
ls ../countries/data-hr/json/ | wc -l     # count of fetched JSONs
cat ../countries/data-hr/json/HR-NN-2026-40-489.json | head -15
```

Each JSON has three chunks:

```json
{
  "metadata": {
    "title": "...",
    "identifier": "HR-NN-2026-40-489",
    "country": "hr",
    "rank": "pravilnik",
    "publication_date": "2026-04-17",
    "source": "https://narodne-novine.nn.hr/eli/sluzbeni/2026/40/489",
    "extra": { "act_number": "489", ... }
  },
  "articles": [ ... ],    // parsed body blocks
  "reforms":  [ ... ]     // one entry per legislative modification
}
```

At this point there are no Markdown files and no commits — only JSON.

---

## Phase 3 — Commit

Goal: render Markdown from the JSONs and stream them into git.
Does NOT download anything.

**The repo must be empty** (no prior commits on `main`) — see "Why
commit isn't idempotent" below.

```bash
py -3.13 -c "from legalize.cli import cli; cli()" commit -c hr --all
```

The default is `--fast` (git fast-import). Flags:
- `--no-fast` — one commit at a time via `git commit` (slow, idempotent-ish)
- `--limit N` / `--offset N` — subset (e.g. to test on 10 first)
- `--batch N` — batch + push after each batch (for long runs)
- `--dry-run` — print what it would do

What happens inside:

```
1. Load every JSON from data-hr/json/
2. Flatten into (norm, reform_date) tuples — one per reform
3. Sort globally by date (oldest first)
4. For each tuple:
   a. Render the norm's Markdown as-of that reform's date
   b. Stream `blob` + `commit` records to `git fast-import` stdin
5. fast-import builds refs/heads/main atomically
```

Output:

```
INFO     git fast-import: 495 commits imported
✓ 495 commits created (fast-import)
```

### Verify

```bash
git -C ../countries/hr rev-list --count HEAD                    # commit count
git -C ../countries/hr log --oneline | head -3                  # latest commits
ls ../countries/hr/hr/ | wc -l                                   # md file count
py -3.13 -c "from legalize.cli import cli; cli()" health -c hr   # full health check
```

Each commit:

```
commit 5d7bae6...
Author:     Legalize <legalize@legalize.dev>
AuthorDate: 2026-04-17 00:00:00 +0000
    [bootstrap] Pravilnik o izmjenama i dopuni Pravilnika o izobrazbi — versión original 2026
    Source-Id: HR-NN-2026-40-489
    Source-Date: 2026-04-17
    Norm-Id: eli/sluzbeni/2026/40/489
```

- Author/committer = the Legalize bot
  (set in `config.yaml::git.committer_name/email`)
- Subject tag = `[bootstrap]`, `[reforma]`, `[nueva]`, `[derogacion]`,
  `[correccion]`, or `[fix-pipeline]`
- Trailers map each commit back to its source record
- AuthorDate = the reform's publication date (so `git log` gives real
  chronological order)

---

## Combined: one-shot bootstrap

`bootstrap` is just `fetch` + `commit` wrapped together.

```bash
py -3.13 -c "from legalize.cli import cli; cli()" bootstrap -c hr --limit 500
```

Use this once you trust the separate phases. For our validation run it
took ~11 min fetch + ~15 s commit = 500 laws → 495 commits on main
(5 norms had no body content — day-of-publication acts whose HTML
wasn't cached on NN yet).

---

## Anatomy of the rendered Markdown

`countries/hr/hr/HR-NN-2026-40-489.md`:

```markdown
---
title: "Pravilnik o izmjenama i dopuni Pravilnika o izobrazbi"
identifier: "HR-NN-2026-40-489"
country: "hr"
rank: "pravilnik"
publication_date: "2026-04-17"
last_updated: "2026-04-17"
status: "in_force"
source: "https://narodne-novine.nn.hr/eli/sluzbeni/2026/40/489"
act_number: "489"
date_signed: "2026-04-16"
type_document: "PRAVILNIK"
amends: "eli/sluzbeni/2023/50/832"
changes: "eli/sluzbeni/2023/50/832"
---
# Pravilnik o izmjenama i dopuni Pravilnika o izobrazbi

MINISTARSTVO OBRANE

Na temelju članka 88. stavka 3. Zakona o službi...

### Članak 1.
...
```

Rules (enforced across all countries):

- Mandatory frontmatter keys: `title`, `identifier`, `country`, `rank`,
  `publication_date`, `last_updated`, `status`, `source`
- Country-specific fields (from `metadata.extra` in the JSON) are
  written flat at the top level — not nested
- UTF-8, LF line endings only
- Filename is `{country}/{identifier}.md` — flat layout, no rank or
  category subdirectories

---

## How to reset

### Full reset — start completely over

```bash
rm -rf ../countries/data-hr ../countries/hr
mkdir -p ../countries/hr
git -C ../countries/hr init -b main
git -C ../countries/hr remote add origin https://github.com/norislav/legalize-hr.git
git -C ../countries/hr config core.autocrlf false
```

Then re-run phases 1 → 2 → 3.

### Keep the fetch cache, redo commits only

Parser or renderer changed, but the source data is still good.

```bash
rm -rf ../countries/hr/.git ../countries/hr/hr ../countries/hr/README.md ../countries/hr/LICENSE
git -C ../countries/hr init -b main
git -C ../countries/hr remote add origin https://github.com/norislav/legalize-hr.git
git -C ../countries/hr config core.autocrlf false

py -3.13 -c "from legalize.cli import cli; cli()" commit -c hr --all
```

Takes ~15s because everything is cached in `data-hr/json/`.

### Reset one norm

```bash
rm ../countries/data-hr/json/HR-NN-2026-40-489.json
# next fetch will re-download that norm
py -3.13 -c "from legalize.cli import cli; cli()" fetch -c hr eli/sluzbeni/2026/40/489
```

---

## Why commit isn't idempotent

`commit_all_fast` (`pipeline.py:670`) explicitly says:

> Does NOT support idempotency — use only for fresh bootstrap on an empty repo.

It streams to `git fast-import` which builds the entire ref from
scratch in one atomic write. If `main` already has commits, fast-import
produces a parallel chain that becomes dangling (fast-import doesn't
pass `--force`). **Always start with an empty `.git/` before re-running
Phase 3.**

If you just want to update after daily changes, use `--no-fast`
instead — it commits one at a time and skips existing content.

---

## Windows gotchas

1. **`PYTHONUTF8=1` is required.** Without it, `rich` crashes printing
   `✓` on cp1252. Set it in your shell before any command.
2. **Line endings must be LF.** The engine writes via fast-import's
   stdin as raw bytes, which skips Python's text-mode CRLF
   translation. As belt-and-suspenders, set `core.autocrlf=false`
   in the country repo (see "Full reset" above).
3. **`data-hr/discovery_ids.txt` is order-sensitive.** `--offset` and
   `--limit` slice the file by position. If you delete it and
   re-discover, the order may change; don't mix old offsets with a
   newly generated file.

---

## Current repo state (validation run)

```
$ git -C ../countries/hr rev-list --count HEAD
496
$ git -C ../countries/hr log --oneline | head -3
d7fc449 [fix-pipeline] Add README and LICENSE
47d2dea [bootstrap] Presuda Visokog upravnog suda...
bbb9872 [bootstrap] Odluka i Rješenje Ustavnog suda...
```

Next step (pending): force-push to `norislav/legalize-hr`.

---

## Known issues (from the full-catalog bootstrap, 2026-04-22/23)

### 1. `norm_id` vs `identifier` mismatch broke the cache-hit check

**Symptom.** Re-running `fetch -c hr --all` re-downloaded every norm on
disk. The pipeline's "already fetched, skipping" check
(`pipeline.py:250`) never matched for HR.

**Cause.** Discovery yielded ELI paths (`eli/sluzbeni/YYYY/ISSUE/ORD`)
while the parser produced a different identifier (`HR-NN-YYYY-ISSUE-ORD`)
and saved the JSON under that name. The generic cache-hit check compares
`safe_id(norm_id)` against the filename — they disagreed.

**Fix.** Discovery now yields the canonical `HR-NN-YYYY-ISSUE-ORD` form
directly; the client translates to the ELI URI
(`/eli/sluzbeni/YYYY/ISSUE/ORD`) internally for HTTP. Migration script
rewrote the existing `discovery_ids.txt` in place
(`discovery_ids.txt.bak` kept).

### 2. Fetch errors — transient vs genuine 404s

Bulk fetch finished with **97 090 / 97 116 OK, 26 errors**. Retrying
the 26 individually:

- **24** saved on retry (transient — rate-limit wobble or parallel-worker
  races under `max_workers=2`).
- **2** recovered via the sitemap fallback + content-ELI extraction
  introduced for issue §3:
  - `HR-NN-2016-85-1863` → `HR-NN-2016-85-2080` (sitemap ord ≠ ELI ord).
  - `HR-NN-2024-102-0` → `HR-NN-2024-102-0000` (leading-zero stripping).
  Both aliases live in `../countries/data-hr/discovery_aliases.txt`.

Final fetch coverage: **97 116 / 97 116 = 100%**.

### 2a. Commit-phase orphans (JSONs without Markdown)

After the initial full bootstrap, **199** JSON records produced no
Markdown file (no commit on `main`). 21 of those were recoverable in
the same session:

- **6** were transient parser misses — NN was serving valid content,
  but the original parse came back empty. Recovered by
  `legalize reprocess -c hr HR-NN-2001-30-525 HR-NN-2002-29-639
   HR-NN-2006-43-1029 HR-NN-2011-109-2154 HR-NN-2013-31-559
   HR-NN-2019-4-83`.
- **15** State Budget (`Državni proračun`) and collective-agreement
  acts that NN serves as PDF bytes directly at the ELI URL (HTML-form
  request returns `%PDF-…`). Recovered after adding a PDF branch to
  `NarodneNovineTextParser.parse_text` — `pdfplumber` extracts one
  preamble block per act. All 15 were reprocessed and now commit
  with their real publication dates.

**Final commit coverage: 96 938 / 97 116 = 99.82%.** The remaining
**178 are all NN data-quality issues, not pipeline issues** — for each
one NN itself does not serve a usable body. Composition (verified
2026-05-13 by inspecting each orphan's live HTML):

- **~140 vocational-curriculum decisions** (`odluka o uvođenju
  strukovnog/posebnog kurikula`, mostly 2024–2025 from the Ministry
  of Education). NN renders these as a thin HTML shell with `<iframe
  src=".../pdf">` + `pdf-view` class; the binding curriculum text
  (program, hours, learning outcomes) lives in the iframe-loaded
  PDF, which is mostly bitmap-rendered tables. Following the iframe
  and running `pdfplumber` yields only the legal preamble
  (~13 KB/act of boilerplate); the curriculum proper is locked in
  images and would need OCR to recover. Deferred — the legal
  preamble alone wouldn't accurately represent the legislation, so
  no partial extraction.
- **5 zakon (primary laws)** that NN never digitized:
    - `HR-NN-1990-18-344` Zakon o privremenoj zabrani raspolaganja…
    - `HR-NN-1991-53-2001` Zakon o Carinskoj tarifi
    - `HR-NN-1991-65-1664` Ustavni zakon o ljudskim pravima i
      slobodama (constitutional law — most significant gap)
    - `HR-NN-1993-91-2291` Zakon o osnovama deviznog sustava
    - `HR-NN-2020-124-2402` Zakon o izmjenama Zakona o izvršavanju
      Državnog proračuna 2020 — NN's page literally displays
      "Sadržaj je nedostupan" ("Content is unavailable")
  Recovering these requires a non-NN source (Sabor archive, paper
  editions, secondary legal databases) and is out of scope for the
  pipeline.
- **~33 misc** — `rjesenje` (appointments), `uredba` and
  `pravilnik` (non-curriculum 2024–2025), other `odluka`
  (Constitutional Court, parliamentary committee changes, 1992
  bank rediscount), and 7 `SADRŽAJ BROJA` table-of-contents pages
  that NN indexes as acts but aren't legislation. All are
  metadata-only stubs on NN.

The 178 stay cached as metadata-only JSONs and can be reprocessed
later if NN's underlying pages change.

### 2b. Pipeline bug — sentinel publication dates

The HR PDF branch (and HR's HTML fallback when `<h3>` date is
missing) emit `date(1900, 1, 1)` as a placeholder publication date
on block versions. `extract_reforms(blocks)` propagated that into the
bootstrap `Reform.date`, and git author dates rendered as 1970-01-02
(Git clamps pre-1970 dates to epoch) with commit subjects saying
"versión original 1900".

Fix: `pipeline.py::_backfill_sentinel_dates` rewrites placeholder
dates to `metadata.publication_date` (which comes from the
authoritative ELI JSON-LD / detailsTable) after `_extract_reforms_
generic`, for both reforms and block versions. It's country-agnostic:
any future parser that uses the same sentinel convention benefits.

**Note on the 26 count.** `UnicodeEncodeError` inherits from
`ValueError`, which `generic_fetch_one`'s `except` clause catches.
Croatian titles contain characters (`č`, `š`, `ž`, etc.) that blow up
Rich's fall-back renderer on Windows cp1252 consoles. Some of the
"errors" were actually successful fetches whose `✓` print crashed after
`save_structured_json` had already written the JSON — but those files
*did* land on disk, so they don't show up in the missing set. Running
with `PYTHONUTF8=1` avoids the crash entirely.

### 3. norm_id vs canonical ELI disagreements — fixed

Observed two failure modes in the 97 116-act catalog:

- **Sitemap ord ≠ ELI ord.** The sitemap lists
  `/clanci/sluzbeni/YYYY_MM_ISSUE_ORD.html`, but the ELI embedded on
  that page can point at a different ord. Example:
  `HR-NN-2016-85-1863` → `HR-NN-2016-85-2080`.
- **Leading-zero stripping.** Discovery applied `int()` to the ord
  when building the norm_id, collapsing `0000` to `0`. The server
  treats `0` and `0000` as distinct ELIs; our request hit the former
  (404) while the act lives at the latter. Example:
  `HR-NN-2024-102-0` → `HR-NN-2024-102-0000`.

**Resolution.** Three-part fix across the fetcher:

- `client.get_text` falls back to the sitemap URL when the ELI URI
  returns 404. The fallback picks the sub-sitemap `<loc>` whose
  trailing `_{issue}_<digits>.html` digits match the requested ord
  numerically (not textually), so zero-padding differences don't
  cause the lookup to miss.
- The metadata parser extracts the canonical ELI from the HTML
  `ELI:` anchor (detailsTable) or the JSON-LD `@id` of the Work node,
  and sets `metadata.identifier` from that content rather than the
  input `norm_id`. When they agree (99.998% of acts) it's a no-op.
- The pipeline saves the JSON under `metadata.identifier` and, when
  it differs from `safe_id(norm_id)`, writes a
  `{norm_id}\t{resolved_id}` line to
  `../countries/data-hr/discovery_aliases.txt`. The cache-hit check in
  `generic_fetch_one` consults the alias map before re-fetching, so
  subsequent runs short-circuit without another network round-trip.

The alias file is append-only and expected to stay very small (2
entries today). It's part of the data-dir cache and regenerable —
deleting `data-hr/` wipes it along with everything else.
