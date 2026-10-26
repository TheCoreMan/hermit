"""Exercise real Hugo social metadata builds in isolated temporary sites."""

import hashlib
from html.parser import HTMLParser
from pathlib import Path
import subprocess
import tempfile
import unittest


THEME = Path(__file__).resolve().parents[1]


class Head(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.meta = {}
        self.feed(html.split("</head>", 1)[0])

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "meta":
            key = attrs.get("property", attrs.get("name"))
            self.meta.setdefault(key, []).append(attrs.get("content"))


class SocialPreviewsTest(unittest.TestCase):
    def fixture(self, image="images/card.png"):
        temporary = tempfile.TemporaryDirectory(prefix="hermit-social-")
        self.addCleanup(temporary.cleanup)
        site = Path(temporary.name)

        def write(path, contents):
            target = site / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(contents, encoding="utf-8")

        write("hugo.toml", f'''baseURL = "https://example.test/"
title = "Example"
[params]
socialImage = "{image}"
socialImageAlt = "Portrait"
socialAnimation = "images/small.gif"
socialAnimationSize = 96
''')
        layout = ('<html><head>{{ partial "opengraph.html" . }}'
                  '{{ partial "twitter_card.html" . }}</head></html>')
        write("layouts/index.html", layout)
        write("layouts/_default/single.html", layout)
        for name in ("opengraph", "twitter_card", "share-image"):
            write(f"layouts/partials/{name}.html",
                  (THEME / f"layouts/partials/{name}.html").read_text())
        write("static/images/card.png", "default image bytes")
        write("static/images/article.png", "specific article bytes")
        write("content/local.md",
              '+++\ntitle = "Local"\nfeaturedImg = "images/article.png"\n+++\n')
        write("content/remote.md", '+++\ntitle = "Remote"\n'
              'images = ["https://cdn.example.test/article.jpg"]\n+++\n')
        write("content/bundle/index.md",
              '+++\ntitle = "Bundle"\nimages = ["cover.png"]\n+++\n')
        write("content/bundle/cover.png", "page resource bytes")
        write("content/legacy.md", '+++\ntitle = "Legacy"\n[twitter]\n'
              'card = "summary_large_image"\nsite = "@example"\n'
              'image = "https://i.imgur.com/ROzkHYp.png"\n+++\n')
        write("content/twitter.md", '+++\ntitle = "Twitter override"\n[twitter]\n'
              'card = "summary_large_image"\nsite = "@example"\n'
              'image = "https://cdn.example.test/twitter.jpg"\n+++\n')
        write("content/app.md",
              '+++\ntitle = "App"\n[twitter]\ncard = "app"\n+++\n')
        write("content/player.md", '+++\ntitle = "Player"\n[twitter]\n'
              'card = "player"\nplayer = "https://player.example.test/"\n'
              'player_width = 640\nplayer_height = 360\n+++\n')
        return site

    def build(self, site, page="index.html"):
        result = subprocess.run(
            ["hugo", "--source", str(site), "--destination", str(site / "build"),
             "--cacheDir", str(site / "cache")],
            capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return Head((site / "build" / page).read_text()).meta

    def default_url(self, data=b"default image bytes"):
        digest = hashlib.sha256(data).hexdigest()[:12]
        return f"https://example.test/images/card.png?v={digest}"

    def test_single_large_still_for_all_default_cards_even_with_legacy_gif_config(self):
        head = self.build(self.fixture())
        self.assertEqual(head["og:image"], [self.default_url()])
        self.assertEqual(head["twitter:image"], head["og:image"])
        self.assertEqual(head["og:image:type"], ["image/png"])
        self.assertEqual(head["og:image:width"], ["1200"])
        self.assertEqual(head["og:image:height"], ["630"])
        self.assertEqual(head["og:image:alt"], ["Portrait"])
        self.assertEqual(head["twitter:card"], ["summary_large_image"])

    def test_version_is_stable_and_changes_with_the_image_bytes(self):
        site = self.fixture()
        first = self.build(site)["og:image"]
        self.assertEqual(self.build(site)["og:image"], first)
        (site / "static/images/card.png").write_bytes(b"replacement image")
        self.assertEqual(self.build(site)["og:image"],
                         [self.default_url(b"replacement image")])
        self.assertNotEqual(self.build(site)["og:image"], first)

    def test_specific_local_remote_and_bundle_artwork_is_not_replaced_or_versioned(self):
        site = self.fixture()
        for page, url in (
            ("local/index.html", "https://example.test/images/article.png"),
            ("remote/index.html", "https://cdn.example.test/article.jpg"),
            ("bundle/index.html", "https://example.test/bundle/cover.png"),
        ):
            with self.subTest(page=page):
                head = self.build(site, page)
                self.assertEqual(head["og:image"], [url])
                self.assertEqual(head["twitter:image"], [url])
                self.assertNotIn("og:image:width", head)
                self.assertNotIn("og:image:type", head)

    def test_legacy_avatar_uses_versioned_default_but_explicit_twitter_art_survives(self):
        site = self.fixture()
        head = self.build(site, "legacy/index.html")
        self.assertEqual(head["twitter:image"], [self.default_url()])
        head = self.build(site, "twitter/index.html")
        self.assertEqual(head["twitter:image"],
                         ["https://cdn.example.test/twitter.jpg"])
        self.assertNotIn("twitter:image", self.build(site, "app/index.html"))
        player = self.build(site, "player/index.html")
        self.assertEqual(player["twitter:card"], ["player"])
        self.assertEqual(player["twitter:player"], ["https://player.example.test/"])
        self.assertEqual(player["twitter:player:width"], ["640"])
        self.assertEqual(player["twitter:image"], [self.default_url()])

    def test_remote_default_does_not_require_a_local_file(self):
        head = self.build(self.fixture("https://cdn.example.test/default.png"))
        self.assertEqual(head["og:image"],
                         ["https://cdn.example.test/default.png"])
        self.assertEqual(head["twitter:image"], head["og:image"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
