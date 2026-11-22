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


# Any of these anywhere refuses the whole file: a revoked key must stop
# everything it signed, even next to another valid signature.
FATAL = {"BADSIG", "REVKEYSIG"}
# A signature is usable only if its own block says GOODSIG; EXPSIG and
# EXPKEYSIG come with a VALIDSIG too and must not count.
USABLE = "GOODSIG"


def _blocks(status: list[list[str]]) -> list[list[list[str]]]:
    """Status lines grouped per signature (gpgv starts each with NEWSIG)."""
    blocks: list[list[list[str]]] = [[]]
    for s in status:
        if s[0] == "NEWSIG":
            blocks.append([])
        blocks[-1].append(s)
    return [b for b in blocks if b]


def _pinned_signer(status: list[list[str]], pinned: set[str]) -> str:
    keywords = {s[0] for s in status}
    if keywords & FATAL:
        raise SignatureError(f"refused: {', '.join(sorted(keywords & FATAL))}")
    wanted, signers = {p.upper() for p in pinned}, []
    for block in _blocks(status):
        kinds = {s[0] for s in block}
        # VALIDSIG <fpr> ... <primary-key-fpr>: pin the primary key, not a subkey.
        for fpr in (s[-1].upper() for s in block if s[0] == "VALIDSIG"):
            signers.append(fpr)
            if USABLE in kinds and fpr in wanted:
                return fpr
    raise SignatureError(f"no usable signature by a pinned key (signers: {signers or 'none'}, "
                         f"status: {', '.join(sorted(keywords - {'NEWSIG'}))})")


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
