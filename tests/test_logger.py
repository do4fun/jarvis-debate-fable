import json
import tempfile
import unittest
from pathlib import Path

from proto.logger import SessionLogger
from proto.paths import UnsafeIdentifierError


class TestSessionLogger(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.sessions_dir = Path(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_log_step_accumulates_steps_with_timestamp(self):
        logger = SessionLogger(session_id="s1", sessions_dir=self.sessions_dir)
        logger.log_step("thesis", claims=["a"])
        self.assertEqual(len(logger.steps), 1)
        self.assertEqual(logger.steps[0]["step"], "thesis")
        self.assertEqual(logger.steps[0]["claims"], ["a"])
        self.assertIn("logged_at", logger.steps[0])

    def test_write_creates_file_named_after_session_id(self):
        logger = SessionLogger(session_id="my-session", sessions_dir=self.sessions_dir)
        logger.log_step("thesis")
        path = logger.write()
        self.assertEqual(path.name, "my-session_full.json")
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["session_id"], "my-session")
        self.assertEqual(len(data["steps"]), 1)

    def test_write_creates_sessions_dir_if_missing(self):
        nested = self.sessions_dir / "nested"
        logger = SessionLogger(session_id="s1", sessions_dir=nested)
        logger.write()
        self.assertTrue(nested.exists())

    def test_rejects_path_traversal_session_id(self):
        logger = SessionLogger(session_id="../escape", sessions_dir=self.sessions_dir)
        with self.assertRaises(UnsafeIdentifierError):
            logger.write()


if __name__ == "__main__":
    unittest.main()
