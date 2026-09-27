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

HTML_TMPL = """<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MiniPublic Veille — la veille des mini-publics en Suisse</title>
<meta name="description" content="Veille trilingue automatisée sur les mini-publics et la démocratie délibérative en Suisse — assemblées citoyennes, tirage au sort, panels.">
<link rel="alternate" type="application/rss+xml" href="feed.xml">
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
<p>La veille trilingue des mini-publics et de la démocratie délibérative en Suisse · FR / DE / IT</p>
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
            articles.append({"date": date, "title": title, "link": link, "meta": meta, "summary": summary})
    return date, articles


def main():
    dates = sorted((p for p in DIGESTS.glob("digest-*.md")), reverse=True)
    all_articles = []
    for p in dates[:30]:
        _, arts = parse_digest(p)
        all_articles.extend(arts)

    arts_html = []
    for a in all_articles:
        safe_title = html.escape(a["title"])
        link = html.escape(a["link"], quote=True)
        title_html = f'<a href="{link}" rel="noopener">{safe_title}</a>' if link else safe_title
        arts_html.append(
            f'<article><h2>{title_html}<span class="badge">{a["date"]}</span></h2>'
            f'<div class="meta">{html.escape(a["meta"])}</div>'
            f'<p>{html.escape(a["summary"])}</p></article>'
        )

    (SITE / "index.html").write_text(
        HTML_TMPL.format(articles="\n".join(arts_html) or "<p>Aucun item pour le moment.</p>"),
        encoding="utf-8",
    )

    # RSS feed (syndication tierce, §8)
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    items = []
    for a in all_articles[:30]:
        items.append(
            f"<item><title>{html.escape(a['title'])}</title>"
            f"<link>{html.escape(a['link'], quote=True)}</link>"
            f"<pubDate>{a['date']} 06:00:00 GMT</pubDate>"
            f"<description>{html.escape(a['summary'])}</description></item>"
        )
    (SITE / "feed.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        "<title>MiniPublic Veille</title>"
        "<link>https://example.ch/</link>"
        "<description>Veille trilingue des mini-publics en Suisse</description>"
        f"<lastBuildDate>{now}</lastBuildDate>"
        + "".join(items) + "</channel></rss>",
        encoding="utf-8",
    )

    # robots.txt (crawlers IA autorisés explicitement) + llms.txt + sitemap (§7)
    (SITE / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\n"
        "User-agent: GPTBot\nAllow: /\n"
        "User-agent: ClaudeBot\nAllow: /\n"
        "User-agent: PerplexityBot\nAllow: /\n"
        "User-agent: Google-Extended\nAllow: /\n"
        f"\nSitemap: https://example.ch/sitemap.xml\n",
        encoding="utf-8",
    )
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
        '<url><loc>https://example.ch/</loc></url></urlset>',
        encoding="utf-8",
    )
    print(f"Site OK — {len(all_articles)} articles, feed/robots/llms.txt/sitemap générés")


if __name__ == "__main__":
    main()
