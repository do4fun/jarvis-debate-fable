# references-mad.md — Base documentaire

Références citées dans les plans d'implantation (`plan-implantation-debat-multi-agent*.md`)
et l'audit (`audit-plan-mad*.md`).

## Références confirmées

- **MAST** (Multi-Agent System failure Taxonomy) — taxonomie de classification des échecs
  utilisée pour catégoriser les défaillances du prototype (toutes phases).

## Références en attente de vérification

- **« Yin 2025 » §3.3.4 et §3.3.5** — cité dans `plan-implantation-debat-multi-agent-v4.md`
  comme base du consensus pondéré S(o) et de la crédibilité d'argument C(a_i). **Introuvable
  dans cette base documentaire** (point ouvert n°6 du plan v4). La mécanique S(o)/C(a_i) est
  implémentée dans `proto/scoring.py` indépendamment de cette citation — dès que le
  titre/lien exact est fourni, l'ajouter ici et référencer la section précise.

## Outillage externe (non-LLM)

- **SearXNG** — méta-moteur de recherche auto-hébergé, utilisé en étape [1] du pipeline
  (`proto/acquire.py`) pour l'unique requête d'ancrage par débat.
- **trafilatura** — extraction de contenu propre (texte + métadonnées) depuis les pages
  archivées.
- **BM25** — index de retrieval local (`proto/chunk_and_index.py`), implémentation pure
  Python interne au prototype (pas de dépendance lourde), embeddings envisagés seulement si
  BM25 plafonne (mesuré, non supposé).
