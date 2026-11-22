import hashlib
import shutil
import tempfile
import unittest
from pathlib import Path

from isolator.cache import DigestCache
from isolator.verify import Status, load_pinned, verify_tree
from tests.test_gpg import _gpg, _new_key


@unittest.skipUnless(shutil.which("gpg") and shutil.which("gpgv"), "gpg/gpgv not installed")
class VerifyTreeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.home = base / "gnupg"
        key, self.fpr = _new_key(self.home, "distro")
        self.keys = base / "keys"
        self.keys.mkdir()
        (self.keys / "distro.gpg").write_bytes(key)
        (self.keys / "trusted.txt").write_text(f"# comment\n{self.fpr}  Test distro\n")
        self.root = base / "disk"
        (self.root / "iso").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def add_iso(self, name: str, content: bytes) -> str:
        (self.root / "iso" / name).write_bytes(content)
        return hashlib.sha256(content).hexdigest()

    def check(self) -> dict[str, Status]:
        return {r.iso.name: r.status for r in verify_tree(self.root, self.keys)}

    def test_detached_signed_sums(self):
        digest = self.add_iso("good.iso", b"good")
        self.add_iso("other.iso", b"other")
        sums = f"{digest}  good.iso\n{'0' * 64}  other.iso\n".encode()
        (self.root / "iso/SHA256SUMS").write_bytes(sums)
        (self.root / "iso/SHA256SUMS.gpg").write_bytes(_gpg(self.home, "--detach-sign", data=sums))
        self.assertEqual(self.check(), {"good.iso": Status.VERIFIED, "other.iso": Status.MISMATCH})

    def test_clearsigned_sums(self):
        digest = self.add_iso("fedora.iso", b"fedora")
        sums = f"SHA256 (fedora.iso) = {digest}\n".encode()
        (self.root / "iso/Fedora-CHECKSUM").write_bytes(_gpg(self.home, "--clearsign", data=sums))
        self.assertEqual(self.check(), {"fedora.iso": Status.VERIFIED})

    def test_unsigned_sums_do_not_count(self):
        digest = self.add_iso("x.iso", b"x")
        (self.root / "iso/SHA256SUMS").write_text(f"{digest}  x.iso\n")
        self.assertEqual(self.check(), {"x.iso": Status.UNVERIFIED})

    def test_tampered_sums_do_not_count(self):
        digest = self.add_iso("x.iso", b"x")
        sums = f"{digest}  x.iso\n".encode()
        (self.root / "iso/SHA256SUMS.gpg").write_bytes(_gpg(self.home, "--detach-sign", data=sums))
        (self.root / "iso/SHA256SUMS").write_bytes(sums + b"0" * 64 + b"  evil.iso\n")
        self.assertEqual(self.check(), {"x.iso": Status.UNVERIFIED})

    def test_signature_over_the_iso_itself(self):
        self.add_iso("cachy.iso", b"cachy")
        (self.root / "iso/cachy.iso.sig").write_bytes(_gpg(self.home, "--detach-sign", data=b"cachy"))
        self.assertEqual(self.check(), {"cachy.iso": Status.VERIFIED})

    def test_cache_skips_hashing_but_still_checks_signatures(self):
        digest = self.add_iso("x.iso", b"x")
        sums = f"{digest}  x.iso\n".encode()
        (self.root / "iso/SHA256SUMS").write_bytes(sums)
        (self.root / "iso/SHA256SUMS.gpg").write_bytes(_gpg(self.home, "--detach-sign", data=sums))
        calls = []

        def compute(path, algo):
            calls.append(path)
            return hashlib.sha256(path.read_bytes()).hexdigest()

        store = Path(self.tmp.name) / "digests.json"
        for _ in range(2):
            cache = DigestCache(store, compute=compute)
            reports = verify_tree(self.root, self.keys, cache=cache)
            cache.save()
            self.assertEqual([r.status for r in reports], [Status.VERIFIED])
        self.assertEqual(len(calls), 1)
        (self.root / "iso/SHA256SUMS.gpg").write_bytes(b"garbage")
        cache = DigestCache(store, compute=compute)
        self.assertEqual([r.status for r in verify_tree(self.root, self.keys, cache=cache)],
                         [Status.UNVERIFIED])

    def test_load_pinned(self):
        self.assertEqual(load_pinned(self.keys / "trusted.txt"), {self.fpr: "Test distro"})


if __name__ == "__main__":
    unittest.main()
