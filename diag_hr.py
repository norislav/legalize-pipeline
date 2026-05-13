"""Pre-seed HR discovery cache with progress output.

Unlike the silent enumeration inside generic_fetch_all, this script prints
every sub-sitemap URL as it's fetched so stalls are immediately visible.

Usage: py -3.13 -u diag_hr.py [TARGET]
  TARGET = number of norm_ids to collect (default 600, enough for --limit 500)
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from legalize.fetcher.hr import NarodneNovineClient, NarodneNovineDiscovery

CACHE = Path("../countries/data-hr/discovery_ids.txt")
TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 600

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stderr)

t0 = time.time()
client = NarodneNovineClient(
    base_url="https://narodne-novine.nn.hr",
    requests_per_second=1.5,
    request_timeout=20,
    max_retries=2,
)
disc = NarodneNovineDiscovery(parts=(1,), year_start=1990)

print(f"[{time.time()-t0:6.1f}s] Fetching root sitemap...", flush=True)
sub_sitemaps = list(disc._enumerate_sub_sitemaps(client))
print(f"[{time.time()-t0:6.1f}s] Root: {len(sub_sitemaps)} sub-sitemaps (part=1, all years)", flush=True)

sub_sitemaps = [s for s in sub_sitemaps if s[2] >= 1990]
print(f"[{time.time()-t0:6.1f}s] Filtered to year >= 1990: {len(sub_sitemaps)} sub-sitemaps", flush=True)

# NN sitemap index is sorted oldest-first. Reverse so we start with recent
# issues, giving variety (JSON-LD + HTML paths) in the first 500.
sub_sitemaps.sort(key=lambda s: (s[2], s[3]), reverse=True)

ids: list[str] = []
for i, (sub_url, _part, year, issue) in enumerate(sub_sitemaps):
    try:
        batch = list(disc._parse_sub_sitemap(client, sub_url))
    except Exception as exc:
        print(f"[{time.time()-t0:6.1f}s]   ! {sub_url} -> {exc}", flush=True)
        continue
    ids.extend(batch)
    if i % 25 == 0 or len(ids) >= TARGET:
        print(f"[{time.time()-t0:6.1f}s]   {i+1}/{len(sub_sitemaps)} sitemaps, {len(ids)} ids (year={year}, issue={issue})", flush=True)
    if len(ids) >= TARGET:
        break

CACHE.parent.mkdir(parents=True, exist_ok=True)
CACHE.write_text("\n".join(ids) + "\n")
print(f"[{time.time()-t0:6.1f}s] Seeded {len(ids)} IDs into {CACHE}", flush=True)
