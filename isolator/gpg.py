"""OpenPGP signature checks with gpgv against pinned key fingerprints.

gpgv only verifies, never imports or trusts anything, and runs with an empty
temporary GNUPGHOME so the user's own keyrings never take part. A signature
is accepted only if gpgv reports it valid AND the primary key fingerprint is
in the pinned set: a key merely present in the keyring is not enough.
"""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class SignatureError(Exception):
    pass


def _status(stdout: str) -> list[list[str]]:
    return [line.split()[1:] for line in stdout.splitlines() if line.startswith("[GNUPG:] ")]


def _pinned_signer(status: list[list[str]], pinned: set[str]) -> str:
    if any(s[0] == "BADSIG" for s in status):
        raise SignatureError("bad signature")
    # VALIDSIG <fpr> ... <primary-key-fpr>; several signatures may be present
    # (Ubuntu signs with an old and a new key), one pinned valid one suffices.
    signers = [s[-1].upper() for s in status if s[0] == "VALIDSIG"]
    for fpr in signers:
        if fpr in {p.upper() for p in pinned}:
            return fpr
    raise SignatureError(f"no valid signature by a pinned key (valid signers: {signers or 'none'})")


def _gpgv(args: list[str], keyrings: list[Path], home: str) -> list[list[str]]:
    cmd = ["gpgv", "--homedir", home, "--status-fd", "1"]
    for k in keyrings:
        cmd += ["--keyring", str(Path(k).resolve())]
    res = subprocess.run(cmd + args, capture_output=True, text=True)
    return _status(res.stdout)


def verify_detached(data: bytes, signature: bytes, keyrings: list[Path], pinned: set[str]) -> str:
    """Primary fingerprint of the pinned key that signed exactly `data`."""
    with tempfile.TemporaryDirectory(prefix="isolator-gpg-") as home:
        sig, dat = Path(home, "data.sig"), Path(home, "data")
        sig.write_bytes(signature)
        dat.write_bytes(data)
        return _pinned_signer(_gpgv([str(sig), str(dat)], keyrings, home), pinned)


def verify_clearsigned(document: bytes, keyrings: list[Path], pinned: set[str]) -> tuple[str, bytes]:
    """(signer, signed text). Only the text gpgv extracts is returned: lines
    outside the signed block of a clearsigned file are attacker-controlled."""
    with tempfile.TemporaryDirectory(prefix="isolator-gpg-") as home:
        doc, out = Path(home, "doc.asc"), Path(home, "plain")
        doc.write_bytes(document)
        signer = _pinned_signer(_gpgv(["--output", str(out), str(doc)], keyrings, home), pinned)
        return signer, out.read_bytes()


def verify_detached_file(path: Path, signature: bytes, keyrings: list[Path], pinned: set[str]) -> str:
    """Same as verify_detached for a file too large to hold in memory (an
    ISO signed directly, as CachyOS does); gpgv streams it from disk."""
    with tempfile.TemporaryDirectory(prefix="isolator-gpg-") as home:
        sig = Path(home, "data.sig")
        sig.write_bytes(signature)
        return _pinned_signer(_gpgv([str(sig), str(Path(path).resolve())], keyrings, home), pinned)
