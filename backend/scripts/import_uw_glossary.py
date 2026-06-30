"""
Seed the glossary from unfoldingWord translationWords (Telugu).

translationWords (tW) is an openly-licensed (CC-BY-SA 4.0) Biblical key-terms
dictionary: theological terms + proper names (people/places) with definitions.
The Telugu edition (te_tw) gives the Telugu rendering per article; the English
edition (en_tw) gives the canonical English term. Aligning them by article id
yields a high-precision Telugu->English seed for this project's glossary.

Usage (from backend/):
    venv\\Scripts\\python.exe -m scripts.import_uw_glossary            # dry-run -> preview JSON
    venv\\Scripts\\python.exe -m scripts.import_uw_glossary --commit   # upsert into the glossary

Dry-run writes scripts/uw_glossary_preview.json and prints a category summary.
--commit upserts via routers.glossary.apply_bulk (idempotent meaning-merge).
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os
import re
import sys
import zipfile

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Windows console here is cp1252 — force UTF-8 so printing Telugu doesn't crash.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

from database import AsyncSessionLocal
from routers.glossary import GlossaryBulkItem, apply_bulk

PREVIEW_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "uw_glossary_preview.json")

# Door43 archive candidates (Gitea). Try in order; first that has bible/kt wins.
TE_URLS = [
    "https://git.door43.org/Door43-Catalog/te_tw/archive/master.zip",
    "https://git.door43.org/STR/te_tw/archive/master.zip",
    "https://git.door43.org/Door43-Catalog/te_tw/archive/main.zip",
]
EN_URLS = [
    "https://git.door43.org/unfoldingWord/en_tw/archive/master.zip",
    "https://git.door43.org/Door43-Catalog/en_tw/archive/master.zip",
]

_FOLDER_CATEGORY = {"kt": "theology", "names": "name", "other": "general"}
_ENTRY_RE = re.compile(r"/bible/(kt|names|other)/([^/]+)\.md$")
_HEADING_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
_TELUGU_RE = re.compile(r"[ఀ-౿]")
# Reclassify a `names` entry as a place when its English definition opens like a location.
_PLACE_RE = re.compile(
    r"\b(?:name of (?:a |an |the )?)?"
    r"(?:city|cities|town|village|region|province|district|land of|country|"
    r"kingdom|nation|river|sea|lake|mountain|mount|hill|valley|desert|"
    r"wilderness|island|peninsula)\b",
    re.IGNORECASE,
)


def _download_zip(urls: list[str]) -> zipfile.ZipFile | None:
    for url in urls:
        try:
            r = httpx.get(url, follow_redirects=True, timeout=90)
            r.raise_for_status()
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            if any(_ENTRY_RE.search(n) for n in zf.namelist()):
                print(f"  downloaded {url} ({len(r.content)//1024} KB)")
                return zf
        except Exception as exc:  # try next candidate
            print(f"  skip {url}: {exc}")
    return None


def _first_heading(md: str) -> str:
    m = _HEADING_RE.search(md)
    return (m.group(1) if m else "").replace("*", "").replace("`", "").strip()


def _split_forms(title: str) -> list[str]:
    return [p.strip(" .:;") for p in re.split(r"[,;/]", title) if p.strip(" .:;")]


def _pretty(article_id: str) -> str:
    return article_id.replace("-", " ").replace("_", " ").strip().title()


def _parse_zip(zf: zipfile.ZipFile, *, want_body: bool) -> dict[str, dict]:
    """Return {article_id: {folder, title, body?}} for bible/{kt,names,other}/*.md."""
    out: dict[str, dict] = {}
    for name in zf.namelist():
        m = _ENTRY_RE.search(name)
        if not m:
            continue
        folder, article_id = m.group(1), m.group(2)
        try:
            md = zf.read(name).decode("utf-8", errors="replace")
        except Exception:
            continue
        entry = {"folder": folder, "title": _first_heading(md)}
        if want_body:
            entry["body"] = md[:400].lower()
        out[article_id] = entry
    return out


def _build_items(
    te: dict[str, dict], en: dict[str, dict], include_other: bool
) -> list[GlossaryBulkItem]:
    by_te: dict[str, GlossaryBulkItem] = {}
    for article_id, te_entry in te.items():
        # `other/` is ordinary Biblical vocabulary (category=general). Skip by default —
        # the high-value seed is theology (kt) + names/places.
        if te_entry["folder"] == "other" and not include_other:
            continue
        te_forms = [f for f in _split_forms(te_entry["title"]) if _TELUGU_RE.search(f)]
        if not te_forms:
            continue  # untranslated / English-only title — skip

        en_entry = en.get(article_id)
        en_title = en_entry["title"] if en_entry else ""
        meanings = _split_forms(en_title) or [_pretty(article_id)]

        folder = te_entry["folder"]
        category = _FOLDER_CATEGORY.get(folder, "general")
        if folder == "names":
            body = (en_entry or {}).get("body", "")
            category = "place" if _PLACE_RE.search(body) else "name"

        for te_form in te_forms:
            existing = by_te.get(te_form)
            if existing:
                for m in meanings:
                    if m not in existing.meanings:
                        existing.meanings.append(m)
                if existing.category == "general" and category != "general":
                    existing.category = category
            else:
                by_te[te_form] = GlossaryBulkItem(
                    te_term=te_form, meanings=list(meanings),
                    category=category, notes="uW tW",
                )
    return list(by_te.values())


def _summary(items: list[GlossaryBulkItem]) -> dict:
    by_cat: dict[str, int] = {}
    for it in items:
        by_cat[it.category] = by_cat.get(it.category, 0) + 1
    samples = [
        {"te_term": it.te_term, "meanings": it.meanings, "category": it.category}
        for it in items[:40]
    ]
    return {"total": len(items), "by_category": by_cat, "samples": samples}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="upsert into the glossary (default: dry-run)")
    ap.add_argument("--include-other", action="store_true",
                    help="also import the tW 'other' folder (~1300 general Biblical terms)")
    args = ap.parse_args()

    print("Fetching te_tw …")
    te_zip = _download_zip(TE_URLS)
    if te_zip is None:
        print("ERROR: could not download te_tw from any candidate URL.")
        sys.exit(1)
    print("Fetching en_tw …")
    en_zip = _download_zip(EN_URLS)
    if en_zip is None:
        print("WARN: en_tw unavailable — English terms will fall back to article ids.")

    te = _parse_zip(te_zip, want_body=False)
    en = _parse_zip(en_zip, want_body=True) if en_zip else {}
    print(f"Parsed te_tw entries: {len(te)}   en_tw entries: {len(en)}")

    items = _build_items(te, en, include_other=args.include_other)
    summ = _summary(items)
    print(f"Built {summ['total']} glossary items: {summ['by_category']}")

    with open(PREVIEW_PATH, "w", encoding="utf-8") as f:
        json.dump(summ, f, ensure_ascii=False, indent=2)
    print(f"Preview written to {PREVIEW_PATH}")

    if not args.commit:
        print("Dry-run only. Re-run with --commit to upsert into the glossary.")
        return

    async with AsyncSessionLocal() as session:
        created, updated, skipped = await apply_bulk(session, items)
    print(f"Committed: created={created} updated={updated} skipped={skipped}")


if __name__ == "__main__":
    asyncio.run(main())
