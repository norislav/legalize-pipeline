"""§0.5 version-history spike for Croatia.

Gate: extract >=2 versions with publication dates from one law.

Chosen law: Ustav Republike Hrvatske. We have the 2010 pročišćeni tekst
fixture (NN 85/2010). Its preamble should list all predecessor NN citations
(56/90 original, then 1997/1998/2000/2001 amendments). We resolve two of
those citations to real per-act pages and extract their <h3> publication
dates. Success = 2 dated versions from one law's chain.
"""
import json
import os
import re
import ssl
import sys
import urllib.request

CTX = ssl.create_default_context()
try:
    import certifi
    CTX.load_verify_locations(certifi.where())
except ImportError:
    pass

UA = "legalize-bot/1.0 (+https://github.com/legalize-dev/legalize)"
BASE = "https://narodne-novine.nn.hr"

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "version-spike.txt")


def fetch(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
            return r.status, r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, ""


def extract_body_stats(html):
    """Return (paragraph_count, first_excerpt) from the articleContent body.

    Counts <p> inside the main articleContent div and returns a short text
    excerpt from the first substantial paragraph (so the spike proves that
    the version's full text is reachable, not just its citation heading).
    """
    body = re.search(r'<div[^>]*class="[^"]*\barticleContent\b[^"]*"[^>]*>(.*)',
                     html, re.DOTALL)
    if not body:
        return 0, ""
    content = body.group(1)
    paragraphs = re.findall(r"<p\b[^>]*>(.*?)</p>", content, re.DOTALL)
    count = len(paragraphs)
    excerpt = ""
    for p in paragraphs:
        text = re.sub(r"<[^>]+>", " ", p)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) >= 40:
            excerpt = text[:240]
            break
    return count, excerpt


def extract_h3_citation(html):
    """Parse 'NN {issue}/{year} ({d.m.yyyy.}), {title}' from first <h3>."""
    m = re.search(r"<h3[^>]*>([^<]+)</h3>", html)
    if not m:
        return None
    text = m.group(1).strip()
    # Example: 'NN 56/1990 (22.12.1990.), Ustav Republike Hrvatske'
    m2 = re.match(
        r"NN\s+(\d+)/(\d{2,4})\s+\((\d{1,2})\.(\d{1,2})\.(\d{4})\.\)\s*,\s*(.+)",
        text,
    )
    if not m2:
        return {"raw": text}
    issue, year, d, mth, yr, title = m2.groups()
    # Normalize 2-digit years
    year_full = f"20{year}" if len(year) == 2 and int(year) < 50 else (
        f"19{year}" if len(year) == 2 else year
    )
    return {
        "raw": text,
        "issue": int(issue),
        "year": int(year_full),
        "publication_date": f"{int(yr):04d}-{int(mth):02d}-{int(d):02d}",
        "title": title,
    }


def extract_preamble_citations(html):
    """Find predecessor NN citations near the top of the consolidated text."""
    # Isolate the first 6 KB of body content (after nav/chrome)
    body = re.search(r'<div[^>]*class="[^"]*\barticleContent\b[^"]*"[^>]*>(.*)',
                     html, re.DOTALL)
    content = body.group(1) if body else html
    # Strip <style>, <script>, and inline CSS rule blocks (they precede the
    # actual text in NN pages and contain noise like font-size:16px)
    content = re.sub(r"<style\b[^>]*>.*?</style>", " ", content,
                     flags=re.DOTALL | re.IGNORECASE)
    content = re.sub(r"<script\b[^>]*>.*?</script>", " ", content,
                     flags=re.DOTALL | re.IGNORECASE)
    window = content[:20000]
    window_txt = re.sub(r"<[^>]+>", " ", window)
    # Drop any remaining CSS-like fragments (e.g. ".sl-content { ... }")
    window_txt = re.sub(r"\.[a-zA-Z][\w-]*\s*\{[^}]*\}", " ", window_txt)
    window_txt = re.sub(r"\s+", " ", window_txt)
    # Match NN N/YY(YY) citations
    cites = re.findall(r"\b(\d{1,3})/(\d{2,4})\b", window_txt)
    seen, out = set(), []
    for issue, year in cites:
        key = (int(issue), int(year))
        if key in seen:
            continue
        seen.add(key)
        out.append({"issue": int(issue), "year_raw": year, "year": (
            int(f"20{year}") if len(year) == 2 and int(year) < 50
            else int(f"19{year}") if len(year) == 2
            else int(year)
        )})
    return out, window_txt[:400]


