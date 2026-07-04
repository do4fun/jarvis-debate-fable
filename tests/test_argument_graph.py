import unittest
from datetime import date

from proto.argument_graph import ArgumentGraph, Claim, Evidence, EvidenceLevel, RelationType, Stance


def make_evidence(eid: str, level: EvidenceLevel = EvidenceLevel.N1) -> Evidence:
    return Evidence(id=eid, source_url=f"https://example.org/{eid}", level=level, excerpt="excerpt",
                     published_date=date(2024, 1, 1), captured_date=date(2024, 1, 2), content_hash="deadbeef")


class TestArgumentGraphBasics(unittest.TestCase):
    def test_add_and_retrieve_claim_and_evidence(self):
        graph = ArgumentGraph()
        ev = make_evidence("e1")
        graph.add_evidence(ev)
        claim = Claim(id="c1", author_role="advocate", text="X is true", stance=Stance.SUPPORT,
                       cited_evidence_ids=("e1",))
        graph.add_claim(claim)

        self.assertEqual(graph.claim("c1"), claim)
        self.assertEqual(graph.evidence_for("c1"), (ev,))
        self.assertEqual(len(graph.claims), 1)
        self.assertEqual(len(graph.evidence), 1)

    def test_duplicate_claim_id_rejected(self):
        graph = ArgumentGraph()
        claim = Claim(id="c1", author_role="advocate", text="X", stance=Stance.SUPPORT)
        graph.add_claim(claim)
        with self.assertRaises(ValueError):
            graph.add_claim(claim)

    def test_duplicate_evidence_id_rejected(self):
        graph = ArgumentGraph()
        ev = make_evidence("e1")
        graph.add_evidence(ev)
        with self.assertRaises(ValueError):
            graph.add_evidence(ev)


class TestConflictDetection(unittest.TestCase):
    def test_explicit_rebuttal_creates_attack_edge(self):
        graph = ArgumentGraph()
        c1 = Claim(id="advocate-1", author_role="advocate", text="A", stance=Stance.SUPPORT)
        c2 = Claim(id="challenger-1", author_role="challenger", text="not A", stance=Stance.ATTACK,
                   rebuts=("advocate-1",))
        graph.add_claim(c1)
        graph.add_claim(c2)

        conflicts = graph.detect_conflicts()

        self.assertEqual(len(conflicts), 1)
        relation = conflicts[0]
        self.assertEqual(relation.type, RelationType.ATTACK)
        self.assertEqual(relation.source_claim_id, "challenger-1")
        self.assertEqual(relation.target_claim_id, "advocate-1")
        self.assertEqual(relation.reason, "explicit_rebuttal")

    def test_shared_evidence_opposing_stance_creates_attack_edge(self):
        graph = ArgumentGraph()
        graph.add_evidence(make_evidence("e1"))
        c1 = Claim(id="advocate-1", author_role="advocate", text="A supports X", stance=Stance.SUPPORT,
                   cited_evidence_ids=("e1",))
        c2 = Claim(id="challenger-1", author_role="challenger", text="A undermines X", stance=Stance.ATTACK,
                   cited_evidence_ids=("e1",))
        graph.add_claim(c1)
        graph.add_claim(c2)

        conflicts = graph.detect_conflicts()

        self.assertEqual(len(conflicts), 1)
        self.assertEqual(conflicts[0].reason, "shared_evidence_opposing_stance")

    def test_same_role_sharing_evidence_is_not_a_conflict(self):
        graph = ArgumentGraph()
        graph.add_evidence(make_evidence("e1"))
        c1 = Claim(id="advocate-1", author_role="advocate", text="A", stance=Stance.SUPPORT,
                   cited_evidence_ids=("e1",))
        c2 = Claim(id="advocate-2", author_role="advocate", text="B", stance=Stance.ATTACK,
                   cited_evidence_ids=("e1",))
        graph.add_claim(c1)
        graph.add_claim(c2)

        self.assertEqual(graph.detect_conflicts(), [])

    def test_shared_evidence_same_stance_is_not_a_conflict(self):
        graph = ArgumentGraph()
        graph.add_evidence(make_evidence("e1"))
        c1 = Claim(id="advocate-1", author_role="advocate", text="A", stance=Stance.SUPPORT,
                   cited_evidence_ids=("e1",))
        c2 = Claim(id="challenger-1", author_role="challenger", text="B", stance=Stance.SUPPORT,
                   cited_evidence_ids=("e1",))
        graph.add_claim(c1)
        graph.add_claim(c2)

        self.assertEqual(graph.detect_conflicts(), [])

    def test_detect_conflicts_is_idempotent(self):
        graph = ArgumentGraph()
        c1 = Claim(id="advocate-1", author_role="advocate", text="A", stance=Stance.SUPPORT)
        c2 = Claim(id="challenger-1", author_role="challenger", text="not A", stance=Stance.ATTACK,
                   rebuts=("advocate-1",))
        graph.add_claim(c1)
        graph.add_claim(c2)

        first = graph.detect_conflicts()
        second = graph.detect_conflicts()

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])  # no new relations on a second call
        self.assertEqual(len(graph.relations), 1)


class TestSerialization(unittest.TestCase):
    def test_claim_round_trip(self):
        claim = Claim(id="c1", author_role="advocate", text="X", stance=Stance.SUPPORT,
                       cited_evidence_ids=("e1", "e2"), rebuts=("c0",))
        restored = Claim.from_dict(claim.to_dict())
        self.assertEqual(claim, restored)

    def test_evidence_round_trip_with_dates(self):
        ev = make_evidence("e1")
        restored = Evidence.from_dict(ev.to_dict())
        self.assertEqual(ev, restored)

    def test_evidence_round_trip_without_dates(self):
        ev = Evidence(id="e1", source_url="https://example.org", level=EvidenceLevel.N3, excerpt="x")
        restored = Evidence.from_dict(ev.to_dict())
        self.assertEqual(ev, restored)

    def test_graph_to_dict_is_json_serializable(self):
        import json
        graph = ArgumentGraph()
        graph.add_evidence(make_evidence("e1"))
        graph.add_claim(Claim(id="c1", author_role="advocate", text="X", stance=Stance.SUPPORT,
                               cited_evidence_ids=("e1",)))
        json.dumps(graph.to_dict())  # must not raise


if __name__ == "__main__":
    unittest.main()
