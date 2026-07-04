# PLAN_recherche_web.md — Étape [1] du pipeline (v4, fonctionnalité 2)

Rédigé à partir des spécifications de la fonctionnalité 2 dans
`plan-implantation-debat-multi-agent-v4.md` (point ouvert n°7). À relire et valider.

## Principe

La recherche web est **la première étape du pipeline, exécutée et close avant tout débat**.
Elle alimente le corpus local (0.6) ; le débat lui-même (étapes 2 à 7) reste 100 % hors ligne.
Un seul point d'ancrage par débat, quel que soit le nombre d'agents ou d'itérations en aval.

## Séquence (2 appels LLM au total)

1. **Formulation de la requête d'ancrage** (1 appel LLM)
   - Entrée : la question de débat brute.
   - Sortie : une requête de recherche courte, adaptée à un moteur type SearXNG (pas de
     reformulation par claim — une requête unique pour tout le débat).
2. **Recherche + acquisition** (0 appel LLM — `proto/acquire.py`)
   - Requête envoyée à une instance **SearXNG auto-hébergée** (`format=json`).
   - Résultats restreints aux **domaines de confiance** N1/N2 (liste blanche, cf. 0.6.3) ;
     N3 admis uniquement en repli explicite si aucun résultat N1/N2, et marqué comme tel dans
     les métadonnées (`fallback_n3: true`).
   - Chaque page retenue est archivée telle quelle dans `corpus/raw/` avec hash SHA-256 +
     horodatage de capture (permet l'invalidation par re-crawl, cf. Axe 2.4).
   - Extraction de contenu propre via **trafilatura** (texte + métadonnées : date de
     publication, auteur, langue, domaine).
3. **Échantillonnage ciblé**
   - Seuls le **titre/en-tête + les 3 premiers paragraphes pertinents** de chaque source
     entrent dans un prompt LLM. La page complète n'est jamais envoyée à un modèle — elle
     reste dans `corpus/raw/` pour l'indexation (0.6.4) et l'invalidation par hash.
4. **Validation indépendante avant injection** (1 appel LLM — rôle partagé avec le filtre
   pré-débat F4, pas un agent supplémentaire)
   - Vérifie : pertinence par rapport à la question, cohérence des métadonnées (date,
     domaine), niveau de confiance assigné (N1/N2/N3).
   - Seul le contenu validé est écrit dans la fiche de faits qui alimente les étapes
     suivantes du pipeline (brainstorming, thèse, antithèse).

## Garde-fous

- Aucun accès réseau après la clôture de cette étape (invariant v4) — vérifié par
  `PipelineConfig.enable_web_research` : une fois l'étape [1] terminée, le contexte de
  débat ne contient plus que des références à `corpus/` (chunks + métadonnées), jamais
  d'appel HTTP sortant.
- En Phase 3 (boucle conversationnelle Jarvis), cette étape est **désactivée par défaut**
  (latence + invariant hors-ligne) ; activation explicite réservée aux requêtes de veille,
  critères définis avec le routeur (3.2).

## Liste blanche des domaines de confiance (N1/N2) — à compléter

Placeholder initial, à valider et étoffer avec l'utilisateur avant le premier run corpus complet :

- **N1** (primaire) : `arxiv.org`, `doi.org`, dépôts officiels de projet (GitHub releases/tags,
  documentation officielle du dépôt SPDX), sites d'organismes de standardisation.
- **N2** (secondaire) : blogs de recherche d'équipes reconnues, actes de conférence, articles
  techniques signés et datés.
- **N3** (tertiaire, repli explicite uniquement) : agrégateurs, presse généraliste, forums.

## Implémentation

Voir `proto/acquire.py` (`formulate_anchor_query`, `search_and_archive`, `validate_sources`)
et `proto/pipeline.py` (étape `step_1_web_research`).
