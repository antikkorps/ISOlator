import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from isolator.gpg import SignatureError, verify_clearsigned, verify_detached


def _gpg(home: Path, *args: str, data: bytes | None = None) -> bytes:
    env = {**os.environ, "GNUPGHOME": str(home)}
    return subprocess.run(["gpg", "--batch", "--quiet", "--pinentry-mode", "loopback",
                           "--passphrase", "", *args], input=data, env=env,
                          capture_output=True, check=True).stdout


def _new_key(home: Path, name: str) -> tuple[bytes, str]:
    home.mkdir(mode=0o700)
    _gpg(home, "--quick-gen-key", f"{name} <{name}@example.invalid>", "ed25519", "sign", "never")
    fpr = [line.split(":")[9] for line in _gpg(home, "--with-colons", "--list-keys").decode().splitlines()
           if line.startswith("fpr:")][0]
    return _gpg(home, "--export"), fpr


@unittest.skipUnless(shutil.which("gpg") and shutil.which("gpgv"), "gpg/gpgv not installed")
class GpgTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.home, cls.other = base / "signer", base / "attacker"
        key, cls.fpr = _new_key(cls.home, "signer")
        _, cls.other_fpr = _new_key(cls.other, "attacker")
        cls.keyring = base / "trusted.gpg"
        cls.keyring.write_bytes(key)
        cls.data = b"0" * 64 + b"  x.iso\n"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_detached_signature_returns_signer(self):
        sig = _gpg(self.home, "--detach-sign", data=self.data)
        self.assertEqual(verify_detached(self.data, sig, [self.keyring], {self.fpr}), self.fpr)

    def test_detached_signature_over_other_data_fails(self):
        sig = _gpg(self.home, "--detach-sign", data=self.data)
        with self.assertRaises(SignatureError):
            verify_detached(self.data + b"evil", sig, [self.keyring], {self.fpr})

    def test_clearsigned_returns_only_signed_text(self):
        signed = _gpg(self.home, "--clearsign", data=self.data)
        fpr, text = verify_clearsigned(b"injected  line\n" + signed, [self.keyring], {self.fpr})
        self.assertEqual(fpr, self.fpr)
        self.assertEqual(text, self.data)

    def test_valid_key_not_pinned_is_refused(self):
        sig = _gpg(self.home, "--detach-sign", data=self.data)
        with self.assertRaises(SignatureError):
            verify_detached(self.data, sig, [self.keyring], {self.other_fpr})

    def test_unknown_signer_is_refused(self):
        sig = _gpg(self.other, "--detach-sign", data=self.data)
        with self.assertRaises(SignatureError):
            verify_detached(self.data, sig, [self.keyring], {self.fpr, self.other_fpr})


if __name__ == "__main__":
    unittest.main()


FPR = "A" * 40


def status(*lines: str) -> list[list[str]]:
    return [line.split() for line in lines]


class PinnedSignerTest(unittest.TestCase):
    def check(self, *lines):
        from isolator.gpg import _pinned_signer
        return _pinned_signer(status(*lines), {FPR})

    def valid(self, keyword="GOODSIG"):
        return ["NEWSIG", f"{keyword} KEYID uid", f"VALIDSIG {'B' * 40} 2026 1 0 4 0 1 10 00 {FPR}"]

    def test_good_signature(self):
        self.assertEqual(self.check(*self.valid()), FPR)

    def test_expired_signature_revoked_or_expired_key_refused(self):
        for keyword in ("EXPSIG", "EXPKEYSIG", "REVKEYSIG"):
            with self.assertRaises(SignatureError, msg=keyword):
                self.check(*self.valid(keyword))

    def test_unknown_second_signer_tolerated(self):
        self.assertEqual(self.check(*self.valid(), "NEWSIG", "ERRSIG 1234 1 10 00 0 9"), FPR)

    def test_any_bad_or_revoked_signature_refuses_the_file(self):
        for keyword in ("BADSIG", "REVKEYSIG"):
            with self.assertRaises(SignatureError, msg=keyword):
                self.check(*self.valid(), "NEWSIG", f"{keyword} OTHER uid")

    def test_validsig_without_goodsig_in_same_block_refused(self):
        with self.assertRaises(SignatureError):
            self.check("NEWSIG", "GOODSIG X uid", "NEWSIG", f"VALIDSIG {'B' * 40} 2026 1 0 4 0 1 10 00 {FPR}")


@unittest.skipUnless(shutil.which("gpg") and shutil.which("gpgv"), "gpg/gpgv not installed")
class RealExpiryTest(unittest.TestCase):
    def test_expired_signature_from_real_gpg(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / "k"
            home.mkdir(mode=0o700)
            past = ("--faked-system-time", "20250101T000000")
            _gpg(home, *past, "--quick-gen-key", "old <old@example.invalid>", "ed25519", "sign", "never")
            fpr = [line.split(":")[9] for line in _gpg(home, "--with-colons", "--list-keys").decode().splitlines()
                   if line.startswith("fpr:")][0]
            ring = Path(tmp) / "k.gpg"
            ring.write_bytes(_gpg(home, "--export"))
            sig = _gpg(home, *past, "--default-sig-expire", "1d", "--detach-sign", data=b"data")
            with self.assertRaises(SignatureError):
                verify_detached(b"data", sig, [ring], {fpr})
