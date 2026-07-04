# Audit du plan d'implantation MAD v2 — failles et optimisations

**Rôle :** architecte logiciel principal / expert optimisation prompts & LLM
**Objet :** `docs/plan-implantation.md` (v2, repo `jarvis-debate-fable`)
**Référence principale :** Du et al. 2023 (arXiv:2305.14325), texte intégral fourni
**Périmètre :** analyse et optimisation uniquement — aucun code, aucune implémentation
**Filtres appliqués :** 100 % gratuit, 100 % local, laptop CPU/iGPU 8-16 Go RAM, zéro lock-in, français intégral

---

## Axe 1 — Failles du plan actuel

### F1 · Circularité épistémique (faille la plus grave) — risque d'hallucination structurel

La Phase 2 fait débattre deux modèles sur la véracité de claims **sans leur fournir de sources**. Or Du et al. le montrent explicitement (leur Figure 8) : sur les faits incertains, le débat force les agents à converger vers un fait unique **« which is not necessarily correct »**. Le débat mesure la cohérence interne des modèles, pas la factualité du monde. Deux Qwen 3-4B qui s'accordent sur un claim faux produiront un consensus faux avec un score de confiance élevé — c'est pire qu'un modèle seul, car le verdict paraît validé.

**Conséquence :** tel quel, le vérificateur MAD-Fact de la Phase 2 est un détecteur de plausibilité, pas un vérificateur de faits. Pour un pipeline anti-hallucination, c'est une inversion de l'objectif.

**Correction :** le débat doit porter sur *« l'évidence fournie soutient-elle le claim ? »*, jamais sur *« le claim est-il vrai ? »*. Chaque claim entre dans le débat accompagné d'extraits sources ; sans évidence, le verdict est automatiquement « invérifiable » sans dépenser un seul tour de débat. (Détail Axe 2.)

### F2 · Cutoff des modèles vs fraîcheur du corpus — données obsolètes, faux négatifs systématiques

Ton corpus catalogue des ressources 2025-2026. Les modèles locaux ont un cutoff antérieur. Un claim exact mais postérieur au cutoff (« MeloTTS v2 supporte X ») sera systématiquement contesté par le sceptique « de mémoire » — le plan produira des **faux négatifs corrélés à la fraîcheur**, c'est-à-dire exactement sur les données qui ont le plus de valeur dans une veille. Le plan ne distingue nulle part « contredit par une source » et « inconnu du modèle ».

**Correction :** métadonnée de date obligatoire par claim ; tout claim postérieur au cutoff du modèle est routé « vérifiable par source uniquement » — le verdict ne peut alors s'appuyer que sur l'évidence, la mémoire paramétrique des débatteurs étant explicitement disqualifiée dans le prompt.

### F3 · L'arrêt anticipé récompense la sycophancie — convergence ≠ correction

Du et al. constatent que les agents sont « relatively agreeable » (effet RLHF) et que les prompts induisant une convergence *lente* donnent un **meilleur** consensus final (leur Figure 10 : long debate prompt > short). Ton invariant « arrêt anticipé si convergence au tour 1 » optimise l'inverse : il économise des tokens précisément dans les cas où l'accord rapide est le plus suspect. Sur des petits modèles instruction-tunés, l'accord au tour 1 est souvent de la complaisance, pas de la vérification.

**Correction :** l'arrêt anticipé ne doit pas se déclencher sur le simple accord des positions, mais sur l'accord **assorti d'évidences citées concordantes**. Accord sans citations = tour 2 obligatoire avec un prompt anti-complaisance pour le challenger (« ton rôle échoue si tu acceptes sans citation »).

### F4 · Gouffre à tokens non chiffré — explosion combinatoire de la Phase 2

Le plan empile : traduction FR→EN (+1 appel) × décomposition en claims (+1 appel) × débat par claim (3 appels minimum : 2 débatteurs + juge) × N claims par chunk × ~300 ressources. À ~5 claims/chunk, on dépasse **~4 500 appels modèle** pour un passage complet du corpus, sur CPU. Aucun plafond de budget par chunk n'est fixé, aucune extrapolation de coût total n'est exigée avant le go/no-go — le seuil « Budget maximal » de DECISION.md compare débat/baseline par item, mais ne borne pas le coût du corpus entier.

