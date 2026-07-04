# DECISION.md — Seuils go/no-go et paramètres validés

Gabarit v4 (0.2). Chaque valeur est **proposée** par le prototype après les premiers runs, puis
**validée explicitement par l'utilisateur** avant d'être considérée actée. Tant qu'une ligne porte
`(proposé — non validé)`, le prototype ne doit pas en dépendre pour bloquer une décision go/no-go.

## Seuils généraux (hérités v2/v3)

| Paramètre | Valeur | Statut |
|---|---|---|
| Gain minimal débat vs baseline (budget compute égal) | — | à proposer après premiers runs Phase 1 |
| Budget maximal absolu (tokens/temps CPU par claim) | — | à proposer après premiers runs Phase 2 |
| Extrapolation coût total corpus (~300+ ressources) | — | à proposer après premiers runs Phase 2 |
| Fiabilité — taux max d'échecs MAST-(iii) | — | à proposer |
| Fidélité traduction FR→EN→FR (taux d'accord) | — | à mesurer Phase 0 (0.4) |

## Paramètres v4 (nouveaux)

| Paramètre | Valeur par défaut | Statut |
|---|---|---|
| θ — seuil d'acceptation du consensus S(o) | `0.6` | (proposé — non validé, point ouvert n°6/9 de `plan-implantation-debat-multi-agent-v4.md`) |
| N1 — poids de crédibilité (source primaire) | `1.0` | (proposé — non validé, point ouvert n°9) |
| N2 — poids de crédibilité (source secondaire) | `0.6` | (proposé — non validé, point ouvert n°9) |
| N3 — poids de crédibilité (source tertiaire) | `0.3` | (proposé — non validé, point ouvert n°9) |
| Décroissance de fraîcheur — demi-vie | `730 jours` (~2 ans) | (proposé — non validé, point ouvert n°9) |
| trust_weight — valeur initiale (neutre) | `0.5` | (proposé — non validé, point ouvert n°9) |
| trust_weight — α (EMA) | `0.1` | (proposé — non validé, point ouvert n°9) |
| Répertoire des logs de session | `results/sessions/` | (choix par défaut retenu — le v4 proposait aussi `rapports/sessions/`, à confirmer) |
| `docs/PLAN_recherche_web.md` | rédigé par le prototype | voir ce fichier — à relire/valider |
| Référence « Yin 2025 » (§3.3.4, base de S(o)) | non retrouvée | **point ouvert — non bloquant** : la formule S(o) = Σ trust_weight_i·v_i(o) est implémentée indépendamment de la citation ; ajouter la référence à `docs/references-mad.md` dès qu'elle est fournie |

## Phase 3 (nouveau)

| Paramètre | Valeur par défaut | Statut |
|---|---|---|
| Seuil de latence bout-en-bout (`proto/jarvis_loop.py`) | `5.0 s` | (proposé — non validé, 3.3 : « seuil proposé puis validé utilisateur ») — à mesurer sur de vrais runs Ollama, pas encore fait |
| Critères du routeur débat/réponse directe (3.2) | — | **décision actée, inchangée depuis v2/v3 : « définis plus tard »** — `proto/jarvis_loop.py::default_router` répond toujours par une réponse directe (aucun débat) tant qu'aucun critère n'est fourni ; ne pas confondre ce défaut avec une heuristique réfléchie |
| Config Phase 3 = « config gagnante » de la Phase 2 (3.1) | — | aucune config n'a encore « gagné » : Phase 2 n'a pas été mesurée sur données réelles (`datasets/facts/` vide) |

## Notes d'implémentation

- Les valeurs ci-dessus sont des **constantes par défaut** dans `proto/scoring.py`, jamais codées en dur ailleurs — un seul point de mise à jour une fois validées.
- Le juge (étape [7]) ne dépend jamais de S(o)/C(a_i) comme verdict automatique — ce sont des signaux d'entrée, jamais un remplacement (invariant v4 conservé).
- **Déviation assumée** : `consensus_score` (`proto/scoring.py`) normalise par la somme des trust_weight (S(o) = Σ trust_weight_i·v_i(o) / Σ trust_weight_i), alors que la formule du plan v4 (§3.3.4) n'a pas de terme de normalisation. Choix délibéré pour garder S(o) comparable à θ quel que soit le nombre d'agents ou l'échelle des poids — signalé ici pour qu'un futur lecteur ne le prenne pas pour une erreur de transcription.
