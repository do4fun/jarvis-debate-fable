# jarvis-debate-fable

Prototype de débat multi-agent (MAD) — *debate on evidence, not on memory*.
Spécifications complètes : `plan-implantation-debat-multi-agent-v4.md` (et
v3 pour les phases inchangées — **v4 ne liste que les ajouts, les phases
elles-mêmes viennent de v3**), `audit-plan-mad-v2.md`, `DECISION.md`.

Deux implémentations coexistent, pour deux contextes d'exécution différents :

- **`proto/`** — pipeline Python à 7 étapes (Phase 0/2/3), pensé pour tourner
  hors session Claude Code (Ollama local, corpus archivé, batchs de mesure).
  `proto/pipeline.py` implémente le tour 2 et l'arrêt anticipé (F3) comme
  Flux C : le tour 1 (thèse/antithèse) alimente une détection de conflits
  mécanique ; si elle ne trouve rien (citations concordantes), le tour 2 est
  sauté ; sinon chaque débatteur réfute le résumé structuré de l'autre
  (`debate_local.generate_position(..., opposing_claims=...)`) avant que le
  graphe final (tour 1 + tour 2) n'aille au juge. Le brainstorming (étape
  [2]) est injecté dans les prompts de thèse/antithèse tour 1
  (`brainstorming_notes`), pas seulement loggé.
  `proto/fact_verification.py` + `proto/verdict_store.py` implémentent
  MAD-Fact (Phase 2, 2.1 + 2.4) : `verify_chunk()` décompose un chunk en
  claims atomiques, puis pour chaque claim — retrieval BM25, filtre
  pré-débat à 1 appel (F4, court-circuite le débat si confiant), débat 1
  tour affirmateur/sceptique réservé aux claims incertains, juge
  double-passage → label (checkpoint après chaque claim). Agrégation par
  chunk (`aggregate_chunk`), invalidation de verdict par hash au re-crawl
  (`proto/verdict_store.py`). `proto/metrics.py` (2.3) : précision/rappel de
  détection d'erreur, taux de routage « invérifiable » correct (F1), taux de
  faux négatifs post-cutoff (F2) — prêt, en attente de contenu réel dans
  `datasets/facts/` pour produire de vrais chiffres (2.2, test A/B modèles
  homogène/hétérogène, est déjà couvert par les paramètres
  `model_affirmateur`/`model_sceptique` de `verify_chunk` : rien à ajouter,
  juste à exécuter avec de vrais modèles une fois `datasets/facts/` rempli).
  `proto/jarvis_loop.py` (Phase 3) : `answer_or_debate()` route une question
  vers une réponse directe ou vers `run_pipeline()` selon un `router`
  injecté par l'appelant — **les critères du routeur (3.2) restent une
  décision actée « définie plus tard »**, `default_router` est un
  placeholder qui répond toujours directement, jamais une heuristique à
  prendre au sérieux. La recherche web est désactivée par défaut pour le
  chemin débat (3.1) même si la config fournie l'active. Mesure la latence
  bout-en-bout (`meets_latency_threshold`, seuil proposé dans `DECISION.md`,
  non validé).
- **Flux C ci-dessous** — le même pattern de débat, mais natif à Claude Code
  (Phase 1), pour les décisions d'architecture prises *dans* ce projet.
  Mêmes schémas de données (`Claim`/`Evidence`, même format JSON), mêmes
  invariants, orchestré directement par l'assistant plutôt que par
  `proto/pipeline.py`.

## Invariants (toutes phases, v3+v4 — ne jamais déroger sans validation utilisateur)

- 2 débatteurs + 1 juge maximum, jamais de débat symétrique à N agents.
- 2 tours maximum ; arrêt anticipé conditionné aux **citations concordantes**
  (pas au simple accord).
- Aucun débat sans fiche de faits sourcée ; mémoire paramétrique disqualifiée
  pour tout claim postérieur au cutoff du modèle.
- Juge en double passage à ordre inversé ; divergence → « indécidable ».
- Débats stateless sur le contenu (aucun verdict précédent dans le contexte).
- La détection de conflits reste **mécanique, non-LLM**, y compris dans Flux
  C (voir `proto/judge_bridge.py` ci-dessous).

## Flux C — débat d'architecture (Phase 1)