def resolve_nn_citation(issue, year):
    """Try known URL patterns to find an NN act page from an (issue, year) tuple.

    We don't know the within-issue act number (that's the hard part). So this
    is a BEST-EFFORT resolver: it tries the issue-sitemap to enumerate acts
    in that issue, then picks the first ZAKON about "Ustav" or similar. For the
    spike, we already know some direct URLs, so we seed a small index below.
    Production discovery must use the sitemap approach.
    """
    # Seed index of Ustav-chain citations (from web search results, spike only):
    known = {
        (85, 2010): "/clanci/sluzbeni/2010_07_85_2422.html",  # pročišćeni tekst 2010
        (76, 2010): "/clanci/sluzbeni/2010_06_76_2214.html",  # amendment 2010
        (5, 2014): "/clanci/sluzbeni/2014_01_5_106.html",      # amendment 2014
        (56, 1990): "/clanci/sluzbeni/1990_12_56_1092.html",   # original 1990
    }
    return known.get((issue, year))


def main():
    lines = []
    P = lambda s: (lines.append(s), print(s))  # noqa: E731

    P("=" * 72)
    P("§0.5 VERSION-HISTORY SPIKE — Croatia (HR)")
    P("=" * 72)
    P("")
    P("Law: Ustav Republike Hrvatske (Croatian Constitution)")
    P("Entry point: NN 85/2010 pročišćeni tekst")
    P("")

    # 1. Load the pročišćeni tekst from fixture
    with open(os.path.join(HERE, "sample-constitution-procisceni-2010.html"),
              encoding="utf-8") as f:
        pt_html = f.read()
    pt_h3 = extract_h3_citation(pt_html)
    P("Step 1: Parse pročišćeni tekst heading")
    P(f"  <h3> raw: {pt_h3['raw']}")
    P(f"  issue={pt_h3['issue']}, year={pt_h3['year']}, date={pt_h3['publication_date']}")
    P("")

    # 2. Extract preamble citation chain
    cites, sample = extract_preamble_citations(pt_html)
    P("Step 2: Preamble citation chain (from articleContent first 6KB)")
    P(f"  preamble sample (first 400 chars): {sample!r}")
    P(f"  {len(cites)} unique (issue, year) tuples found:")
    for c in cites[:15]:
        P(f"    NN {c['issue']}/{c['year_raw']} -> year={c['year']}")
    P("")

    # 3. Pick two predecessors and resolve them to dated versions
    # Ustav chain candidates: 56/90 (original), 76/2010 (pre-pročišćeni amendment)
    P("Step 3: Resolve two predecessors -> fetch -> extract dated version")
    targets = [(56, 1990), (76, 2010)]
    resolved = []
    for issue, year in targets:
        P(f"\n  >>> NN {issue}/{year}")
        path = resolve_nn_citation(issue, year)
        if not path:
            P(f"     no seeded URL (would require sitemap lookup in production)")
            continue
        P(f"     trying {BASE}{path}")
        status, html = fetch(path)
        if status != 200:
            P(f"     HTTP {status}")
            continue
        h3 = extract_h3_citation(html)
        P(f"     <h3>: {h3.get('raw')}")
        if "publication_date" in h3:
            pcount, excerpt = extract_body_stats(html)
            h3["paragraph_count"] = pcount
            h3["excerpt"] = excerpt
            P(f"     EXTRACTED: title={h3['title']!r}")
            P(f"                publication_date={h3['publication_date']}")
            P(f"                nn_issue={h3['issue']}/{h3['year']}")
            P(f"                paragraph_count={pcount}")
            P(f"                text_excerpt={excerpt[:160]!r}")
            resolved.append(h3)

    P("")
    P("=" * 72)
    P(f"RESULT: {len(resolved)} versions dated and titled from one law's chain")
    for i, v in enumerate(resolved, 1):
        P(f"  version {i}: date {v['publication_date']}, "
          f"{v.get('paragraph_count', 0)} paragraphs  "
          f"(NN {v['issue']}/{v['year']}, {v['title']!r})")
    P("GATE: PASS" if len(resolved) >= 2 else "GATE: FAIL")
    P("=" * 72)
    P("")
    P("Interpretation:")
    P(f"  - The pročišćeni tekst preamble yielded {len(cites)} predecessor citations")
    P(f"  - {len(resolved)} were resolvable to dated NN per-act pages via <h3>")
    P("  - Full production discovery replaces the seeded URL index with a")
    P("    sitemap lookup that enumerates all acts in issue {year}/{issue}")
    P("    and filters to the one whose title matches the Ustav chain.")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return 0 if len(resolved) >= 2 else 1


if __name__ == "__main__":
    sys.exit(main())
