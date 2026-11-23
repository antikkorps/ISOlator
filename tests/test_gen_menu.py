import subprocess
import tempfile
import unittest
from pathlib import Path

GEN_MENU = Path(__file__).resolve().parent.parent / "gen-menu.py"


class InvalidConfigTest(unittest.TestCase):
    def test_invalid_config_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            menu = Path(tmp) / "multiboot" / "menu.cfg"
            menu.parent.mkdir()
            menu.write_text("# previous menu\n")
            (menu.parent / "isolator.toml").write_text("[menu]\ntimout = 5\n")
            res = subprocess.run([str(GEN_MENU), "--root", tmp], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1)
            self.assertIn("timout", res.stderr)
            self.assertEqual(menu.read_text(), "# previous menu\n")


if __name__ == "__main__":
    unittest.main()
