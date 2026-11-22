import tempfile
import unittest
from pathlib import Path

from isolator.sums import file_digest, parse_sums

H256 = "a" * 64
H512 = "b" * 128


class ParseSumsTest(unittest.TestCase):
    def test_gnu_style_text_and_binary(self):
        text = f"{H256}  ubuntu.iso\n{H512} *debian.iso\n"
        self.assertEqual(parse_sums(text), {"ubuntu.iso": ("sha256", H256),
                                            "debian.iso": ("sha512", H512)})

    def test_bsd_style(self):
        text = f"# Fedora-Workstation-Live-45\nSHA256 (Fedora.iso) = {H256}\n"
        self.assertEqual(parse_sums(text), {"Fedora.iso": ("sha256", H256)})

    def test_uppercase_hex_is_normalised(self):
        self.assertEqual(parse_sums(f"{H256.upper()}  x.iso")["x.iso"], ("sha256", H256))

    def test_ignores_noise_and_paths_with_directories(self):
        text = f"random line\n{H256}  ./x.iso\n{H256}  sub/y.iso\n{'c' * 63}  short.iso\n"
        self.assertEqual(parse_sums(text), {"x.iso": ("sha256", H256)})

    def test_conflicting_entries_are_refused(self):
        with self.assertRaises(ValueError):
            parse_sums(f"{H256}  x.iso\n{'d' * 64}  x.iso\n")


class DigestTest(unittest.TestCase):
    def test_sha256_of_file(self):
        with tempfile.NamedTemporaryFile() as f:
            f.write(b"abc")
            f.flush()
            self.assertEqual(file_digest(Path(f.name), "sha256"),
                             "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")


if __name__ == "__main__":
    unittest.main()
