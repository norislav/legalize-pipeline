#!/usr/bin/env python3
"""Render the 5 Step-7 HR fixtures to C:/dev/hr-sandbox/*.md.

Usage:
    python scripts/render_sample_hr.py

Between parser iterations: re-run this, then inspect the MDs.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from legalize.countries import get_metadata_parser, get_text_parser
from legalize.transformer.markdown import render_norm_at_date

CODE = "hr"
FIXTURES = ROOT / "tests" / "fixtures" / "hr"
OUT = Path("C:/dev/hr-sandbox")

# 5 laws chosen to exercise every parser dimension:
#   - both metadata branches (JSON-LD + HTML fallback)
#   - ranks: ustav, zakon, uredba
#   - departments: Hrvatski sabor, Vlada, parliamentary committee
#   - sizes: 29 → 320 articles
#   - new-act + amendment forms
#   - years spanning 2001–2022
SAMPLES = [
    # (norm_id, metadata fixture, text fixture, role)
    (
        "eli/sluzbeni/2010/85/2422",
        "sample-constitution-procisceni-2010.html",
        "sample-constitution-procisceni-2010.html",
        "Ustav pročišćeni (HTML fallback, highest rank)",
    ),
    (
        "eli/sluzbeni/2014/93/1872",
        "sample-zakon-radu-2014.html",
        "sample-zakon-radu-2014.html",
        "Zakon o radu 2014 (HTML fallback, 235 articles)",
    ),
    (
        "eli/sluzbeni/2021/111/1941",
        "sample-autorsko-pravo-2021.json-ld",
        "sample-autorsko-pravo-2021.html",
        "Zakon o autorskom pravu 2021 (JSON-LD, repeals/transposes)",
    ),
    (
        "eli/sluzbeni/2022/151/2343",
        "sample-amendment-radu-2022.json-ld",
        "sample-amendment-radu-2022.html",
        "Amendment Zakona o radu 2022 (JSON-LD, [reform])",
    ),
    (
        "eli/sluzbeni/2001/37/644",
        "sample-uredba-radna-mjesta-2001.html",
        "sample-uredba-radna-mjesta-2001.html",
        "Uredba radna mjesta 2001 (HTML, Vlada-issued)",
    ),
]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    mp = get_metadata_parser(CODE)
    tp = get_text_parser(CODE)
    for norm_id, meta_file, text_file, role in SAMPLES:
        meta_bytes = (FIXTURES / meta_file).read_bytes()
        text_bytes = (FIXTURES / text_file).read_bytes()
        meta = mp.parse(meta_bytes, norm_id)
        blocks = tp.parse_text(text_bytes)
        md = render_norm_at_date(
            meta, blocks, meta.publication_date, include_all=True
        )
        out_file = OUT / f"{meta.identifier}.md"
        out_file.write_text(md, encoding="utf-8", newline="\n")
        articles = sum(1 for b in blocks if b.block_type == "article")
        print(
            f"{meta.identifier:25s} {len(md):>7} chars  "
            f"{len(blocks):>4} blocks ({articles} articles)  — {role}"
        )


if __name__ == "__main__":
    main()
