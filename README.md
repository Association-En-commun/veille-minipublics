# MiniPublic Veille — prototype

Site de veille trilingue (FR/DE/IT) sur les mini-publics et la démocratie délibérative en Suisse.
Objectif : devenir la référence suisse du domaine, avec une chaîne de production majoritairement automatisée par IA.
Cadrage complet : ClickUp **ECA-2611** (architecture, GEO, syndication, intégration Odoo).

## Fonctionnement (autonome)

```
GitHub Actions (cron lun/mer/ven 06:00 UTC)
   → pipeline/veille.py      : collecte RSS → scoring (cadrage humain) → dédup → digest Markdown
   → pipeline/build_site.py  : site statique v0 + feed.xml + robots.txt (IA autorisés) + llms.txt + sitemap
   → commit & push           : le site se régénère à chaque run
```

- **Le thème = `config/sources.yaml`** (sources + mots-clés + seuil). Dupliquer le repo = nouvelle veille sur un autre thème.
- **Le cadrage humain (le "5%")** = la section `cadrage:` et la taxonomie. Un affinage LLM est prévu (secret `OPENAI_API_KEY`).
- **Site vitrine** : v0 minimale ici ; remplacée par Astro Starlight trilingue (phase 2) sans changer la pipeline amont.
- **Audio** : les digests sont conçus pour être lus par Podcastfy / TTS (`site/latest.md` = entrée standard).

## Utilisation locale

```bash
pip install pyyaml
python3 pipeline/veille.py       # génère digests/digest-YYYY-MM-DD.md
python3 pipeline/build_site.py   # génère site/
```

## Déploiement GitHub Pages (une fois le repo poussé)

Settings → Pages → Source: GitHub Actions, ou servir `site/` en statique.
Remplacer `https://example.ch` dans `build_site.py` par le domaine final.

## Étapes suivantes (ECA-2611)

1. Traduction FR→DE→IT des digests (étape LLM) + vues par langue
2. Couche audio Podcastfy → flux RSS podcast
3. Vitrine Astro Starlight (design EC Penpot-SVG)
4. Webhook Odoo (déclenchement + file de validation, §9)
