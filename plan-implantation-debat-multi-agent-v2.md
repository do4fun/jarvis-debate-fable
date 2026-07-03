# Plan d'implantation — Débat multi-agent (MAD) · `jarvis-debate-fable` · v3

**Version :** 3 (intègre les 10 corrections de l'audit `audit-plan-mad-v2.md`) · 3 juillet 2026
**Principe directeur ajouté en v3 :** *debate on evidence, not on memory* — tout débat porte sur « l'évidence sourcée soutient-elle le claim ? », jamais sur « le claim est-il vrai ? ».

## Décisions actées (inchangées depuis v2)

| Sujet | Décision |
|---|---|
| Repo | `jarvis-debate-fable`, branche `main` (prototype sur `proto`) |
| Seuils go/no-go | Proposés par le prototype, **validés explicitement par l'utilisateur** avant chaque passage de phase |
| Critères du routeur (Phase 3) | Définis plus tard, hors périmètre actuel |
| Langue | Traduction/enrichissement FR→EN avant chaque envoi aux modèles locaux ; sortie finale en français |
| Pattern RAG anti-hallucination | MAD-Fact, **révisé v3** : débat sur évidence, pas sur mémoire paramétrique |

## Garde-fous (invariants, toutes phases — révisés v3)

- 2 débatteurs + 1 juge maximum ; jamais de débat symétrique à N agents
- 2 tours maximum, **arrêt anticipé conditionné aux citations concordantes** (pas au simple accord — correction F3)
- Personas explicitement différenciés
- Toute config de débat mesurée contre une **baseline à budget compute égal** (correction F7)
- Chaque échec du prototype classé selon la taxonomie MAST
- **Nouveau v3 :** aucun débat sans fiche de faits sourcée ; mémoire paramétrique disqualifiée pour tout claim postérieur au cutoff du modèle
- **Nouveau v3 :** juge en double passage à ordre inversé, divergence → « indécidable » (correction F6)
- **Nouveau v3 :** débats stateless — aucun verdict précédent transmis au contexte d'un autre débat (correction F5 / propagation d'erreur)

---

## Phase 0 — Mise en place

**Objectif :** repo, harnais de mesure, jeux de test **et infrastructure d'évidence** prêts avant d'écrire le moindre agent.
**Livrables :** repo initialisé, `DECISION.md`, 3 jeux de test (doubles variantes), corpus archivé + index de retrieval, script de traduction validé, logger JSON.
**Critère de sortie :** l'utilisateur valide les seuils proposés dans `DECISION.md`.

### 0.1 Structure du repo `jarvis-debate-fable`

```
jarvis-debate-fable/
├── README.md
├── DECISION.md                  # seuils go/no-go + budget compute baseline (corr. F7)
├── docs/
│   ├── plan-implantation.md             # ce fichier (v3)
│   ├── references-mad.md                # base documentaire
│   └── audit-plan-mad-v2.md             # audit archi (traçabilité des corrections)
├── datasets/
│   ├── archi/        # Phase 1, double variante (corr. F9)
│   ├── facts/         # Phase 2, format claim + évidence (corr. F1)
│   └── reasoning/     # Phase 3
├── corpus/
│   ├── raw/            # pages archivées (HTML + hash + horodatage) — corr. Axe 2.1/2.4
│   ├── chunks/          # découpage sémantique + métadonnées (corr. Axe 2.2)
│   └── index/            # index BM25 local (corr. Axe 2.2 §4)
├── proto/
│   ├── acquire.py          # crawl SearXNG + trafilatura, archivage (nouveau 0.6)
│   ├── chunk_and_index.py  # chunking sémantique + métadonnées + BM25 (nouveau 0.6)
│   ├── translate_enrich.py # FR→EN, extraction verbatim des tokens sensibles (corr. F8)
│   ├── evidence_match.py   # appariement claim ↔ évidence (nouveau 0.6)
│   ├── debate_local.py     # orchestrateur Ollama 2+1, fiches de faits (corr. Axe 3)
│   ├── baseline.py         # self-consistency à budget compute égal (corr. F7)
│   └── logger.py           # JSON par débat + hash évidence (corr. Axe 2.4)
└── results/
```

### 0.2 `DECISION.md` — gabarit des seuils (révisé v3)

