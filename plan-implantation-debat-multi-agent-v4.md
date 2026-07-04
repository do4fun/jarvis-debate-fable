# Plan d'implantation — Débat multi-agent (MAD) · `jarvis-debate-fable` · v4

**Version :** 4 (v3 + intégration de 10 nouvelles fonctionnalités, après analyse de conflits) · 3 juillet 2026
**Principe directeur (inchangé) :** *debate on evidence, not on memory*.

---

## 0. Analyse de conflits des nouvelles fonctionnalités (lu avant intégration)

| Fonctionnalité | Verdict | Réconciliation appliquée |
|---|---|---|
| 1. Pipeline structuré (7 étapes) | ✅ Compatible | Thèse/antithèse = advocate/challenger existants ; le pipeline ajoute des *étapes*, pas des agents — l'invariant « 2 débatteurs + 1 juge » est préservé |
| 2. Recherche web économe | ⚠️ Réconcilié | Le v3 impose la séparation acquisition/débat (F1). La recherche web devient la **première étape du pipeline, exécutée et close avant tout débat** : elle alimente le corpus local, le débat reste 100 % hors ligne. Le « rôle de validation avant injection » fusionne avec le filtre pré-débat existant (F4). ⚠️ `PLAN_recherche_web.md` n'existe pas encore dans le repo — à fournir ou à rédiger |
| 3. Ordre de parole configurable | ✅ Compatible | Configurable, mais les **valeurs par défaut respectent les invariants v3** (tour 1 parallèle sans visibilité mutuelle — nécessaire à F3/F9) ; `wait_for` sert le pipeline inter-étapes, pas à ajouter des tours |
| 4. Modèle par agent/phase | ✅ Compatible | Généralise le test A/B homogène/hétérogène (2.2) — `AgentPersona.model` et `DebateConfig.phase_models` en sont la mécanique de configuration |
| 5. Argument graph | ✅ Compatible | Prolonge naturellement la fiche de faits : claims + relations support/attaque + Evidence citées par ID — la détection de conflits devient mécanique (arêtes d'attaque) au lieu d'être laissée au juge seul |
| 6. Consensus pondéré (Yin 2025 §3.3.4) | ⚠️ Réconcilié | Avec 2 débatteurs aux rôles imposés (pro/contra), un vote pondéré des stances n'a pas de sens seul. S(o) devient un **signal d'entrée du juge**, pas un remplaçant du juge. Le seuil θ est **proposé puis validé utilisateur** (règle DECISION.md). ⚠️ « Yin 2025 » absent de la base documentaire — référence à vérifier et ajouter à `references-mad.md` |
| 7. Trust weight persistant (EMA) | ⚠️ Réconcilié | **Tension réelle avec l'invariant « débats stateless »** (F5/MAD-M²). Résolution : le stateless porte sur le *contenu* (aucun verdict/claim antérieur dans le contexte d'un débat) ; le trust_weight est une **méta-donnée de pondération**, jamais injectée dans les prompts, appliquée uniquement au calcul S(o). Garde-fou ajouté : la mise à jour EMA n'est déclenchée que sur les items à vérité terrain connue (jeux de test) — jamais sur l'accord inter-agents seul, sinon boucle de renforcement de la sycophancie (F3) |
| 8. Crédibilité C(a_i) (§3.3.5) | ✅ Compatible | Formalise ce que le v3 faisait qualitativement : fiabilité = niveau N1/N2/N3, fraîcheur = date de publication/capture — les deux métadonnées existent déjà dans le corpus (0.6) |
| 9. Reprise sur interruption | ✅ Compatible | Pure infrastructure, aucun conflit ; d'autant plus utile que les runs corpus complets sont longs sur CPU (F4) |
| 10. Log complet par session | ⚠️ Réconcilié | Le v3 loggue dans `results/`, la fonctionnalité demande `rapports/sessions/`. Harmonisation proposée : `results/sessions/{session_id}_full.json` + `results/trust_weights.json` — **à valider** (ou adopter `rapports/` partout, ton choix) |