**Corrections :**

- Trier avant de débattre : un filtre à un appel (le juge seul, avec évidence) traite les cas triviaux ; le débat n'est déclenché que sur les claims où le juge seul est incertain (score de confiance sous un seuil). C'est le même esprit que SID/arrêt adaptatif, appliqué *en amont*.
- Plafond dur de tokens par claim et par chunk, imposé par le harnais, mesuré dès le premier run.
- La traduction FR→EN se fait **une fois par chunk**, pas par claim ni par tour.

### F5 · Saturation du contexte inter-tours — la concaténation est une dette

Du et al. signalent en limites que « as debates got longer, current language models struggled to fully process the context », et démontrent que **résumer les réponses adverses améliore la performance** tout en réduisant le contexte (leur Figure 11). Ton Flux C (Phase 1) et le débat local (Phase 2) transmettent les positions adverses complètes. Sur un 3-4B avec KV cache en RAM partagée, c'est doublement pénalisant : qualité et mémoire.

**Correction :** structurer l'échange inter-tours (voir Axe 3) — jamais de concaténation brute.

### F6 · Juge unique, ordre fixe — biais de position non traité

La littérature LLM-as-judge (ChatEval, PRD, déjà dans ta base documentaire) documente le biais de position : le juge favorise la première ou la dernière position présentée. Le plan ne randomise pas l'ordre advocate/challenger et ne fait passer le juge qu'une fois.

**Correction :** deux passages du juge avec ordres inversés ; si les verdicts divergent → « indécidable » ou escalade humaine. Coût : +1 appel, uniquement sur les claims déjà filtrés (F4), donc marginal.

### F7 · Baselines à budget inégal — le protocole d'évaluation favorise le débat

Du et al. comparent le débat (3 agents × 2 tours = ~9 appels) à un agent unique (1 appel) : le gain observé mélange l'effet « débat » et l'effet « plus de compute ». La critique « Stop Overvaluing MAD » (déjà dans ta base) repose exactement là-dessus. Ton plan hérite du biais : la baseline « CoT + Self-Consistency » n'est pas spécifiée en nombre d'échantillons.

**Correction :** baseline à **budget compute égal** — si le débat consomme ~6 appels/claim, la self-consistency a droit à 6 échantillons + vote majoritaire. C'est le seul comparatif honnête, et Du et al. eux-mêmes montrent (Table 1) que Multiagent-Majority capture une partie du gain sans aucun débat.

### F8 · La traduction FR→EN est un maillon non mesuré isolément

