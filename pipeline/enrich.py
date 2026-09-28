#!/usr/bin/env python3
"""Enrichissement des items du digest par LLM (Gemini) — phase « brief d'apprentissage ».
Pour chaque item retenu, produit une fiche structurée répondant aux questions En Commun :
qui porte, composition du MiniPublic, objet de délibération, rôle décisionnel/consultatif,
étapes de la procédure, état d'avancement à la publication, auteur/média, intérêt EC.
Guard : sans GEMINI_API_KEY → no-op. Sortie : digests/fiches-<date>.json
"""
import os
import re
import json
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

PROMPT = """Tu es analyste pour En Commun, bureau suisse expert des mini-publics (assemblées de citoyens tirés au sort) et de la démocratie délibérative.

À partir du titre et du résumé de l'article suivant (et de tes connaissances générales SI ET SEULEMENT SI elles sont fiables et directement liées), produis une fiche d'apprentissage structurée en JSON strict avec ces champs :
- "resume_detaille": 150-300 mots expliquant de quoi parle l'article, le contexte et l'essentiel à retenir
- "qui_porte": qui porte le dispositif/processus mentionné (institution, organisation, personne)
- "composition_minipublic": composition du mini-public si identifiable (nombre, mode de sélection, profils) sinon "Non précisé dans l'article"
- "objet_deliberation": objet précis de la délibération / des questions posées aux citoyens
- "role_decisionnel": rôle décisionnel ou consultatif du dispositif (que devient l'avis des citoyens ?)
- "etapes_procedure": étapes de la procédure passées et à venir (liste courte)
- "etat_avancement": où en est le processus au moment de la publication de l'article
- "date_publication": date de publication de l'article si elle est connue (sinon "Non précisée")
- "auteur_media": qui écrit l'article (journaliste/rédaction) et quel média, avec la ligne éditoriale apparente si connue
- "interet_ec": ce qu'En Commun peut apprendre ou réutiliser de ce cas (2-3 phrases, angle practice)

Règles : si une information n'est pas dans l'article, écris "Non précisé dans l'article" plutôt que d'inventer. Pas de markdown, JSON pur.
"""

ITEM_TMPL = """ARTICLE {i}:
Titre : {title}
Média/source : {source}
Résumé : {summary}
"""


def gemini_json(prompt, key):
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={key}")
    body = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
    }).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        d = json.loads(r.read().decode())
    return json.loads(d["candidates"][0]["content"]["parts"][0]["text"])


def parse_digest_items(text):
    items = []
    blocks = re.split(r"\n## ", text)[1:]
    for b in blocks:
        lines = b.strip().splitlines()
        title = lines[0].strip()
        meta, link, summary = {}, "", ""
        for ln in lines[1:]:
            if ln.startswith("- **Score**"):
                meta = ln
            elif ln.startswith("- **Lien**"):
                link = ln.replace("- **Lien** : ", "").strip()
            elif ln and not ln.startswith("-"):
                summary = ln
        src = re.search(r"Source : (\S+)", meta or "")
        items.append({"title": title, "link": link, "summary": summary,
                      "source": src.group(1) if src else ""})
    return items


def latest_digest():
    cands = sorted((BASE / "digests").glob("digest-*.md"),
                   key=lambda p: p.stem.replace("digest-", "").split(".")[0], reverse=True)
    return cands[0] if cands else None


def main():
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        print("GEMINI_API_KEY absent — enrichissement sauté")
        return 0
    src = latest_digest()
    if not src:
        print("Aucun digest — enrichissement sauté")
        return 0
    date = src.stem.replace("digest-", "").split(".")[0]
    items = parse_digest_items(src.read_text(encoding="utf-8"))
    if not items:
        print("Digest vide — enrichissement sauté")
        return 0

    fiches_path = BASE / "digests" / f"fiches-{date}.json"
    fiches = json.loads(fiches_path.read_text(encoding="utf-8")) if fiches_path.exists() else {}

    ok = 0
    for i, it in enumerate(items, 1):
        slug = re.sub(r"\W+", "-", it["title"].lower())[:60].strip("-")
        if slug in fiches:
            continue  # déjà enrichi
        try:
            fiche = gemini_json(
                PROMPT + "\n\n" + ITEM_TMPL.format(i=i, title=it["title"],
                                                   source=it["source"], summary=it["summary"]),
                key)
            fiche["title"] = it["title"]
            fiche["link"] = it["link"]
            fiche["source"] = it["source"]
            fiches[slug] = fiche
            ok += 1
        except Exception as e:
            print(f"Fiche {i} ÉCHEC (non fatal) : {e}")
    fiches_path.write_text(json.dumps(fiches, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Enrichissement : {ok}/{len(items)} fiches → {fiches_path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