**Aucune fonctionnalité rejetée.** Trois points nécessitent ta validation (fin de document) : la référence Yin 2025, le nom du répertoire de logs, et la fourniture de `PLAN_recherche_web.md`.

---

## Décisions actées (inchangées)

| Sujet | Décision |
|---|---|
| Repo | `jarvis-debate-fable`, branche `main` (prototype sur `proto`) |
| Seuils go/no-go | Proposés par le prototype, validés explicitement par l'utilisateur — **inclut désormais θ (seuil de consensus) et les paramètres EMA du trust_weight** |
| Critères du routeur (Phase 3) | Définis plus tard |
| Langue | Traduction FR→EN enrichie avant envoi aux modèles ; sortie en français |
| Pattern RAG | MAD-Fact révisé : débat sur évidence |

## Garde-fous (invariants — v3 conservés, précisions v4)

- 2 débatteurs + 1 juge maximum (le pipeline à 7 étapes n'ajoute pas d'agents, il séquence le travail des trois rôles + outillage non-LLM)
- 2 tours maximum ; arrêt anticipé conditionné aux citations concordantes
- Personas différenciés ; baseline à budget compute égal ; taxonomie MAST
- Aucun débat sans fiche de faits sourcée ; mémoire paramétrique disqualifiée post-cutoff
- Juge en double passage à ordre inversé
- Débats stateless **sur le contenu** — précision v4 : le trust_weight persistant est une méta-donnée de pondération hors-contexte, jamais visible des agents
- **Nouveau v4 :** la recherche web est close avant le premier appel de débat ; aucun accès réseau pendant le débat

---

## Architecture du pipeline de débat (nouveau v4 — fonctionnalité 1)

Sept étapes séquencées, orchestrées par le harnais (`DebateConfig`) :

```
[1] Recherche web ──► [2] Brainstorming ──► [3] Thèse ──► [4] Antithèse
        │                                        (advocate)    (challenger)
        ▼                                               │
   corpus local                                         ▼
   (0.6, hors ligne          [7] Synthèse ◄── [6] Argument graph ◄── [5] Détection
    après cette étape)           (juge)          (claims/support/       de conflits
                                                  attaque/Evidence)      (mécanique)
```

- **[1] Recherche web** — fonctionnalité 2, exécutée une fois par débat puis close :
  - **Un seul point d'ancrage par débat** : 1 appel LLM pour formuler la requête d'ancrage à partir de la question, 1 appel LLM pour la validation — **2 appels LLM au total pour toute la phase de recherche, quel que soit le nombre d'agents/itérations en aval**
  - Sources restreintes aux **domaines de confiance** N1/N2 (liste blanche du 0.6.3) ; N3 admis en repli explicite, marqué comme tel
  - **Échantillonnage ciblé** : titre/en-tête + 3 premiers paragraphes pertinents par source — jamais la page complète dans un contexte LLM (la page complète est archivée dans `corpus/raw/` pour l'invalidation par hash, mais n'entre pas dans les prompts)
  - **Validation indépendante avant injection** : rôle spécialisé (le même appel que le filtre pré-débat F4, pas un agent supplémentaire) vérifie pertinence + métadonnées + niveau de confiance ; seul le contenu validé entre dans la fiche de faits
  - Spécification détaillée : `docs/PLAN_recherche_web.md` (**à fournir/rédiger — point ouvert n°7**)
