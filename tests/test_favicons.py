"""Exercise real Hugo output without writing into the deployment submodule."""

import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest


THEME = Path(__file__).resolve().parents[1]
ICONS = (
    "apple-touch-icon.png", "favicon-32x32.png", "favicon-16x16.png",
    "site.webmanifest", "favicon.ico",
)


class FaviconsTest(unittest.TestCase):
    def test_content_versions_update_and_missing_assets_remain_supported(self):
        with tempfile.TemporaryDirectory(prefix="hermit-favicons-") as directory:
            site = Path(directory)
            (site / "layouts/partials").mkdir(parents=True)
            (site / "static").mkdir()
            (site / "hugo.toml").write_text('baseURL = "https://example.test/"\n')
            (site / "layouts/index.html").write_text('{{ partial "favicons.html" . }}')
            (site / "layouts/partials/favicons.html").write_text(
                (THEME / "layouts/partials/favicons.html").read_text())

            def build():
                subprocess.run(
                    ["hugo", "--source", str(site), "--destination", str(site / "build")],
                    check=True, capture_output=True, timeout=20)
                return (site / "build/index.html").read_text()

            html = build()
            for name in ICONS:
                self.assertIn(f'href="/{name}"', html)
                (site / "static" / name).write_bytes(b"first")
            html = build()
            version = hashlib.sha256(b"first").hexdigest()[:12]
            for name in ICONS:
                self.assertIn(f'href="/{name}?v={version}"', html)
            self.assertIn('sizes="32x32"', html)
            self.assertIn('rel="apple-touch-icon"', html)
            (site / "static/favicon.ico").write_bytes(b"replacement")
            html = build()
            replacement = hashlib.sha256(b"replacement").hexdigest()[:12]
            self.assertIn(f'href="/favicon.ico?v={replacement}"', html)
            self.assertIn(f'href="/favicon-32x32.png?v={version}"', html)


if __name__ == "__main__":
    unittest.main()