**Déclencheur :** l'utilisateur écrit `débat : [question d'architecture]`.

Cette section décrit comment *toi* (l'assistant Claude Code exécutant cette
session) orchestres le débat — les trois rôles (`debate-advocate`,
`debate-challenger`, `debate-judge` dans `.claude/agents/`) ne voient chacun
que ce qui leur est explicitement transmis ci-dessous.

1. **Formulation de la question.** Si des contraintes non négociables du
   projet déterminent probablement la réponse à elles seules, teste
   **séparément avec et sans** ces contraintes auto-injectées (deux runs
   complets, correction F9) — sinon un seul run suffit. Ceci est surtout
   critique pour le protocole d'évaluation (1.3) sur `datasets/archi/`, mais
   s'applique par défaut à tout déclenchement de Flux C.
2. **Brainstorming** (v4, nouveau) — avant d'invoquer les débatteurs,
   énumère toi-même brièvement les options/angles pertinents à partir des
   évidences disponibles. Non contraignant : alimente les positions
   initiales sans les figer.
3. **Rassembler les évidences, par ID.** Cherche (code du projet, docs
   officielles des technologies en jeu, benchmarks) et numérote chaque
   évidence (`e1`, `e2`, ...). Partitionne-les en deux jeux **asymétriques**
   (Axe 3.2 de l'audit) :
   - `debate-advocate` reçoit un sous-ensemble **favorable** à la solution
     proposée.
   - `debate-challenger` reçoit **l'ensemble complet**, y compris les
     évidences contradictoires ou défavorables.
4. **Tour 1 — parallèle, sans visibilité mutuelle.** Invoque
   `debate-advocate` et `debate-challenger` (Agent tool, en parallèle dans
   le même message) avec la question + leur jeu d'évidences respectif.
   Chacun répond en JSON structuré (schéma `Claim`, voir les fichiers
   agents).
5. **Résumé structuré inter-tours** (correction F5) — condense chaque
   position en 1 ligne + 3 arguments max (1 ligne chacun, IDs cités).
   Jamais la prose complète d'un côté transmise à l'autre.
6. **Arrêt anticipé ?** Si les deux positions du tour 1 convergent **avec
   citations concordantes** (mêmes IDs d'évidence soutenant la même
   conclusion), passe directement à l'étape 8. Sinon, tour 2 obligatoire.
7. **Tour 2 — réfutation.** Chaque débatteur reçoit uniquement le résumé
   structuré de l'autre (étape 5) et produit sa réfutation finale en JSON
   (même schéma, `rebuts` renseigné avec les IDs de claims contrés).
8. **Argument graph** (v4, nouveau, mécanique) — rassemble les évidences et
   tous les claims (tour 1 + tour 2 des deux côtés) dans deux fichiers JSON
   temporaires (`{"evidence": [...]}`, `{"claims": [...]}`), puis invoque :

   ```bash
   python -m proto.judge_bridge --evidence <evidence.json> --claims <claims.json>
   ```

   Ce script construit le graphe et détecte les conflits **sans LLM** (arêtes
   `attack`/`support` dérivées mécaniquement des citations par ID), calcule
   `C(a_i)` par claim et `S(o)` (signal de consensus). Ne reconstruis jamais
   ce graphe "à la main" par raisonnement — c'est exactement l'invariant que
   ce script préserve.
9. **Synthèse — juge en double passage.** Invoque `debate-judge` deux fois :
   une fois avec les claims dans l'ordre advocate-puis-challenger, une fois
   challenger-puis-advocate (même contenu, ordre inversé — correction F6).
   Fournis-lui dans les deux cas la question, les claims dans l'ordre voulu,
   et le rapport JSON de l'étape 8 (graphe + `C(a_i)` + `S(o)`/`theta`) comme
   signaux — jamais comme un remplacement de son verdict.
10. **Verdict final.** Si les deux passages du juge sont d'accord, c'est le
    verdict. **S'ils divergent, force le verdict à
    `"indécidable — information manquante"`**, quel que soit le contenu de
    chaque passage individuel.
11. **Fiche de décision** — assemble : question, options considérées
    (issues du brainstorming), arguments retenus/rejetés (par ID de claim),
    décision, conditions de réversibilité, sources par ID, niveau de
    confiance. Référence les IDs du graphe plutôt que de reformuler les
    arguments en prose.

### Protocole d'évaluation (1.3, v3+v4) — pas encore exécutable

Nécessite du contenu réel dans `datasets/archi/` (double variante
avec/sans contraintes non négociables, cf. `plan-implantation-debat-multi-agent.md`
0.3) — **actuellement vide**, en attente de fourniture. Une fois rempli,
chaque item doit passer par : (a) agent unique, (b) self-consistency à
budget compute égal (`proto/baseline.py`), (c) Flux C complet, (d) Flux C
« nu » sans brainstorming/argument-graph (mesure ce que ces deux ajouts v4
apportent réellement, à budget compté). Comparaison → tableau → seuils
proposés dans `DECISION.md` → validation utilisateur → go/no-go.

## Phase 4 — Consolidation

`proto/pattern_report.py` (4.2) génère `results/pattern_report.json` :
traçabilité des patterns implémentés (corrections F1-F9/Axe 2.4, fichiers
source) + dérive des trust_weights (`TrustWeightStore.get_history()`).
**Tous les patterns sont marqués `en_attente`** — aucun n'a encore été
« retenu » ou « rejeté » par une vraie mesure (1.3/2.2-2.3/3.3-3.4 n'ont pas
tourné sur données réelles). Ne pas changer un statut sans un vrai
go/no-go.

4.1 (extraction `proto/` → `jarvis-test` → `jarvis`) est **en attente** :
`jarvis-test` (sibling repo, `c:\dev\jarvis-test`) sert actuellement à un
autre sous-système (avatar/skills, branche `avatar/skills/svg-generator`)
avec des suppressions non commitées en cours — ne rien y écrire tant que ce
n'est pas nettoyé/commité.

## Tests

`python -m unittest discover -s tests -v` (stdlib `unittest`, aucune
dépendance pytest requise).

Pour un résumé exploitable après coup : `python run_tests.py` — journalise
chaque test terminé en DEBUG (`logs/test_run_<timestamp>.log`) et écrit un
résumé JSON (`logs/test_results_<timestamp>.json` : totaux, et par test
`test`/`outcome`/`duration_s`/`detail` si échec). `logs/` est gitignored
(artefacts de run, pas des livrables versionnés).