- **[2] Brainstorming** : énumération des options/angles à partir de la fiche de faits (1 appel, modèle configurable par phase) — alimente les positions initiales sans les figer
- **[3]/[4] Thèse / Antithèse** : advocate et challenger v3, asymétrie d'évidence conservée, ordre de parole selon configuration (défaut : parallèle sans visibilité mutuelle)
- **[5] Détection de conflits** : mécanique (non-LLM) — extraction des paires claim/contre-claim depuis les citations par ID des deux positions
- **[6] Argument graph** — fonctionnalité 5 : graphe claims → relations `support`/`attack` → nœuds `Evidence` (ID, niveau, date, hash). Le graphe est la représentation canonique du débat ; le résumé structuré inter-tours (F5) en est une projection texte
- **[7] Synthèse** : le juge (double passage) reçoit le graphe + les scores S(o) et C(a_i) comme signaux, tranche, produit la fiche de décision

## Configuration (nouveau v4 — fonctionnalités 3 et 4)

- `AgentPersona.model` : modèle par agent — le test A/B (2.2) devient un cas particulier de cette config (A = deux personas sur le même modèle ; B = modèles distincts)
- `DebateConfig.phase_models` : override de modèle par étape du pipeline (ex. traduction et brainstorming sur le modèle le plus léger, synthèse sur le plus capable — arbitrage RAM mesuré, pas supposé)
- `DebateConfig.speaking_order` : `sequential` | `parallel` (défaut tour 1) | `dependencies` (tri topologique via `wait_for` entre étapes du pipeline)
- `DebateConfig.theta` : seuil d'acceptation du consensus — **valeur validée utilisateur via DECISION.md**

## Scoring et consensus (nouveau v4 — fonctionnalités 6, 7, 8)

- **Stance par agent** v_i(o) sur chaque option o, **score de consensus** S(o) = Σ trust_weight_i · v_i(o), **seuil θ** : S(o) ≥ θ requis pour qu'une option soit acceptable sans arbitrage renforcé (réf. Yin 2025 §3.3.4 — **référence à vérifier**, point ouvert n°6)
- **Crédibilité d'argument** C(a_i) (§3.3.5) : combinaison fiabilité des preuves citées (niveau N1=1.0 / N2=0.6 / N3=0.3 — pondérations initiales à valider) × fraîcheur (décroissance selon l'âge de la publication, claims post-cutoff évalués sur évidence seule, cf. F2)
- **Trust weight dynamique et persistant** : mis à jour par moyenne mobile exponentielle après chaque débat **à vérité terrain connue uniquement** (garde-fou anti-sycophancie), conservé entre sessions dans `results/trust_weights.json` (chemin à valider, point ouvert n°8). Jamais injecté dans les prompts — pondération pure côté harnais
- **Rôle du juge inchangé** : S(o), C(a_i) et le graphe sont des *entrées* du juge ; ils ne remplacent pas son verdict (avec 2 débatteurs aux rôles imposés, un vote pondéré seul serait dégénéré)

## Robustesse d'exécution (nouveau v4 — fonctionnalités 9 et 10)

