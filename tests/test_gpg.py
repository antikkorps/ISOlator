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
