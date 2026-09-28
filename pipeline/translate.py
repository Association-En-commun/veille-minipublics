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
MODEL = "gemini-flash-latest"  # alias stable ; 3.8-flash persistait en 503 (log 36391349122)


def gemini(prompt, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.3}}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    import time
    last_err = None
    for attempt in range(4):  # 503/429 = surcharge transitoire → backoff 5/15/45 s
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                d = json.loads(r.read().decode())
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:800]
            last_err = RuntimeError(f"Gemini {e.code}: {body}")
            if e.code in (429, 503) and attempt < 3:
                time.sleep([5, 15, 45][attempt])
                req = urllib.request.Request(url, data=body2, headers={"Content-Type": "application/json"}) if False else req
                continue
            if attempt >= 3:
                list_models(key)
            raise last_err from e
    else:
        raise last_err
    return d["candidates"][0]["content"]["parts"][0]["text"]


def list_models(key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={key}&pageSize=100"
    try:
        with urllib.request.urlopen(url, timeout=60) as r:
            d = json.loads(r.read().decode())
        names = [m["name"] for m in d.get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
        print("MODELS DISPONIBLES:", ", ".join(sorted(names)))
    except Exception as e:
        print("ListModels échec:", e)


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
