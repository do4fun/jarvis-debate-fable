import tempfile
import unittest
from pathlib import Path

from proto.checkpoint import CheckpointStore


class TestCheckpointStore(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.store = CheckpointStore(sessions_dir=Path(self.tmpdir.name))

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_load_returns_none_when_absent(self):
        self.assertIsNone(self.store.load("missing-session"))

    def test_save_then_load_round_trips_state(self):
        self.store.save("s1", "thesis", {"thesis": {"claims": ["a"]}})
        loaded = self.store.load("s1")
        self.assertEqual(loaded.session_id, "s1")
        self.assertEqual(loaded.step, "thesis")
        self.assertEqual(loaded.state, {"thesis": {"claims": ["a"]}})

    def test_exists(self):
        self.assertFalse(self.store.exists("s1"))
        self.store.save("s1", "thesis", {})
        self.assertTrue(self.store.exists("s1"))

    def test_clear_removes_checkpoint(self):
        self.store.save("s1", "thesis", {})
        self.store.clear("s1")
        self.assertFalse(self.store.exists("s1"))
        self.assertIsNone(self.store.load("s1"))

    def test_clear_on_missing_session_is_a_noop(self):
        self.store.clear("never-existed")  # must not raise

    def test_later_save_overwrites_state_for_same_session(self):
        self.store.save("s1", "thesis", {"thesis": {}})
        self.store.save("s1", "antithesis", {"thesis": {}, "antithesis": {}})
        loaded = self.store.load("s1")
        self.assertEqual(loaded.step, "antithesis")
        self.assertEqual(set(loaded.state.keys()), {"thesis", "antithesis"})

    def test_sessions_are_independent(self):
        self.store.save("s1", "thesis", {"thesis": {"who": "s1"}})
        self.store.save("s2", "thesis", {"thesis": {"who": "s2"}})
        self.assertEqual(self.store.load("s1").state["thesis"]["who"], "s1")
        self.assertEqual(self.store.load("s2").state["thesis"]["who"], "s2")

    def test_no_leftover_tmp_file_after_save(self):
        self.store.save("s1", "thesis", {})
        tmp_files = list(Path(self.tmpdir.name).glob("*.tmp"))
        self.assertEqual(tmp_files, [])


if __name__ == "__main__":
    unittest.main()
