#!/usr/bin/env python3
"""Traduction des digests FR → DE / IT via Gemini (étape LLM, phase 1).
Guard : si GEMINI_API_KEY absent → no-op (le site reste FR seul, jamais d'échec).
Sortie : digests/digest-YYYY-MM-DD.de.md et .it.md
"""
import os
import re
import json
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
LANGS = {"de": "allemand (Suisse)", "it": "italien (Suisse)"}
MODEL = "gemini-2.5-flash"  # gemini-2.0-flash retiré par Google (404)


def gemini(prompt, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.3}}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    return d["candidates"][0]["content"]["parts"][0]["text"]


def translate_digest(md_text, lang, key):
    prompt = (
        f"Traduis ce digest de veille en {LANGS[lang]}. Garde EXACTEMENT la structure Markdown "
        f"(titres ##, listes, gras **), ne traduis PAS les URLs, ni les noms propres, "
        f"ni les identifiants de sources. Termine par la ligne d'intro inchangée sauf traduction. "
        f"Réponds UNIQUEMENT avec le Markdown traduit.\n\n{md_text}"
    )
    return gemini(prompt, key)


def main():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        print("GEMINI_API_KEY absent — traduction sautée (site FR seul)")
        return 0
    import datetime
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    src = BASE / "digests" / f"digest-{today}.md"
    if not src.exists():
        # fallback : dernier digest disponible
        cands = sorted((BASE / "digests").glob("digest-*.md"))
        if not cands:
            print("Aucun digest à traduire")
            return 0
        src = cands[-1]
    text = src.read_text(encoding="utf-8")
    stem = src.stem  # digest-YYYY-MM-DD
    for lang in LANGS:
        out = BASE / "digests" / f"{stem}.{lang}.md"
        try:
            translated = translate_digest(text, lang, key)
            out.write_text(translated, encoding="utf-8")
            print(f"Traduction {lang} OK → {out.name}")
        except Exception as e:
            print(f"Traduction {lang} ÉCHEC (non fatal) : {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
