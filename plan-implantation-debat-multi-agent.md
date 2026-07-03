# Plan d'implantation — Débat multi-agent (MAD) · `jarvis-debate-fable`

**Version :** 2 (décisions utilisateur intégrées) · 3 juillet 2026

## Décisions actées

| Sujet | Décision |
|---|---|
| Repo | `jarvis-debate-fable`, branche `main` (prototype sur `proto`) |
| Seuils go/no-go | Proposés par le prototype, **validés explicitement par l'utilisateur** avant chaque passage de phase — aucun seuil auto-appliqué |
| Critères du routeur (Phase 3) | Définis plus tard, hors périmètre actuel |
| Langue | **Étape de traduction/enrichissement du prompt (FR → EN enrichi) avant chaque envoi aux modèles locaux** ; sortie finale restituée en français |
| Pattern RAG anti-hallucination | **MAD-Fact** (débat multi-agent pour l'évaluation de factualité, arXiv:2510.22967) |

## Garde-fous issus de la recherche (invariants, toutes phases)

- 2 débatteurs + 1 juge maximum ; jamais de débat symétrique à N agents
- 2 tours maximum, arrêt anticipé si convergence (arrêt adaptatif > tours fixes)
- Personas explicitement différenciés (rôles identiques = dégradation démontrée, cf. ChatEval)
- Toute config de débat est mesurée contre une baseline single-agent (CoT + Self-Consistency) ; sans gain validé par l'utilisateur, pas de déploiement
- Chaque échec du prototype est classé selon la taxonomie MAST : (i) spécification, (ii) désalignement inter-agents, (iii) vérification/terminaison

---

## Phase 0 — Mise en place

**Objectif :** repo, harnais de mesure et jeux de test prêts avant d'écrire le moindre agent.
**Livrables :** repo initialisé, `DECISION.md`, 3 jeux de test, logger JSON.
**Critère de sortie :** l'utilisateur valide les seuils proposés dans `DECISION.md`.

### 0.1 Structure du repo `jarvis-debate-fable`

```
jarvis-debate-fable/
├── README.md
├── DECISION.md              # seuils go/no-go (proposés, puis validés utilisateur)
├── docs/
│   ├── plan-implantation.md         # ce fichier
│   └── references-mad.md            # base documentaire issue de la recherche
├── datasets/
│   ├── archi/     # décisions d'architecture (Phase 1)
│   ├── facts/     # chunks vrais/faux (Phase 2, format MAD-Fact)
│   └── reasoning/ # questions de raisonnement (Phase 3)
├── proto/
│   ├── translate_enrich.py   # étape FR → EN enrichi (décision actée)
│   ├── debate_local.py       # orchestrateur Ollama 2+1
│   ├── baseline.py           # CoT + Self-Consistency single-agent
│   └── logger.py             # JSON par débat
└── results/                  # logs JSON, un fichier par run
```

### 0.2 `DECISION.md` — gabarit des seuils (valeurs à valider par l'utilisateur)

Pour chaque phase, trois seuils sont proposés après les premiers runs, jamais fixés d'avance :
- **Gain minimal** : écart de précision débat vs baseline (points de %)
- **Budget maximal** : ratio tokens et temps CPU débat/baseline accepté
- **Fiabilité** : taux maximal d'échecs MAST-(iii) (non-terminaison, verdict absent)

Processus : le prototype produit un tableau de mesures → proposition de seuils → **validation utilisateur écrite dans DECISION.md** → alors seulement go/no-go.

### 0.3 Jeux de test (10-20 items chacun)

- `datasets/archi/` : décisions passées de `jarvis-fable` à vérité connue (MeloTTS vs Piper ; VRM vs Ready Player Me ; hybride navigateur+Python vs full-browser), format : question, contexte, contraintes (gratuit/local/licence), décision correcte, justification.
- `datasets/facts/` : chunks issus des inventaires `data-automated-extractor`, moitié exacts, moitié altérés (métrique changée, licence erronée, ressource dépréciée présentée comme active) — les altérations reproduisent les erreurs réelles du domaine. Format aligné MAD-Fact : chunk, claims atomiques, label par claim.
- `datasets/reasoning/` : questions de raisonnement type usage Jarvis, avec réponse attendue.

### 0.4 Étape de traduction/enrichissement (nouvelle, décision actée)

`translate_enrich.py` : reçoit la requête/le contexte en français → produit un prompt anglais enrichi (terminologie technique explicitée, contraintes reformulées, format de sortie imposé) → c'est ce prompt qui part vers les modèles → la restitution finale vers l'utilisateur repasse en français.
- Le traducteur est le même modèle local (appel séparé, prompt de traduction dédié) — pas de service externe.
- À mesurer dès la Phase 2 : coût ajouté (1 appel de plus) vs gain de qualité du raisonnement en anglais. Si le gain est nul, l'étape saute (mesure, pas dogme).

### 0.5 Logger

Un JSON par débat : id, phase, config (modèles, temp., personas), prompts (FR source + EN enrichi), tours, tokens in/out, temps, verdict débat, verdict baseline, vérité terrain, catégorie MAST si échec.

---

## Phase 1 — Débat d'architecture dans Claude Code (démarrage)

**Objectif :** pattern de débat contradictoire réutilisable dans l'orchestration `.claude/agents/` existante, validé sur des décisions d'archi réelles.
**Livrables :** 3 fichiers agents, Flux C dans `CLAUDE.md`, fiche de décision structurée, tableau comparatif débat vs agent unique.
**Critère de sortie :** go/no-go validé utilisateur selon `DECISION.md`.

### 1.1 Agents (`.claude/agents/`)

- `debate-advocate.md` — défend la solution proposée : bénéfices, faisabilité, alignement avec la stack existante. Interdiction de mentionner les risques (c'est le rôle d'en face).
- `debate-challenger.md` — cherche exclusivement les risques : licence, lock-in, viabilité long terme, perf CPU/iGPU, couverture FR, biais géographique des sources. Checklist calquée sur tes principes actés (Ready Player Me comme cas d'école).
- `debate-judge.md` — ne débat pas ; pondère les arguments, exige les sources, tranche, remplit la fiche de décision. Peut rendre « indécidable — information manquante » (sortie valide, pas un échec).

### 1.2 Flux C dans `CLAUDE.md`

Déclencheur : `débat : [question d'architecture]`
1. Orchestrateur racine formule la question + contexte (contraintes non négociables injectées automatiquement)
2. Advocate et Challenger produisent leur position **en parallèle, sans voir l'autre** (tour 1)
3. Chacun reçoit la position adverse, une seule réfutation (tour 2, dernier)
4. Judge tranche → **fiche de décision** (contrat de données, même logique que la fiche avatar) : question, options, arguments retenus/rejetés, décision, conditions de réversibilité, sources
5. Arrêt anticipé : si les positions du tour 1 convergent déjà, le juge tranche sans tour 2

Contrainte respectée : les subagents ne peuvent pas orchestrer d'autres subagents → toute l'orchestration reste dans `CLAUDE.md` racine, les 3 agents sont des feuilles.

### 1.3 Protocole d'évaluation

Chaque item de `datasets/archi/` passe : (a) agent unique avec le même contexte, (b) Flux C. Comparaison sur décision correcte, qualité des justifications, risques identifiés. Tableau → proposition de seuils → validation utilisateur → go/no-go.

### 1.4 Issues du no-go

Si no-go : rapport MAST des échecs, le pattern est archivé documenté, Phase 2 démarre sans dépendance à la Phase 1.

---

## Phase 2 — Vérification factuelle RAG, pattern MAD-Fact (data-automated-extractor)

**Objectif :** vérificateur de chunks avant indexation, aligné sur MAD-Fact, en local.
**Livrables :** `debate_local.py` opérationnel, comparatif config homogène vs hétérogène, mesures RAM/latence réelles laptop, recommandation d'intégration pipeline.
**Critère de sortie :** go/no-go validé utilisateur.

### 2.1 Adaptation du pattern MAD-Fact au contexte local

MAD-Fact cible l'évaluation de factualité en génération longue ; adaptation ici :
1. Décomposition du chunk en claims atomiques (1 appel)
2. Par claim : débat 1 tour — « affirmateur » (le claim est soutenu par le contexte/les sources) vs « sceptique » (cherche contradiction, absence de source, obsolescence)
3. Juge : label par claim (soutenu / contredit / invérifiable) + score de confiance
4. Agrégation : chunk accepté, rejeté ou marqué « à vérifier humainement »
Un seul tour (pas deux) : c'est le meilleur rapport coût/bénéfice attendu vu la contrainte CPU ; le second tour ne sera testé que si le premier échoue de peu.
Toutes les requêtes passent par `translate_enrich.py` (0.4).

### 2.2 Test A/B de composition (question laissée ouverte, résolue par mesure)

- **Config A (homogène)** : 2 instances Qwen 3 3-4B quantifié, températures et personas différents
- **Config B (hétérogène)** : Qwen 3 + Gemma 3B
- Mesures RAM à documenter honnêtement : chargement simultané des 2 modèles vs séquentiel (swap) sur 8-16 Go ; le séquentiel double le temps mais tient en mémoire — l'arbitrage sera chiffré, pas supposé.

### 2.3 Métriques

Sur `datasets/facts/` : précision/rappel de détection d'erreur par claim, faux positifs (bons chunks rejetés = coût de re-travail), tokens, temps CPU par chunk, extrapolation au volume réel de l'inventaire (~110 → 300+ ressources). Baseline : un seul modèle, prompt « vérifie ce chunk » en CoT.

### 2.4 Intégration (si go)

Position dans le pipeline `data-automated-extractor` : à décider ensemble au moment du go (options : à l'extraction, avant indexation, ou audit périodique du corpus).

---

## Phase 3 — Raisonnement du Jarvis local

**Objectif :** décider si le débat entre dans la boucle conversationnelle de l'avatar — phase la plus risquée (latence perçue).
**Critère de sortie :** go/no-go validé utilisateur ; en cas de no-go, le débat reste un outil hors-ligne (Phases 1-2), décision parfaitement acceptable.

- 3.1 Reprendre la config gagnante de la Phase 2 (A ou B)
- 3.2 Routeur débat/réponse directe : **critères définis plus tard** (décision actée) — la phase ne démarre pas avant que ce point soit cadré ensemble
- 3.3 Latence bout-en-bout sur laptop cible, incluant l'étape de traduction ; seuil d'acceptabilité pour l'avatar temps réel proposé puis validé utilisateur
- 3.4 Go/no-go final

---

## Phase 4 — Consolidation

- 4.1 Extraction du code retenu : `jarvis-debate-fable/proto` → `jarvis-test` (validation) → `jarvis` (prod) ; le proto est archivé, jamais mergé tel quel
- 4.2 Documentation des patterns retenus **et rejetés** au format JSON standardisé des inventaires (mêmes champs), intégrée à la base de connaissances

---

## Points encore ouverts (aucune initiative prise)

1. Valeurs chiffrées des seuils `DECISION.md` — proposées après premiers runs, validées par toi
2. Position du vérificateur MAD-Fact dans le pipeline (2.4)
3. Critères du routeur Phase 3 (décision actée : plus tard)
4. Contenu exact des 3 jeux de test — je peux proposer les items, tu valides avant usage
