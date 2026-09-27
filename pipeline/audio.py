#!/usr/bin/env python3
"""Génération du podcast (dialogue 2 voix type NotebookLM) via Podcastfy (phase 2).
Choix Julien : Podcastfy complet. Stack : LLM Gemini (GEMINI_API_KEY) + TTS Edge (gratuit).
Guard : sans GEMINI_API_KEY ou si podcastfy indisponible → no-op, jamais d'échec du workflow.
Sortie : site/audio/digest-<date>.mp3 (+ <date>.de.mp3 / .it.mp3 si traductions présentes)
"""
import os
import sys
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "site" / "audio"

# podcastfy est lourd : installation runtime guardée (le workflow n'installe que pyyaml)
def ensure_podcastfy():
    try:
        import podcastfy  # noqa
        return True
    except ImportError:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "podcastfy"],
                           check=True, timeout=600)
            return True
        except Exception as e:
            print(f"podcastfy non installable (non fatal) : {e}")
            return False


def make_podcast(md_path: Path, out_mp3: Path, lang: str):
    from podcastfy.client import generate_podcast
    voice_map = {
        "fr": ("fr-FR-DeniseNeural", "fr-FR-HenriNeural"),
        "de": ("de-CH-LeniNeural", "de-CH-JanNeural"),
        "it": ("it-IT-ElsaNeural", "it-IT-DiegoNeural"),
    }
    v1, v2 = voice_map.get(lang, voice_map["fr"])
    config = {
        "conversation_style": ["engaging", "informative"],
        "dialogue_structure": {"topic": "veille des mini-publics et démocratie délibérative en Suisse"},
        "output_language": lang,
        "tts_configuration": {
            "tts_engine": "edge",
            "default_voice": v1,
            "second_voice": v2,
        },
    }
    audio_file = generate_podcast(
        text=md_path.read_text(encoding="utf-8"),
        llm_model_name="gemini",
        conversation_config=config,
    )
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    Path(audio_file).replace(out_mp3)
    print(f"Podcast {lang} OK → {out_mp3}")


def main():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        print("GEMINI_API_KEY absent — audio sauté")
        return 0
    if not ensure_podcastfy():
        return 0
    os.environ.setdefault("GEMINI_API_KEY", key)
    digests = sorted((BASE / "digests").glob("digest-*.md"), reverse=True)
    if not digests:
        print("Aucun digest → audio sauté")
        return 0
    # Un podcast par langue : FR depuis le digest principal, DE/IT depuis les traductions
    targets = []
    main_digest = next((d for d in digests if "." not in d.stem.replace("digest-", "") and d.suffix == ".md"), digests[0])
    date = main_digest.stem.replace("digest-", "")
    targets.append((main_digest, OUT / f"{date}.mp3", "fr"))
    for lang in ("de", "it"):
        t = BASE / "digests" / f"digest-{date}.{lang}.md"
        if t.exists():
            targets.append((t, OUT / f"{date}.{lang}.mp3", lang))
    ok = 0
    for md, out, lang in targets:
        try:
            if not out.exists():
                make_podcast(md, out, lang)
            ok += 1
        except Exception as e:
            print(f"Podcast {lang} ÉCHEC (non fatal) : {e}")
    print(f"Audio : {ok}/{len(targets)} fichiers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