Pour chaque phase, seuils proposés après premiers runs puis validés par l'utilisateur :
- **Gain minimal** débat vs baseline **à budget compute égal** (correction F7 — plus de comparaison 1 appel vs 9)
- **Budget maximal absolu** : plafond de tokens/temps CPU par claim ET extrapolation chiffrée au corpus entier (correction F4 — le plan v2 ne bornait que le ratio par item, pas le total ~4 500 appels estimés pour ~300 ressources)
- **Fiabilité** : taux maximal d'échecs MAST-(iii)
- **Nouveau v3 — Fidélité traduction** : taux d'accord sur le test aller-retour FR→EN→FR (correction F8), en dessous duquel l'étape 0.4 est bloquante

### 0.3 Jeux de test — révisés v3

- `datasets/archi/` — **double variante par item** (correction F9) : (a) avec les contraintes non négociables injectées automatiquement par le Flux C, qui déterminent souvent la réponse à elles seules ; (b) sans ces contraintes, pour isoler la valeur ajoutée réelle du débat. Ajout d'items pièges dont la bonne réponse contredit l'intuition de surface.
- `datasets/facts/` — **révisé pour le format évidence** (correction F1) : chaque item = chunk + claims atomiques + **évidences associées avec niveau N1/N2/N3** (Axe 2.3) + label vérité terrain + date de publication. Moitié des claims postérieurs au cutoff connu du modèle local, pour tester spécifiquement la correction F2.
- `datasets/reasoning/` — inchangé v2.

### 0.4 Traduction/enrichissement — révisée v3 (correction F8)

`translate_enrich.py` : avant traduction, extraction verbatim des tokens sensibles (noms propres, numéros de version, termes de licence, chiffres) via regex/NER léger, remplacés par des jetons opaques (`__TOK1__`) ; seul le tissu conjonctif est traduit ; ré-injection verbatim après traduction. Traduction une seule fois par chunk (pas par claim ni par tour — correction F4).
**Test de fidélité aller-retour obligatoire en Phase 0** : FR→EN→FR sur `datasets/facts/`, comparaison automatique des claims avant/après, taux d'accord versé dans `DECISION.md` (0.2).

### 0.5 Logger — révisé v3

Un JSON par débat : id, phase, config (modèles, températures, personas), fiche de faits envoyée (IDs claims/évidences, pas le texte brut — cf. 3.1 du plan agent), tours, résumés structurés échangés, tokens in/out par appel, temps, verdict débat (avec IDs cités), verdict baseline à budget égal, vérité terrain, **hash de l'évidence utilisée** (correction Axe 2.4 — permet l'invalidation par re-crawl), catégorie MAST si échec.

### 0.6 Infrastructure d'évidence (nouveau — correction F1, Axe 2)

Étape ajoutée avant tout débat, absente du plan v2.

1. **Acquisition** (`acquire.py`) : recherche via **SearXNG auto-hébergé** (pas Tavily/Perplexity — API cloud incompatibles avec la contrainte 100 % local) ; extraction de contenu propre via **trafilatura** (texte + métadonnées : date, auteur, langue). Chaque page archivée localement avec hash + horodatage de capture. Assumé et documenté : cette étape ponctuelle sort sur le réseau (recherche), le débat lui-même tourne ensuite 100 % hors ligne sur le corpus archivé — séparation acquisition/vérification.
2. **Chunking sémantique** (`chunk_and_index.py`) : découpage aligné sur les unités de sens (section, clause de licence, ligne de tableau de specs), 200-400 tokens cible, pas de découpage à taille fixe.
3. **Métadonnées par chunk** : URL source, date de publication, date de capture, licence du contenu, domaine, langue d'origine, **niveau de confiance N1 (primaire : arXiv/DOI/dépôt officiel/SPDX) / N2 (secondaire : blogs de recherche, actes) / N3 (tertiaire : agrégateurs, presse, forums)**.
4. **Index de retrieval local** : BM25 dans un premier temps (gratuit, CPU, zéro dépendance lourde) ; embeddings seulement si BM25 plafonne, mesuré et non supposé.
5. **Appariement claim ↔ évidence** (`evidence_match.py`) : pour chaque claim atomique du pipeline, retrieval des chunks pertinents dans le corpus local avant tout débat.

---

## Phase 1 — Débat d'architecture dans Claude Code

**Objectif :** pattern de débat contradictoire réutilisable dans `.claude/agents/`, validé sur des décisions d'archi réelles, **avec protocole d'évaluation non biaisé** (correction F9).
**Livrables :** 3 fichiers agents, Flux C dans `CLAUDE.md`, fiche de décision structurée, tableau comparatif débat vs agent unique vs self-consistency à budget égal, résultats en double variante.
**Critère de sortie :** go/no-go validé utilisateur selon `DECISION.md`.

