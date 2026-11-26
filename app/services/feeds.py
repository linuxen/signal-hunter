from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit
from xml.etree.ElementTree import Element

import httpx
from bs4 import BeautifulSoup
from defusedxml import ElementTree


@dataclass(frozen=True)
class Feed:
    name: str
    url: str


FEEDS = (
    Feed("Hacker News", "https://hnrss.org/newest"),
    Feed("Python Insider", "https://blog.python.org/feeds/posts/default"),
)

ATOM = "{http://www.w3.org/2005/Atom}"
RSS_CONTENT = "{http://purl.org/rss/1.0/modules/content/}encoded"
MAX_FEED_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class Entry:
    title: str
    body: str
    url: str


def plain_text(element: Element | None) -> str:
    if element is None:
        return ""
    text = " ".join(element.itertext()).strip()
    if "<" not in text and "&" not in text:
        return text
    return BeautifulSoup(text, "html.parser").get_text(" ", strip=True)


def article_url(link: str, feed_url: str) -> str | None:
    if not link.strip():
        return None
    try:
        url = urljoin(feed_url, link.strip())
        parts = urlsplit(url)
    except ValueError:
        return None
    if parts.scheme in {"http", "https"} and parts.hostname and parts.username is None:
        return url
    return None


def parse_feed(payload: bytes, feed_url: str) -> list[Entry]:
    root = ElementTree.fromstring(payload, forbid_dtd=True)
    if root.tag == ATOM + "feed":
        items = root.findall(ATOM + "entry")
        namespace = ATOM
        body_tags = (ATOM + "content", ATOM + "summary")
    elif root.tag == "rss" and root.find("channel") is not None:
        items = root.findall("channel/item")
        namespace = ""
        body_tags = (RSS_CONTENT, "description")
    else:
        raise ValueError("Expected RSS or Atom")

    entries = []
    for item in items:
        title = plain_text(item.find(namespace + "title"))
        if namespace:
            link = next(
                (link.get("href", "") for link in item.findall(ATOM + "link")
                 if link.get("rel", "alternate") == "alternate" and link.get("href")),
                "",
            )
        else:
            link = item.findtext("link", "")
        url = article_url(link, feed_url)
        if title and url:
            body = " ".join(filter(None, (plain_text(item.find(tag)) for tag in body_tags)))
            entries.append(Entry(title, body, url))
    return entries


async def fetch_feed(client: httpx.AsyncClient, feed: Feed) -> list[Entry]:
    async with client.stream("GET", feed.url) as response:
        response.raise_for_status()
        payload = bytearray()
        async for chunk in response.aiter_bytes(chunk_size=64 * 1024):
            if len(payload) + len(chunk) > MAX_FEED_BYTES:
                raise ValueError("Feed exceeds the size limit")
            payload.extend(chunk)
    return parse_feed(bytes(payload), str(response.url))
