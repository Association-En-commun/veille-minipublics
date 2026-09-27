#!/usr/bin/env python3
"""Génère le site statique (v0 vitrine) depuis les digests Markdown.
V0 volontairement minimaliste (stdlib) — sera remplacée par Astro Starlight trilingue
(phase 2, cf. ClickUp ECA-2611 §5) sans changer la pipeline amont.
Génère aussi : RSS feed, sitemap, llms.txt, robots.txt (couche GEO, §7).
"""
import re
import html
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SITE = BASE / "site"
DIGESTS = BASE / "digests"
AUDIO = SITE / "audio"

HTML_TMPL = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="Veille trilingue automatisée sur les mini-publics et la démocratie délibérative en Suisse — assemblées citoyennes, tirage au sort, panels.">
<link rel="alternate" type="application/rss+xml" href="feed.xml">
<link rel="alternate" type="application/rss+xml" href="podcast.xml">
<style>
:root {{ --ink:#1a2b4a; --accent:#2f6db4; --bg:#f7f8fa; }}
* {{ box-sizing:border-box; }}
body {{ font-family:system-ui,-apple-system,sans-serif; color:var(--ink); background:var(--bg); margin:0; }}
header {{ background:var(--ink); color:#fff; padding:2.5rem 1.5rem; }}
header h1 {{ margin:0 0 .4rem; font-size:1.7rem; }}
header p {{ margin:0; opacity:.85; }}
main {{ max-width:820px; margin:0 auto; padding:2rem 1.5rem; }}
article {{ background:#fff; border-radius:10px; padding:1.2rem 1.5rem; margin-bottom:1.2rem; box-shadow:0 1px 3px rgba(0,0,0,.08); }}
article h2 {{ margin:.1rem 0 .5rem; font-size:1.05rem; }}
article h2 a {{ color:var(--ink); text-decoration:none; }}
article h2 a:hover {{ color:var(--accent); }}
.meta {{ color:#6b7280; font-size:.85rem; }}
footer {{ text-align:center; color:#6b7280; font-size:.85rem; padding:2rem; }}
.badge {{ display:inline-block; background:#e8f0fb; color:var(--accent); border-radius:99px; padding:.1rem .6rem; font-size:.78rem; margin-left:.4rem; }}
</style>
</head>
<body>
<header>
<h1>MiniPublic Veille</h1>
<p>{subtitle}</p>
<p style="margin-top:.5rem">{nav}</p>
</header>
<main>
{articles}
</main>
<footer>
Veille automatisée assistée par IA — sources datées et liées · <a href="feed.xml">RSS</a> · <a href="llms.txt">llms.txt</a>
</footer>
</body>
</html>
"""


def parse_digest(path):
    text = path.read_text(encoding="utf-8")
    date_m = re.search(r"— (\d{4}-\d{2}-\d{2})", text.splitlines()[0])
    date = date_m.group(1) if date_m else path.stem
    # langue du digest : digest-X.fr.md → fr ; digest-X.de.md → de ; digest-X.md → fr
    stem = path.stem.replace("digest-", "")
    lang = stem.split(".")[-1] if "." in stem else "fr"
    if lang not in ("fr", "de", "it"):
        lang = "fr"
    articles = []
    blocks = re.split(r"\n## ", text)[1:]
    for b in blocks:
        lines = b.strip().splitlines()
        title = lines[0].strip()
        meta, link, summary = "", "", ""
        for ln in lines[1:]:
            if ln.startswith("- **Score**"):
                meta = ln
            elif ln.startswith("- **Lien**"):
                link = ln.replace("- **Lien** : ", "").strip()
            elif ln and not ln.startswith("-"):
                summary = ln
        if title:
            articles.append({"date": date, "title": title, "link": link,
                             "meta": meta, "summary": summary, "lang": lang})
    return date, articles


def lang_nav(active="fr"):
    labels = {"fr": "FR", "de": "DE", "it": "IT"}
    pages = {"fr": "index.html", "de": "de.html", "it": "it.html"}
    return " · ".join(
        (f"<strong>{labels[l]}</strong>" if l == active
         else f'<a href="{pages[l]}">{labels[l]}</a>')
        for l in ("fr", "de", "it")
    )


def main():
    dates = sorted((p for p in DIGESTS.glob("digest-*.md")), reverse=True)
    all_articles = []
    for p in dates[:30]:
        _, arts = parse_digest(p)
        all_articles.extend(arts)
    by_lang = {l: [a for a in all_articles if a["lang"] == l] for l in ("fr", "de", "it")}

    titles = {"fr": "MiniPublic Veille — la veille des mini-publics en Suisse",
              "de": "MiniPublic Veille — die Beobachtung der Bürgerräte in der Schweiz",
              "it": "MiniPublic Veille — l'osservatorio dei minipubblici in Svizzera"}
    subtitles = {"fr": "La veille trilingue des mini-publics et de la démocratie délibérative en Suisse",
                 "de": "Die trilinguale Beobachtung von Bürgerräten und deliberativer Demokratie in der Schweiz",
                 "it": "L'osservatorio trilingue dei minipubblici e della democrazia deliberativa in Svizzera"}

    # audios disponibles : site/audio/<date>.mp3 (+ .de/.it)
    audio_files = sorted(AUDIO.glob("*.mp3"), reverse=True) if AUDIO.exists() else []

    for lang in ("fr", "de", "it"):
        arts_html = []
        for a in by_lang[lang]:
            safe_title = html.escape(a["title"])
            link = html.escape(a["link"], quote=True)
            title_html = f'<a href="{link}" rel="noopener">{safe_title}</a>' if link else safe_title
            arts_html.append(
                f'<article><h2>{title_html}<span class="badge">{a["date"]}</span></h2>'
                f'<div class="meta">{html.escape(a["meta"])}</div>'
                f'<p>{html.escape(a["summary"])}</p></article>'
            )
        audio_html = ""
        for af in audio_files:
            if lang == "fr" and "." not in af.stem.replace("digest-", ""):
                pass
            elif f".{lang}" in af.name:
                pass
            else:
                continue
            audio_html += (
                f'<article class="audio"><h2>🎙️ Podcast — {af.stem}</h2>'
                f'<audio controls preload="none" src="audio/{af.name}"></audio></article>'
            )
        articles_block = ("\n".join(arts_html) or
                          ("<p>" + ("Aucun article traduit pour le moment." if lang != "fr" else "Aucun item pour le moment.") + "</p>"))
        page = HTML_TMPL.format(articles=audio_html + "\n" + articles_block,
                                nav=lang_nav(lang), title=titles[lang], subtitle=subtitles[lang])
        outname = {"fr": "index.html", "de": "de.html", "it": "it.html"}[lang]
        (SITE / outname).write_text(page, encoding="utf-8")

    # RSS feed principal (FR) + flux podcast avec enclosures audio (§8)
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    def rss_items(arts):
        out = []
        for a in arts[:30]:
            out.append(
                f"<item><title>{html.escape(a['title'])}</title>"
                f"<link>{html.escape(a['link'], quote=True)}</link>"
                f"<pubDate>{a['date']} 06:00:00 GMT</pubDate>"
                f"<description>{html.escape(a['summary'])}</description></item>"
            )
        return "".join(out)
    (SITE / "feed.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        "<title>MiniPublic Veille</title>"
        "<link>https://example.ch/</link>"
        "<description>Veille trilingue des mini-publics en Suisse</description>"
        f"<lastBuildDate>{now}</lastBuildDate>"
        + rss_items(all_articles) + "</channel></rss>",
        encoding="utf-8",
    )
    pod_items = ""
    for af in audio_files:
        d = af.stem
        pod_items += (
            f"<item><title>MiniPublic Veille — digest {d}</title>"
            f"<link>https://example.ch/audio/{af.name}</link>"
            f"<pubDate>{d} 06:00:00 GMT</pubDate>"
            f'<enclosure url="https://example.ch/audio/{af.name}" length="{af.stat().st_size}" type="audio/mpeg"/>'
            "</item>"
        )
    (SITE / "podcast.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd"><channel>'
        "<title>MiniPublic Veille Podcast</title>"
        "<link>https://example.ch/</link>"
        "<description>Podcast bilingue/trilingue des digests veille mini-publics</description>"
        f"<lastBuildDate>{now}</lastBuildDate>"
        + pod_items + "</channel></rss>",
        encoding="utf-8",
    )

    # robots.txt (crawlers IA autorisés) + llms.txt (par langue) + sitemap (§7)
    (SITE / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\n"
        "User-agent: GPTBot\nAllow: /\n"
        "User-agent: ClaudeBot\nAllow: /\n"
        "User-agent: PerplexityBot\nAllow: /\n"
        "User-agent: Google-Extended\nAllow: /\n"
        f"\nSitemap: https://example.ch/sitemap.xml\n",
        encoding="utf-8",
    )
    for lang in ("fr", "de", "it"):
        arts = by_lang[lang] or all_articles[:10]
        llms = [f"# MiniPublic Veille ({lang.upper()})", "",
                subtitles[lang] + ".",
                "Fiches datées et sourcées, générées par pipeline automatisée avec cadrage éditorial humain (En Commun).", ""]
        for a in arts[:20]:
            llms.append(f"- [{html.escape(a['title'])[:90]}]({a['link']}) : mini-publics/démocratie délibérative ({a['date']})")
        (SITE / f"llms.{lang}.txt").write_text("\n".join(llms), encoding="utf-8")
    top = all_articles[:20]
    llms = ["# MiniPublic Veille", "",
            "Veille trilingue (FR/DE/IT) des mini-publics et de la démocratie délibérative en Suisse.",
            "Fiches datées et sourcées, générées par pipeline automatisée avec cadrage éditorial humain (En Commun).", ""]
    for a in top:
        llms.append(f"- [{html.escape(a['title'])[:90]}]({a['link']}) : mini-publics/démocratie délibérative ({a['date']})")
    (SITE / "llms.txt").write_text("\n".join(llms), encoding="utf-8")
    (SITE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        '<url><loc>https://example.ch/</loc></url>'
        '<url><loc>https://example.ch/de.html</loc></url>'
        '<url><loc>https://example.ch/it.html</loc></url></urlset>',
        encoding="utf-8",
    )
    print(f"Site OK — {len(all_articles)} articles (fr:{len(by_lang['fr'])} de:{len(by_lang['de'])} it:{len(by_lang['it'])}), "
          f"{len(audio_files)} audios, feeds/robots/llms/sitemap générés")


if __name__ == "__main__":
    main()