### 1.1 Agents (`.claude/agents/`)

- `debate-advocate.md` — défend la solution proposée à partir des évidences fournies (bénéfices, faisabilité, alignement stack).
- `debate-challenger.md` — cherche les risques (licence, lock-in, viabilité, perf CPU/iGPU, couverture FR, biais géographique des sources) à partir de **toutes** les évidences disponibles, y compris contradictoires (asymétrie décrite en Axe 3.2 de l'audit — le challenger voit le panorama complet, l'advocate seulement les évidences favorables).
- `debate-judge.md` — **révisé v3** : ne débat pas, pondère les arguments selon le niveau de confiance des sources citées, exige des citations par ID, **passe deux fois avec l'ordre advocate/challenger inversé** (correction F6) ; divergence entre les deux passages → « indécidable — information manquante », sortie valide.

### 1.2 Flux C dans `CLAUDE.md` — révisé v3

Déclencheur : `débat : [question d'architecture]`
1. Orchestrateur formule la question ; **teste séparément avec et sans les contraintes non négociables auto-injectées** (correction F9) — deux runs, pas un seul
2. Advocate et Challenger produisent leur position en parallèle, sans voir l'autre (tour 1), **chacun citant les évidences par ID**
3. Échange inter-tours : **résumé structuré à format imposé** (position 1 ligne, arguments max 3 à 1 ligne chacun, IDs cités) — jamais la prose complète (correction F5, Axe 3.3)
4. Réfutation sur ce résumé (tour 2, dernier)
5. Arrêt anticipé uniquement si les positions du tour 1 convergent **avec citations concordantes** (correction F3) — sinon tour 2 obligatoire
6. Juge : double passage ordre inversé → fiche de décision (question, options, arguments retenus/rejetés, décision, conditions de réversibilité, sources par ID, niveau de confiance)

### 1.3 Protocole d'évaluation — révisé v3

Chaque item de `datasets/archi/`, en double variante, passe par : (a) agent unique, (b) self-consistency **à budget compute égal** au débat (correction F7 — si le débat consomme ~6 appels, la self-consistency échantillonne 6 fois + vote majoritaire), (c) Flux C. Comparaison sur décision correcte, qualité des justifications, risques identifiés, **et écart entre variante avec/sans contraintes** (ce dernier écart mesure la valeur ajoutée réelle du débat, pas la capacité à appliquer un filtre). Tableau → proposition de seuils → validation utilisateur → go/no-go.

### 1.4 Issues du no-go

Inchangé v2 : rapport MAST des échecs, pattern archivé documenté, Phase 2 démarre sans dépendance à la Phase 1.

---

## Phase 2 — Vérification factuelle RAG, pattern MAD-Fact révisé (data-automated-extractor)

**Objectif :** vérificateur de chunks avant indexation, **débattant sur évidence et non sur mémoire** (correction F1/F2), budget borné (correction F4).
**Livrables :** `evidence_match.py` + `debate_local.py` opérationnels, comparatif config homogène vs hétérogène, mesures RAM/latence réelles, extrapolation de coût chiffrée sur le corpus complet, recommandation d'intégration pipeline.
**Critère de sortie :** go/no-go validé utilisateur, incluant validation explicite du coût total extrapolé.

### 2.1 Pipeline révisé v3

1. Chunk source → décomposition en claims atomiques (1 appel)
2. Pour chaque claim : **retrieval d'évidence dans le corpus local** (0.6, pas d'appel modèle — BM25)
3. **Filtre pré-débat à 1 appel** (nouveau v3, correction F4) : le juge seul évalue le claim contre l'évidence retrouvée ; si confiance haute (soutenu ou contredit sans ambiguïté), verdict immédiat, **pas de débat déclenché**. Le débat n'est réservé qu'aux claims où le juge seul est incertain — inversion du plan v2 qui débattait systématiquement.
4. Pour les claims incertains : débat 1 tour — affirmateur vs sceptique, **chacun argumentant à partir de l'évidence retrouvée et de son niveau N1/N2/N3, jamais de la mémoire du modèle pour les claims postérieurs au cutoff** (correction F1/F2, garde-fou explicite dans le prompt système des deux débatteurs)
5. Juge : double passage ordre inversé (correction F6) → label par claim (soutenu / soutenu faible si N3 seul / contredit / invérifiable si aucune évidence trouvée) + score de confiance + IDs cités
6. Agrégation par chunk : accepté / rejeté / à vérifier humainement
Traduction une fois par chunk (0.4). Second tour de débat testé seulement si le premier échoue de peu (inchangé v2).