- **Reprise sur interruption** : checkpoint sérialisé après **chaque appel LLM**, y compris pendant l'étape [1] de recherche web — un run corpus interrompu reprend au claim exact, pas au début (critique vu les volumes F4 sur CPU)
- **Log complet par session** : `results/sessions/{session_id}_full.json` — toutes les étapes du pipeline (requête d'ancrage, sources échantillonnées, fiche de faits, positions, graphe, scores S/C, verdicts des deux passages juge, trust_weights avant/après), en plus du log par débat du 0.5

---

## Phases (v3 conservées — seuls les ajouts v4 sont listés)

### Phase 0 — Mise en place

- 0.1 : arborescence complétée — `proto/pipeline.py` (orchestrateur 7 étapes), `proto/argument_graph.py`, `proto/scoring.py` (S, C, trust EMA), `proto/checkpoint.py` ; `results/sessions/` et `results/trust_weights.json` ; `docs/PLAN_recherche_web.md`
- 0.2 DECISION.md : ajout des seuils θ, pondérations N1/N2/N3 de C(a_i), et paramètres EMA (α, valeur initiale des trust_weights) — tous proposés après premiers runs, validés par toi
- 0.4-0.6 : inchangés ; l'étape [1] du pipeline réutilise `acquire.py` (SearXNG + trafilatura) en mode « point d'ancrage unique » au lieu du crawl batch — même code, deux modes
- **Nouveau 0.7** : implémentation du checkpoint/reprise et du schéma de session JSON — testés sur interruption volontaire avant toute campagne de mesure

### Phase 1 — Débat d'architecture Claude Code

- 1.2 Flux C : les étapes [2] brainstorming et [6] argument graph s'insèrent entre les points 2 et 6 du flux v3 ; la fiche de décision du juge référence le graphe (IDs de claims/arêtes) au lieu de reformuler les arguments
- 1.3 : la comparaison intègre une variante « pipeline complet » vs « débat nu v3 » — mesure ce que brainstorming + graphe apportent réellement, à budget compté

### Phase 2 — Vérification factuelle MAD-Fact

- 2.1 : pipeline v3 conservé tel quel ; l'argument graph remplace la sortie libre du débat de l'étape 4 ; S(o) et C(a_i) alimentent le juge de l'étape 5 ; checkpoint après chaque claim
- 2.2 : le test A/B utilise `AgentPersona.model` ; ajout d'un test C — `phase_models` mixte (léger pour décomposition/traduction, principal pour débat/juge), RAM et latence mesurées
- 2.3 : nouvelles métriques — corrélation entre C(a_i) et la vérité terrain (le score de crédibilité prédit-il quelque chose ?), dérive des trust_weights sur la durée (détection de boucle de renforcement)

### Phase 3 — Raisonnement Jarvis local

- 3.1 : la config gagnante inclut désormais le choix `phase_models` ; l'étape [1] recherche web est **désactivée par défaut** en boucle conversationnelle (latence + invariant hors-ligne) — le Jarvis débat sur le corpus déjà constitué ; activation explicite possible pour les requêtes de veille, critères à définir avec le routeur (3.2)

### Phase 4 — Consolidation

- 4.2 : les trust_weights finaux et leurs courbes de dérive font partie des livrables documentés (retenus **et rejetés**)

---

## Traçabilité (cumul v3 + v4)

Corrections F1-F9 + Axe 2.4 : voir tableau v3 (inchangé). Ajouts v4 :

| Fonctionnalité | Intégrée en |
|---|---|
| 1. Pipeline 7 étapes | Architecture pipeline, 1.2, 2.1 |
| 2. Recherche web économe | Étape [1], 0.4-0.6, garde-fou « réseau clos avant débat » |
| 3. Ordre de parole | DebateConfig.speaking_order |
| 4. Modèle par agent/phase | AgentPersona.model, phase_models, 2.2 test C |
| 5. Argument graph | Étapes [5]-[6], 1.2, 2.1 |
| 6. Consensus S(o), θ | Scoring, 0.2, juge inchangé |
| 7. Trust weight EMA persistant | Scoring, garde-fou vérité-terrain-only, 2.3 dérive |
| 8. Crédibilité C(a_i) | Scoring, adossée aux métadonnées N1-N3 + dates du 0.6 |
| 9. Reprise sur interruption | 0.7, checkpoints par appel |
| 10. Log complet session | results/sessions/, 0.5 |

## Points ouverts (aucune initiative prise)

1-4. Inchangés v3 (seuils DECISION.md, position pipeline, routeur, jeux de test)
5. Confirmation SearXNG pour l'acquisition (inchangé v3)
6. **Référence « Yin 2025 »** : introuvable dans notre base documentaire — peux-tu me donner le titre/lien exact pour que je la vérifie et l'ajoute à `references-mad.md` ?
7. **`PLAN_recherche_web.md`** : tu le fournis, ou je le rédige à partir des spécifications de la fonctionnalité 2 ?
8. **Répertoire de logs** : `results/sessions/` (harmonisé v3) ou `rapports/sessions/` (ta formulation) ?
9. Pondérations initiales N1/N2/N3 de C(a_i) et paramètres EMA — proposés après premiers runs, à valider
