"""Build real minimal Hugo sites; never modify application/deployment assets."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


THEME = Path(__file__).resolve().parents[1]
IMAGES = (
    "256.webp", "128.webp", "64.webp", "32.webp", "original.webp",
    "alpha-mask.webp", "portrait-static.webp", "fallback.png",
)
SHARED = (
    "css/pixel-lava.css", "js/pixel-lava-loader.js",
    "js/pixel-lava.js", "js/pixel-lava-worker.js",
)


class PixelLavaAssetsTest(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory(prefix="hermit-pixel-lava-")
        self.addCleanup(temporary.cleanup)
        site = Path(temporary.name)

        def write(path, contents):
            target = site / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents, encoding="utf-8")

        write("hugo.toml", 'baseURL = "https://example.test/"\n')
        write("layouts/index.html", '{{ partial "pixel-lava.html" (dict) }}')
        write("layouts/_default/single.html", "{{ .Content }}")
        write("content/portrait.md",
              '+++\ntitle = "Custom portrait"\n+++\n'
              '{{< pixel-lava images="images/custom" >}}\n')
        for relative in ("partials/pixel-lava.html", "shortcodes/pixel-lava.html"):
            source = THEME / "layouts" / relative
            write(f"layouts/{relative}", source.read_text(encoding="utf-8"))
        # Nonempty markers test build-time completeness, not image decoding.
        for relative in SHARED:
            write(f"static/{relative}", "/* fixture asset */\n")
        for directory in ("images/pixel-lava", "images/custom"):
            for name in IMAGES:
                write(f"static/{directory}/{name}", "fixture asset\n")
        return site

    def build(self, site):
        return subprocess.run(
            ["hugo", "--source", str(site), "--destination", str(site / "build"),
             "--cacheDir", str(site / "cache")],
            capture_output=True, text=True, timeout=20,
        )

    def assert_invalid(self, site, path):
        result = self.build(site)
        output = result.stdout + result.stderr
        self.assertNotEqual(result.returncode, 0, output)
        self.assertIn("pixel-lava: invalid required assets:", output)
        self.assertIn(path, output)
        self.assertIn("Supply the complete asset bundle", output)
        page = "portrait/index.html" if "/custom/" in path else "index.html"
        rendered = site / "build" / page
        if rendered.exists():
            self.assertNotIn("<pixel-lava", rendered.read_text(encoding="utf-8"))

    def test_complete_default_and_custom_assets_render(self):
        site = self.fixture()
        result = self.build(site)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for page, directory in (
            ("index.html", "images/pixel-lava"),
            ("portrait/index.html", "images/custom"),
        ):
            html = (site / "build" / page).read_text(encoding="utf-8")
            self.assertIn("<pixel-lava", html)
            self.assertIn(f'data-256="/{directory}/256.webp"', html)
            self.assertIn('data-speed="1" data-photo-size="1"', html)
            self.assertIn("/js/pixel-lava-loader.js?v=", html)

    def test_each_required_default_asset_is_mandatory(self):
        for relative in SHARED + tuple(f"images/pixel-lava/{n}" for n in IMAGES):
            with self.subTest(asset=relative):
                site = self.fixture()
                path = f"static/{relative}"
                (site / path).unlink()
                self.assert_invalid(site, path)

    def test_each_custom_shortcode_image_is_mandatory(self):
        for name in IMAGES:
            with self.subTest(asset=name):
                site = self.fixture()
                path = f"static/images/custom/{name}"
                (site / path).unlink()
                self.assert_invalid(site, path)

    def test_empty_files_and_directories_are_rejected(self):
        for relative in ("images/pixel-lava/256.webp", *SHARED):
            for kind in ("empty", "directory"):
                with self.subTest(asset=relative, kind=kind):
                    site = self.fixture()
                    path = f"static/{relative}"
                    target = site / path
                    if kind == "empty":
                        target.write_bytes(b"")
                    else:
                        target.unlink()
                        target.mkdir()
                    self.assert_invalid(site, path)

    def test_all_missing_assets_are_reported_together(self):
        site = self.fixture()
        paths = [f"static/images/pixel-lava/{name}" for name in IMAGES]
        for path in paths:
            (site / path).unlink()
        result = self.build(site)
        self.assertNotEqual(result.returncode, 0)
        output = result.stdout + result.stderr
        for path in paths:
            self.assertIn(f"{path} (missing)", output)


if __name__ == "__main__":
    unittest.main(verbosity=2)
