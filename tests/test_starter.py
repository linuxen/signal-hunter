import tempfile
import unittest
from contextlib import asynccontextmanager
from pathlib import Path

import httpx

from app.config import Settings
from app.main import create_app
from app.services.feeds import FEEDS, parse_feed
from app.services.matcher import matching_keywords

RSS = b"""<rss version="2.0"><channel>
  <item>
    <title>A release announcement</title>
    <link>https://example.org/release</link>
    <description><![CDATA[The <b>PYTHON</b> team has a new release.]]></description>
  </item>
  <item>
    <title>Unrelated story</title>
    <link>https://example.org/other</link>
    <description>A story about databases.</description>
  </item>
</channel></rss>"""

ATOM = b"""<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>A Python update</title>
    <link rel="self" href="/entry-data" />
    <link href="/update" />
    <summary type="html">&lt;p&gt;An update for developers.&lt;/p&gt;</summary>
  </entry>
</feed>"""


class StarterTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        directory = self.enterContext(tempfile.TemporaryDirectory())
        database = Path(directory) / "data" / "test.db"
        self.settings = Settings(database_url=f"sqlite+aiosqlite:///{database}", scan_interval_minutes=30)
        self.client = await self.enterAsyncContext(self.open_client())

    @asynccontextmanager
    async def open_client(self):
        def mock_feed(request: httpx.Request) -> httpx.Response:
            if str(request.url) == FEEDS[0].url:
                return httpx.Response(200, content=RSS)
            if str(request.url) == FEEDS[1].url:
                return httpx.Response(503)
            self.fail(f"Unexpected feed request: {request.url}")

        app = create_app(self.settings, feed_transport=httpx.MockTransport(mock_feed))
        async with app.router.lifespan_context(app), httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver",
        ) as client:
            yield client

    async def test_health_works_with_a_fresh_database(self):
        response = await self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    async def test_keyword_form_trims_input_and_prevents_duplicates(self):
        page = await self.client.get("/")
        self.assertIn("<h1>FeedWatch Starter</h1>", page.text)
        self.assertIn('name="keyword"', page.text)
        headers = {"HX-Request": "true"}
        response = await self.client.post("/keywords", data={"keyword": "  Python  "}, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<!doctype html>", response.text)
        self.assertIn("Keyword added.", response.text)
        duplicate = await self.client.post("/keywords", data={"keyword": "pYtHon"}, headers=headers)
        self.assertIn("Keyword already exists.", duplicate.text)
        self.assertEqual(duplicate.text.count("<li>Python</li>"), 1)
        invalid = await self.client.post("/keywords", data={"keyword": "  "}, headers=headers)
        self.assertIn("Enter a keyword between 1 and 100 characters.", invalid.text)

    def test_matcher_uses_case_insensitive_substrings_in_title_or_body(self):
        matched = matching_keywords("Python tools", "A STRASSE guide", ["thon", "straße", "rust", ""])
        self.assertEqual(matched, {"thon", "straße"})

    def test_atom_parser_reads_text_and_resolves_relative_links(self):
        entries = parse_feed(ATOM, "https://example.org/feed")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].title, "A Python update")
        self.assertEqual(entries[0].body, "An update for developers.")
        self.assertEqual(entries[0].url, "https://example.org/update")

    async def test_scan_saves_rss_matches_once_even_if_another_feed_fails(self):
        await self.client.post("/keywords", data={"keyword": "python"})
        headers = {"HX-Request": "true"}
        with self.assertLogs("app.services.scanner", level="WARNING"):
            first = await self.client.post("/scan", headers=headers)
        self.assertEqual(first.status_code, 200)
        self.assertIn("Last scan found 1 new match.", first.text)
        self.assertIn("Could not read Python Insider.", first.text)
        self.assertIn("A release announcement", first.text)
        self.assertNotIn("Unrelated story", first.text)

        async with self.open_client() as client:
            with self.assertLogs("app.services.scanner", level="WARNING"):
                second = await client.post("/scan", headers=headers)
            self.assertIn("Last scan found 0 new matches.", second.text)
            self.assertEqual(second.text.count('href="https://example.org/release"'), 1)
