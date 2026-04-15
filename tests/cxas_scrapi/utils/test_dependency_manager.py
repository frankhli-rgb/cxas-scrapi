import unittest

from cxas_scrapi.utils.dependency_manager import SessionDependencyManager


class TestSessionDependencyManager(unittest.TestCase):

    def test_resolve_session_id_memory_hit(self):
        manager = SessionDependencyManager()
        manager._memory_cache["test_test"] = "session_123"

        resolved = manager.resolve_session_id("test_test")
        self.assertEqual(resolved, "session_123")

    def test_resolve_session_id_miss(self):
        manager = SessionDependencyManager()
        resolved = manager.resolve_session_id("test_test")

        self.assertIsNone(resolved)

    def test_cache_session_id(self):
        manager = SessionDependencyManager()
        manager.cache_session_id("test_test", "session_789")

        self.assertEqual(manager._memory_cache["test_test"], "session_789")
        self.assertEqual(manager.resolve_session_id("test_test"), "session_789")
