import unittest

from proto.paths import UnsafeIdentifierError, safe_id


class TestSafeId(unittest.TestCase):
    def test_alphanumeric_id_passes_through(self):
        self.assertEqual(safe_id("session-123_abc.v2"), "session-123_abc.v2")

    def test_uuid_passes_through(self):
        uid = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
        self.assertEqual(safe_id(uid), uid)

    def test_rejects_forward_slash(self):
        with self.assertRaises(UnsafeIdentifierError):
            safe_id("../evil")

    def test_rejects_backslash(self):
        with self.assertRaises(UnsafeIdentifierError):
            safe_id("..\\evil")

    def test_rejects_bare_dotdot(self):
        with self.assertRaises(UnsafeIdentifierError):
            safe_id("..")

    def test_rejects_bare_dot(self):
        with self.assertRaises(UnsafeIdentifierError):
            safe_id(".")

    def test_rejects_empty_string(self):
        with self.assertRaises(UnsafeIdentifierError):
            safe_id("")

    def test_rejects_null_byte(self):
        with self.assertRaises(UnsafeIdentifierError):
            safe_id("a\x00b")


if __name__ == "__main__":
    unittest.main()