### 2.2 Test A/B de composition (question ouverte, résolue par mesure — inchangé v2)

- Config A (homogène) : 2 instances Qwen 3 3-4B, températures/personas différents
- Config B (hétérogène) : Qwen 3 + Gemma 3B, RAM mesurée (chargement simultané vs séquentiel)

### 2.3 Métriques — révisées v3

Sur `datasets/facts/` (format évidence, moitié post-cutoff) : précision/rappel de détection d'erreur par claim, faux positifs, tokens et temps CPU **par claim ET extrapolés au volume réel du corpus (~300+ ressources)** (correction F4), taux de claims correctement routés « invérifiable » en l'absence d'évidence (nouvelle métrique, teste directement la correction F1), taux de faux négatifs spécifiquement sur les claims post-cutoff (teste F2). Baseline : self-consistency à budget compute égal (correction F7), pas un simple appel unique.

### 2.4 Intégration (si go)

Inchangé v2 : position dans le pipeline `data-automated-extractor` décidée ensemble au moment du go. **Ajout v3** : mécanique d'invalidation par hash — si un re-crawl ultérieur change le hash d'une évidence, le verdict lié est automatiquement invalidé et le claim repasse en file de re-vérification (correction Axe 2.4).

---

## Phase 3 — Raisonnement du Jarvis local

**Objectif :** décider si le débat entre dans la boucle conversationnelle — phase la plus risquée (latence perçue).
**Critère de sortie :** go/no-go validé utilisateur.

- 3.1 Reprendre la config gagnante de la Phase 2, **y compris le filtre pré-débat à 1 appel** (correction F4 s'applique aussi ici — la latence conversationnelle rend le tri en amont d'autant plus critique)
- 3.2 Routeur débat/réponse directe : critères définis plus tard (décision actée, inchangée)
- 3.3 Latence bout-en-bout incluant traduction et filtre pré-débat ; seuil proposé puis validé utilisateur
- 3.4 Go/no-go final ; no-go = débat reste hors-ligne (Phases 1-2), décision acceptable

---

## Phase 4 — Consolidation

- 4.1 Extraction du code retenu : `jarvis-debate-fable/proto` → `jarvis-test` → `jarvis` ; le proto archivé, jamais mergé tel quel
- 4.2 Documentation des patterns retenus **et rejetés** au format JSON standardisé, intégrée à la base de connaissances — **incluant la traçabilité des corrections F1-F9 appliquées**, pour que la base documentaire garde la mémoire des raisons d'architecture, pas seulement le résultat

---

## Traçabilité des corrections intégrées

| Correction audit | Intégrée en | Description courte |
|---|---|---|
| F1 — circularité épistémique | 0.6, 2.1 | Débat sur évidence, jamais sur mémoire seule |
| F2 — cutoff vs fraîcheur | 0.3, 2.1, 2.3 | Claims post-cutoff routés évidence-only, métrique dédiée |
| F3 — sycophancie/arrêt anticipé | Invariants, 1.2 | Arrêt conditionné aux citations concordantes |
| F4 — gouffre à tokens | 0.2, 2.1, 2.3, 3.1 | Filtre pré-débat, plafonds, extrapolation chiffrée |
| F5 — saturation contexte | 1.2, Axe 3 | Résumés structurés, jamais de concaténation brute |
| F6 — biais de position du juge | Invariants, 1.2, 2.1 | Double passage ordre inversé |
| F7 — baseline à budget inégal | 0.2, 1.3, 2.3 | Self-consistency à budget compute égal |
| F8 — traduction non mesurée isolément | 0.2, 0.4 | Extraction verbatim + test fidélité aller-retour |
| F9 — contamination jeu de test | 0.3, 1.3 | Double variante avec/sans contraintes déterminantes |
| Axe 2.4 — obsolescence non détectée | 0.5, 2.4 | Invalidation par hash au re-crawl |

## Points encore ouverts (aucune initiative prise)

1. Valeurs chiffrées des seuils `DECISION.md`, y compris le plafond de coût total extrapolé (nouveau v3)
2. Position du vérificateur MAD-Fact dans le pipeline (2.4)
3. Critères du routeur Phase 3 (décision actée : plus tard)
4. Contenu exact des jeux de test en double variante, à proposer puis valider
5. **Nouveau v3** : confirmation que SearXNG auto-hébergé est acceptable pour la phase d'acquisition ponctuelle (seul maillon non 100 % local du plan, assumé et isolé du débat lui-même)