L'étape 0.4 est mesurée « coût vs gain global », mais jamais comme source d'erreur propre : une distorsion de claim à la traduction (nuance de licence, périmètre d'une métrique) corrompt tout l'aval, et l'erreur sera imputée au débat. Par ailleurs le traducteur est le même modèle 3-4B — le maillon le plus faible traduit pour les autres.

**Correction :** test de fidélité aller-retour (FR→EN→FR, comparaison des claims) sur le jeu de test, mesuré séparément en Phase 0 ; les claims techniques sensibles (noms, versions, licences, chiffres) sont **extraits avant traduction et réinjectés verbatim** — on ne traduit que le tissu conjonctif.

### F9 · Contamination du jeu de test Phase 1

Les items `datasets/archi/` sont tes décisions passées, et le Flux C injecte automatiquement tes « contraintes non négociables » dans le contexte. Or ces contraintes *encodent la réponse* (MeloTTS vs Piper se déduit de « licence MIT exigée »). Le test mesurera la capacité des agents à appliquer un filtre, pas à débattre — résultat non discriminant, go/no-go non informatif.

**Correction :** deux variantes par item — avec et sans les contraintes qui déterminent la réponse — plus quelques items dont la bonne réponse *contredit* une intuition de surface (pièges). C'est l'écart entre les deux variantes qui mesure la valeur ajoutée réelle du débat.

---

## Axe 2 — Stratégie d'optimisation de la recherche

### 2.1 Tavily / Perplexity : disqualifiés par tes contraintes — alternatives conformes

Tavily et Perplexity sont des API cloud (clé, quota, données sortantes) : triple violation (local, gratuit, lock-in). Équivalents conformes :

| Besoin | Solution conforme | Statut licence |
|---|---|---|
| Métamoteur de recherche | **SearXNG auto-hébergé** (agrège les moteurs publics, API JSON locale) | AGPL, gratuit |
| Extraction de contenu propre | **trafilatura** (HTML → texte + métadonnées : date, auteur, langue) | Apache 2.0 |
| Archivage des sources | Capture locale au moment de l'extraction (HTML + hash + horodatage) | — |

Nuance honnête : SearXNG interroge des moteurs *publics* — le trafic sort de la machine. Si « 100 % local » signifie « zéro trafic sortant », alors la recherche vit dans une **phase d'acquisition** distincte et assumée (déjà le cas : tes inventaires sont constitués via recherche), et le débat, lui, tourne 100 % hors ligne sur le corpus archivé. Cette séparation acquisition/vérification est de toute façon la bonne architecture (F1).

### 2.2 Le principe directeur : « debate on evidence, not on memory »

Réorganisation du flux Phase 2 :

1. **Acquisition** (une fois) : chaque ressource de l'inventaire est archivée localement — page source, date de capture, hash.
2. **Chunking sémantique** : découpage aligné sur les unités de sens (une section, une clause de licence, un tableau de specs), cible 200-400 tokens, overlap minimal. Pas de chunking arbitraire à taille fixe : un claim coupé en deux est invérifiable.
3. **Extraction de métadonnées** par chunk : URL source, date de publication, date de capture, licence du contenu, domaine, langue d'origine (ton exigence de couverture non anglo-centrée devient ici un champ filtrable).
4. **Appariement claim ↔ évidence** : pour chaque claim atomique, retrieval dans le corpus local (BM25 suffit au départ — gratuit, CPU, zéro dépendance lourde ; les embeddings viendront si BM25 plafonne, mesuré, pas supposé).
5. **Débat** : uniquement sur « cette évidence soutient-elle ce claim ? », avec les garde-fous F3/F4/F6.

### 2.3 Filtrage par domaine de confiance — pondération, pas censure

Trois niveaux, cohérents avec ta pratique existante des sources primaires :

- **N1 primaire** : arXiv/DOI, dépôt officiel du projet, documentation éditeur, registre de licence (SPDX).
- **N2 secondaire** : blogs de recherche des équipes, actes de conférences.
- **N3 tertiaire** : agrégateurs, presse tech, forums.

Le niveau est une **métadonnée transmise au juge**, qui pondère : un claim soutenu uniquement par du N3 ne peut pas obtenir le label « soutenu » plein — au mieux « soutenu (faible) ». On ne supprime pas le N3 (il capte la fraîcheur), on l'empêche de conclure seul.

### 2.4 Obsolescence : la détecter, pas la subir

- Chaque verdict est horodaté et lié au hash de l'évidence → si un re-crawl ultérieur change le hash, le verdict est automatiquement invalidé et le claim repasse en file de vérification. L'obsolescence devient un événement détectable, pas une dérive silencieuse.
- Champ `deprecated` de tes inventaires alimenté par cette mécanique (cas Ready Player Me : le re-crawl aurait détecté la page d'annonce de fermeture).

---

## Axe 3 — Gestion du contexte des agents

### 3.1 La fiche de faits comme contrat de données (ton pattern « fiche avatar », appliqué au débat)

Les agents ne reçoivent jamais de texte source brut. Ils reçoivent une **fiche de faits** compacte : claims numérotés (`C1`, `C2`…), évidences numérotées (`E1`, `E2`…) avec extrait court + métadonnées (niveau de confiance N1-N3, date, source), et la question du débat. Les agents **citent par identifiant** (`C1 soutenu par E2`) — jamais de recopie d'évidence dans leurs réponses. Gain triple : contexte court, réponses vérifiables mécaniquement (le harnais contrôle que chaque verdict cite au moins un E), et logs compacts.

### 3.2 Distribution asymétrique de l'information

- **Advocate** : le claim + les évidences qui le soutiennent potentiellement.
- **Challenger** : le claim + *toutes* les évidences (y compris contradictoires) + les métadonnées de fraîcheur/niveau — c'est lui qui a besoin du panorama pour attaquer.
- **Juge** : les deux positions structurées + les identifiants cités ; il peut demander le texte d'une évidence précise (chargement à la demande), il ne reçoit jamais tout le dossier d'office.

L'asymétrie n'est pas un biais : elle reproduit la charge de la preuve et évite de payer trois fois le même contexte.

### 3.3 Résumé structuré entre tours — jamais de concaténation

Application directe de la Figure 11 de Du et al. (le résumé *améliore* la performance en plus de réduire le contexte). Entre le tour 1 et le tour 2, chaque agent reçoit de son adversaire un **résumé structuré à format imposé** : position (1 ligne), arguments (3 max, 1 ligne chacun), évidences citées (IDs). Le harnais tronque tout dépassement. Le tour 2 débat sur ce résumé, pas sur la prose complète.

### 3.4 Budget contexte chiffré et imposé par le harnais

Sur un 3-4B quantifié en RAM partagée, la fenêtre théorique est hors de portée pratique (KV cache). Plafonds à inscrire dans le harnais dès la Phase 0, mesurés puis ajustés : ~2k tokens de contexte utile par appel de débatteur, ~3k pour le juge (il voit deux positions). Tout ce que l'architecture des fiches (3.1-3.3) ne fait pas tenir dans ce budget est un défaut de conception à corriger en amont, pas à absorber en gonflant le contexte.

### 3.5 Débats stateless — pas de mémoire inter-claims

Chaque débat de claim démarre à contexte vierge. Aucun verdict précédent n'est transmis au suivant : c'est la parade à la propagation de « mémoires erronées » entre débats (le problème que MAD-M² corrige a posteriori — autant ne pas le créer). La continuité vit dans les logs et l'agrégation par chunk, pas dans le contexte des agents.

---

## Synthèse — modifications à apporter au plan v2

| # | Modification | Phase touchée | Origine |
|---|---|---|---|
| 1 | Nouveau 0.6 : acquisition + archivage local des sources, chunking sémantique, métadonnées, appariement claim↔évidence (BM25) | Phase 0 | F1, F2, Axe 2 |
| 2 | Reformuler 2.1 : le débat porte sur « évidence ⊨ claim », mémoire paramétrique disqualifiée pour les claims post-cutoff | Phase 2 | F1, F2 |
| 3 | Filtre pré-débat à 1 appel ; débat réservé aux claims incertains ; plafonds de tokens par claim/chunk ; traduction 1×/chunk | Phase 2 | F4 |
| 4 | Arrêt anticipé conditionné aux citations concordantes, pas au simple accord ; prompt anti-complaisance du challenger | Invariants | F3 |
| 5 | Juge : double passage à ordre inversé, divergence → indécidable | Phases 1-2 | F6 |
| 6 | Baseline self-consistency à budget compute égal, spécifiée dans DECISION.md | Phase 0 | F7 |
| 7 | Test de fidélité aller-retour de la traduction + extraction verbatim des tokens sensibles (noms, versions, licences, chiffres) | Phase 0 | F8 |
| 8 | Jeu archi en double variante (avec/sans contraintes déterminantes) + items pièges | Phase 0/1 | F9 |
| 9 | Échanges inter-tours en résumé structuré à format imposé ; fiches de faits avec citation par ID ; débats stateless | Phases 1-2-3 | F5, Axe 3 |
| 10 | Mécanique d'invalidation par hash (re-crawl → verdicts périmés en file de re-vérification) | Phase 2/4 | Axe 2.4 |

Aucune de ces modifications n'est appliquée au plan sans ton accord — dis-moi lesquelles tu valides (toutes, une sélection, ou discussion point par point), et je produis le plan v3 en conséquence.
