# Décisions go/no-go

Gabarit des seuils (plan d'implantation, section 0.2). Pour chaque phase : seuils **proposés** après les premiers runs du prototype, puis **validés explicitement par l'utilisateur** avant le passage à la phase suivante. Aucun seuil n'est auto-appliqué.

## Phase 0 — Mise en place

- **Fidélité traduction (nouveau v3)** : taux d'accord sur le test aller-retour FR→EN→FR (`datasets/facts/`), en dessous duquel l'étape 0.4 est bloquante.
  - Proposé : _à définir après premiers runs_
  - Validé par l'utilisateur : _en attente_

## Phase 1 — Débat d'architecture

- **Gain minimal** débat vs baseline à budget compute égal (correction F7).
  - Proposé : _à définir_
  - Validé : _en attente_

## Phase 2 — Vérification factuelle RAG (MAD-Fact)

- **Budget maximal absolu** : plafond tokens/temps CPU par claim, et extrapolation chiffrée au corpus entier (~300+ ressources, correction F4).
  - Proposé : _à définir_
  - Validé : _en attente_
- **Fiabilité** : taux maximal d'échecs MAST-(iii).
  - Proposé : _à définir_
  - Validé : _en attente_

## Phase 3 — Raisonnement du Jarvis local

- **Latence bout-en-bout** (traduction + filtre pré-débat + débat).
  - Proposé : _à définir_
  - Validé : _en attente_

---

## Points ouverts non liés à un seuil chiffré

Voir plan-implantation.md § « Points encore ouverts » — notamment la confirmation que SearXNG auto-hébergé est acceptable pour l'acquisition (seul maillon non 100 % local, isolé du débat lui-même).
