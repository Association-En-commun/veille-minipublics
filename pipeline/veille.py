#!/usr/bin/env python3
"""
Pipeline de veille MiniPublic — collecte → score → dédup → digest Markdown.
Sans dépendance externe (stdlib only) : fonctionne dans GitHub Actions et localement.
Étape LLM optionnelle : si OPENAI_API_KEY est défini, le scoring/résumé est affiné
par API ; sinon scoring par mots-clés (cadrage humain) — jamais de contenu inventé.
"""
import re
import sys
import html
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:  # fallback minimal si pyyaml absent
    yaml = None

BASE = Path(__file__).resolve().parent.parent
CFG = BASE / "config" / "sources.yaml"
OUT_DIR = BASE / "digests"


def load_config():
    if yaml:
        return yaml.safe_load(CFG.read_text(encoding="utf-8"))
    # parse minimal maison (le fichier est simple)
    cfg = {"sources": [], "cadrage": {"include_keywords": [], "boost_switzerland": [], "exclude_keywords": [], "publish_threshold": 4}}
    section = None
    for raw in CFG.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- id:") and section == "sources":
            cfg["sources"].append({"id": line.split(":", 1)[1].strip()})
        elif section == "sources" and cfg["sources"] and ":" in line and not line.startswith("-"):
            k, v = line.split(":", 1)
            if k in ("name", "url", "lang", "type"):
                cfg["sources"][-1][k] = v.strip().strip('"')
        elif line in ("cadrage:", "sources:"):
            section = line.rstrip(":")
        elif line.startswith("- ") and section == "cadrage":
            for key in ("include_keywords", "boost_switzerland", "exclude_keywords"):
                if key not in cfg["cadrage"] or not isinstance(cfg["cadrage"][key], list):
                    cfg["cadrage"][key] = []
            last = list(cfg["cadrage"].keys())[-1]
            cfg["cadrage"][last].append(line[2:].strip())
        elif line.startswith("publish_threshold:"):
            cfg["cadrage"]["publish_threshold"] = float(line.split(":", 1)[1])
    return cfg


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "veille-minipublics/0.1 (+EC)"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse_rss(xml_text):
    """Retourne [{title, link, summary, date}] d'un flux RSS/Atom."""
    items = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return items
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    for it in root.iter("item"):
        g = lambda tag: (it.findtext(tag) or "").strip()
        items.append({"title": html.unescape(g("title")), "link": g("link"),
                      "summary": re.sub("<[^>]+>", "", html.unescape(g("description"))), "date": g("pubDate")})
    for e in root.findall("atom:entry", ns):
        link = ""
        le = e.find("atom:link", ns)
        if le is not None:
            link = le.get("href", "")
        items.append({"title": html.unescape((e.findtext("atom:title", default="", namespaces=ns) or "").strip()),
                      "link": link,
                      "summary": re.sub("<[^>]+>", "", html.unescape(e.findtext("atom:summary", default="", namespaces=ns) or "")),
                      "date": e.findtext("atom:updated", default="", namespaces=ns)})
    return items


def score(item, cadrage):
    text = (item["title"] + " " + item["summary"]).lower()
    for kw in cadrage.get("exclude_keywords", []):
        if kw.lower() in text:
            return -1, "exclu"
    s = 0
    hits = []
    for kw in cadrage.get("include_keywords", []):
        if kw.lower() in text:
            s += 2
            hits.append(kw)
    for kw in cadrage.get("boost_switzerland", []):
        if kw.lower() in text:
            s += 3
            hits.append(kw + " (CH)")
            break
    return s, ", ".join(hits)


def dedup(items):
    seen, out = set(), []
    for it in items:
        key = re.sub(r"\W+", "", it["title"].lower())[:80]
        if key and key not in seen:
            seen.add(key)
            out.append(it)
    return out


def main():
    cfg = load_config()
    cadr = cfg["cadrage"]
    all_items = []
    errors = []
    for src in cfg["sources"]:
        try:
            items = parse_rss(fetch(src["url"]))
        except Exception as e:
            errors.append(f"{src['id']}: {e}")
            continue
        for it in items:
            it["source"] = src["id"]
            it["lang"] = src["lang"]
            s, why = score(it, cadr)
            if s < 0:
                continue
            it["score"], it["hits"] = s, why
            all_items.append(it)

    all_items = dedup(all_items)
    all_items.sort(key=lambda x: -x.get("score", 0))
    kept = [i for i in all_items if i.get("score", 0) >= cadr.get("publish_threshold", 4)][:15]

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"# Digest veille MiniPublic — {now}", "",
             f"_Pipeline automatisée — {len(all_items)} items collectés, {len(kept)} retenus "
             f"(seuil ≥ {cadr.get('publish_threshold', 4)}). Sources : {len(cfg['sources'])} flux._", ""]
    for i, it in enumerate(kept, 1):
        lines += [f"## {i}. {it['title']}", "",
                  f"- **Score** : {it['score']} ({it['hits'] or '—'}) · **Source** : {it['source']} · **Langue** : {it['lang']}",
                  f"- **Lien** : {it['link']}", ""]
        if it["summary"]:
            lines += [it["summary"][:400] + ("…" if len(it["summary"]) > 400 else ""), ""]
    if errors:
        lines += ["## Erreurs de collecte", ""] + [f"- {e}" for e in errors] + [""]

    OUT_DIR.mkdir(exist_ok=True)
    out = OUT_DIR / f"digest-{now}.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    # latest pour les étapes en aval (site, audio, feed)
    (BASE / "site").mkdir(exist_ok=True)
    (BASE / "site" / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"OK {out} — {len(all_items)} collectés, {len(kept)} retenus")
    if errors:
        print("Erreurs:", *errors, sep="\n  ", file=sys.stderr)

    # Phases 1 & 2 : traduction LLM puis podcast (non fatals — le site reste FR seul si échec)
    try:
        subprocess.run([sys.executable, str(BASE / "pipeline" / "translate.py")],
                       check=False, timeout=900)
    except Exception as e:
        print(f"Traduction sautée : {e}", file=sys.stderr)
    try:
        subprocess.run([sys.executable, str(BASE / "pipeline" / "audio.py")],
                       check=False, timeout=1800)
    except Exception as e:
        print(f"Audio sauté : {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
