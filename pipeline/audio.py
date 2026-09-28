#!/usr/bin/env python3
"""Génération du podcast — dialogue 2 voix type NotebookLM.
Voie 1 : Podcastfy (LLM Gemini + TTS Edge). Voie 2 (fallback, garanti) : script de
dialogue écrit par Gemini puis synthèse phrase par phrase avec edge-tts (2 voix)
et assemblage ffmpeg. Guard : sans GEMINI_API_KEY → no-op, jamais d'échec du workflow.
Sortie : site/audio/<date>.mp3 (+ <date>.de.mp3 / .it.mp3 si traductions présentes)
"""
import os
import sys
import json
import subprocess
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "site" / "audio"
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")

VOICE_MAP = {
    "fr": ("fr-FR-DeniseNeural", "fr-FR-HenriNeural"),
    "de": ("de-CH-LeniNeural", "de-CH-JanNeural"),
    "it": ("it-IT-ElsaNeural", "it-IT-DiegoNeural"),
}

DIALOGUE_PROMPT = """Tu écris le script d'un podcast à deux voix (une animatrice curieuse « A », un expert « B ») style NotebookLM, sur la veille des mini-publics et de la démocratie délibérative en Suisse.

À partir du contenu ci-dessous, produis un dialogue VIVANT (pas une lecture !) : A pose des questions, réagit, s'étonne ; B explique, contextualise, donne l'essentiel des fiches. 10 à 16 échanges courts. Ouvre avec une accroche, ferme avec une synthèse des points à suivre. Langue : {lang_name}.

Réponds UNIQUEMENT en JSON : {{"dialogue": [{{"speaker": "A", "text": "..."}}, {{"speaker": "B", "text": "..."}}]}}

LANGUE IMPÉRATIVE : 100 % des répliques en {lang_name} — AUCUN mot d'une autre langue, même pas les titres d'articles (traduis-les ou paraphrase-les).

CONTENU :
"""


def lang_name(lang):
    return {"fr": "français", "de": "allemand (suisse)", "it": "italien"}[lang]


def gemini_json(prompt, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}"
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "responseMimeType": "application/json"},
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    return json.loads(d["candidates"][0]["content"]["parts"][0]["text"])


def load_context(md_path: Path, date: str):
    ctx = md_path.read_text(encoding="utf-8")
    fiche = BASE / "digests" / f"fiches-{date}.json"
    if fiche.exists():
        ctx += "\n\nFICHES DÉTAILLÉES :\n" + fiche.read_text(encoding="utf-8")[:20000]
    return ctx[:40000]


def ensure_edge_tts():
    try:
        import edge_tts  # noqa
        return True
    except ImportError:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "edge-tts"],
                           check=True, timeout=300)
            return True
        except Exception as e:
            print(f"edge-tts non installable : {e}")
            return False


def ensure_ffmpeg():
    """Retourne un exécutable ffmpeg : binaire système sinon imageio-ffmpeg (pip, statique)."""
    import shutil
    f = shutil.which("ffmpeg")
    if f:
        return f
    try:
        import imageio_ffmpeg  # noqa
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "imageio-ffmpeg"],
                       check=True, timeout=600)
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def synth_dialogue(dialogue, lang, out_mp3: Path):
    """Synthèse réplique par réplique (2 voix) + assemblage ffmpeg."""
    import asyncio
    import edge_tts
    v1, v2 = VOICE_MAP.get(lang, VOICE_MAP["fr"])
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_mp3.parent / f".tmp-{out_mp3.stem}"
    tmp.mkdir(exist_ok=True)
    segs = []
    for i, line in enumerate(dialogue):
        voice = v1 if line.get("speaker", "A") == "A" else v2
        text = line["text"].strip()
        if not text:
            continue
        seg = tmp / f"{i:03d}.mp3"
        asyncio.run(edge_tts.Communicate(text, voice).save(str(seg)))
        segs.append(seg)
    if not segs:
        raise RuntimeError("aucune réplique synthétisée")
    listing = tmp / "list.txt"
    listing.write_text("".join(f"file '{s.name}'\n" for s in segs), encoding="utf-8")
    ffmpeg = ensure_ffmpeg()
    subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c:a", "libmp3lame", "-q:a", "4", str(out_mp3)],
                   check=True, timeout=600, capture_output=True)
    for s in segs:
        s.unlink()
    listing.unlink()
    tmp.rmdir()


def make_podcast(md_path: Path, out_mp3: Path, lang: str, key: str):
    date = md_path.stem.replace("digest-", "").split(".")[0]
    script = gemini_json(
        DIALOGUE_PROMPT.format(lang_name=lang_name(lang)) + load_context(md_path, date), key)
    dialogue = script.get("dialogue", [])
    if len(dialogue) < 4:
        raise RuntimeError("script de dialogue trop court")
    synth_dialogue(dialogue, lang, out_mp3)
    print(f"Podcast {lang} OK (dialogue {len(dialogue)} répliques) → {out_mp3.name}")


def _md_to_speech_text(md_text: str) -> str:
    """Aplatit un digest Markdown en texte parlable (titre + résumés des items)."""
    import re
    lines = []
    for line in md_text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            s = s.lstrip("#").strip()
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)          # gras
        s = re.sub(r"\[(.+?)\]\((https?://[^)]+)\)", r"\1", s)  # liens → texte seul
        s = re.sub(r"https?://\S+", "", s).strip(" -–—*")
        if s:
            lines.append(s + ".")
    return " ".join(lines)


def edge_fallback(md_path: Path, out_mp3: Path, lang: str):
    """Fallback garanti : narration simple 1 voix via edge-tts (voix neurales Edge)."""
    voices = {
        "fr": "fr-FR-DeniseNeural",
        "de": "de-CH-LeniNeural",
        "it": "it-IT-ElsaNeural",
    }
    voice = voices.get(lang, voices["fr"])
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "--quiet", "edge-tts"],
                       check=True, timeout=300)
        import edge_tts
    except Exception as e:
        print(f"Fallback edge-tts indisponible : {e}")
        return False
    text = _md_to_speech_text(md_path.read_text(encoding="utf-8"))[:4500]
    out_mp3.parent.mkdir(parents=True, exist_ok=True)
    try:
        communicate = edge_tts.Communicate(text, voice)
        import asyncio
        asyncio.run(communicate.save(str(out_mp3)))
    except Exception as e:
        # Certains runtimes ont déjà une boucle asyncio : cheminement CLI direct
        try:
            subprocess.run([sys.executable, "-m", "edge_tts", "--voice", voice,
                            "--text", text, "--write-media", str(out_mp3)],
                           check=True, timeout=300)
        except Exception as e2:
            print(f"Fallback edge-tts échec (non fatal) : {e} / {e2}")
            return False
    print(f"Podcast {lang} (fallback edge-tts) OK → {out_mp3}")
    return True


def main():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        print("GEMINI_API_KEY absent — audio sauté")
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
                if not ensure_edge_tts():
                    print("edge-tts indisponible — audio sauté")
                    break
                make_podcast(md, out, lang, key)
            ok += 1
        except Exception as e:
            print(f"Podcast {lang} ÉCHEC (non fatal) : {e}")
            if edge_fallback(md, out, lang):
                ok += 1
    print(f"Audio : {ok}/{len(targets)} fichiers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
