"""Fetch the 5 representative HR fixtures + companion JSON-LD where available.

Run once from this directory to (re)populate the fixture set. Intentionally
simple urllib; no external deps, no retries — rerun on transient failures.
"""
import json
import os
import ssl
import sys
import time
import urllib.request

CTX = ssl.create_default_context()
try:
    import certifi
    CTX.load_verify_locations(certifi.where())
except ImportError:
    pass

UA = "legalize-bot/1.0 (+https://github.com/legalize-dev/legalize)"
BASE = "https://narodne-novine.nn.hr"

FIXTURES = [
    {
        "slug": "sample-constitution-procisceni-2010",
        "role": "highest rank, pročišćeni tekst, pre-2015 (JSON-LD expected 404)",
        "html": "/clanci/sluzbeni/2010_07_85_2422.html",
        "eli": "/eli/sluzbeni/2010/85/2422",
    },
    {
        "slug": "sample-code-obvezni-odnosi-2005",
        "role": "major code (Law of Obligations), pre-2015",
        "html": "/clanci/sluzbeni/2005_03_35_707.html",
        "eli": "/eli/sluzbeni/2005/35/707",
    },
    {
        "slug": "sample-zakon-radu-2014",
        "role": "ordinary zakon with post-2015 amendments pointing back",
        "html": "/clanci/sluzbeni/2014_07_93_1872.html",
        "eli": "/eli/sluzbeni/2014/93/1872",
    },
    {
        "slug": "sample-amendment-radu-2022",
        "role": "post-2015 amendment with full ELI JSON-LD",
        "html": "/clanci/sluzbeni/2022_12_151_2343.html",
        "eli": "/eli/sluzbeni/2022/151/2343",
    },
    {
        "slug": "sample-autorsko-pravo-2021",
        "role": "recent zakon, transposes EU directives, clean JSON-LD",
        "html": "/clanci/sluzbeni/2021_10_111_1941.html",
        "eli": "/eli/sluzbeni/2021/111/1941",
    },
    {
        "slug": "sample-uredba-radnih-mjesta-2023",
        "role": "uredba (government decree), post-2015",
        "html": "/clanci/sluzbeni/2023_03_26_414.html",
        "eli": "/eli/sluzbeni/2023/26/414",
    },
    {
        "slug": "sample-pdv-2013",
        "role": "tax law with rate tables",
        "html": "/clanci/sluzbeni/2013_06_73_1451.html",
        "eli": "/eli/sluzbeni/2013/73/1451",
    },
    # Extra pre-2015 coverage for HTML detailsTable fallback (no JSON-LD expected).
    {
        "slug": "sample-uredba-radna-mjesta-2001",
        "role": "early uredba (Vlada, not Sabor) — referenced by the 2023 amending uredba",
        "html": None,  # month unknown; rely on ELI redirect
        "eli": "/eli/sluzbeni/2001/37/644",
    },
    {
        "slug": "sample-act-2010-62-1979",
        "role": "2010 ordinary act referenced by the 2022 amendment",
        "html": None,
        "eli": "/eli/sluzbeni/2010/62/1979",
    },
    {
        "slug": "sample-act-2003-167-2399",
        "role": "2003 act — older pre-2015 fixture repealed by the 2021 Copyright Act",
        "html": None,
        "eli": "/eli/sluzbeni/2003/167/2399",
    },
]


def fetch(path):
    url = BASE + path
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=30) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        return e.code, b""


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    log = []
    for fx in FIXTURES:
        print(f"[{fx['slug']}]", file=sys.stderr)
        # HTML: use declared path, or fall back to the ELI URI which the
        # server 302-redirects to the canonical /clanci/sluzbeni/... URL.
        html_path = fx["html"] or fx["eli"]
        status, body = fetch(html_path)
        if status == 200:
            with open(os.path.join(here, fx["slug"] + ".html"), "wb") as f:
                f.write(body)
            html_size = len(body)
        else:
            html_size = None
            print(f"  HTML {status}", file=sys.stderr)
        time.sleep(0.4)  # 3 req/s ceiling

        # JSON-LD
        status_jl, body_jl = fetch(fx["eli"] + "/json-ld")
        if status_jl == 200:
            with open(os.path.join(here, fx["slug"] + ".json-ld"), "wb") as f:
                f.write(body_jl)
            jsonld_size = len(body_jl)
        else:
            jsonld_size = None
            print(f"  JSON-LD {status_jl}", file=sys.stderr)
        time.sleep(0.4)

        log.append({
            "slug": fx["slug"],
            "role": fx["role"],
            "html_path": fx["html"],
            "eli_path": fx["eli"],
            "html_status": status,
            "html_bytes": html_size,
            "jsonld_status": status_jl,
            "jsonld_bytes": jsonld_size,
        })

    with open(os.path.join(here, "_fetch_log.json"), "w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)
    print("\nfetch log:", file=sys.stderr)
    for row in log:
        print(
            f"  {row['slug']:50s} html={row['html_status']} "
            f"({row['html_bytes']}) jsonld={row['jsonld_status']} "
            f"({row['jsonld_bytes']})",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
