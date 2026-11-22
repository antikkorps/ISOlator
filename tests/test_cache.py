import os
import tempfile
import unittest
from pathlib import Path

from isolator.cache import DigestCache


class DigestCacheTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.store = base / "cache/digests.json"
        self.iso = base / "x.iso"
        self.iso.write_bytes(b"data")
        self.calls = 0

    def tearDown(self):
        self.tmp.cleanup()

    def compute(self, path, algo):
        self.calls += 1
        return f"{algo}-{path.read_bytes().decode()}"

    def digest(self):
        cache = DigestCache(self.store, compute=self.compute)
        result = cache.digest(self.iso, "sha256")
        cache.save()
        return result

    def test_second_run_reuses_digest(self):
        self.assertEqual(self.digest(), "sha256-data")
        self.assertEqual(self.digest(), "sha256-data")
        self.assertEqual(self.calls, 1)

    def test_size_change_invalidates(self):
        self.digest()
        self.iso.write_bytes(b"changed")
        self.assertEqual(self.digest(), "sha256-changed")
        self.assertEqual(self.calls, 2)

    def test_mtime_change_invalidates(self):
        self.digest()
        st = self.iso.stat()
        os.utime(self.iso, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
        self.digest()
        self.assertEqual(self.calls, 2)

    def test_algorithms_are_cached_separately(self):
        cache = DigestCache(self.store, compute=self.compute)
        cache.digest(self.iso, "sha256")
        self.assertEqual(cache.digest(self.iso, "sha512"), "sha512-data")
        self.assertEqual(self.calls, 2)

    def test_corrupt_store_is_ignored(self):
        self.store.parent.mkdir(parents=True)
        self.store.write_text("{not json")
        self.assertEqual(self.digest(), "sha256-data")

    def test_disabled_cache_always_computes(self):
        for _ in range(2):
            cache = DigestCache(None, compute=self.compute)
            cache.digest(self.iso, "sha256")
            cache.save()
        self.assertEqual(self.calls, 2)


if __name__ == "__main__":
    unittest.main()
