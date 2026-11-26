import asyncio
import logging
from dataclasses import dataclass
from xml.etree.ElementTree import ParseError

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models import Keyword, Match
from app.services.feeds import FEEDS, Entry, Feed, fetch_feed
from app.services.matcher import matching_keywords

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanResult:
    added: int
    failed_feeds: tuple[str, ...]


class Scanner:
    def __init__(self, sessions: async_sessionmaker[AsyncSession], client: httpx.AsyncClient) -> None:
        self.sessions = sessions
        self.client = client
        self.last_result: ScanResult | None = None
        self.lock = asyncio.Lock()

    async def scan(self) -> None:
        async with self.lock:
            async with self.sessions() as session:
                rows = await session.execute(select(Keyword.term, Keyword.id))
                keywords = {term: keyword_id for term, keyword_id in rows}
            if not keywords:
                return

            results = await asyncio.gather(*(self._read_feed(feed) for feed in FEEDS))
            added = 0
            failed = []
            async with self.sessions() as session:
                for feed, entries in zip(FEEDS, results, strict=True):
                    if entries is None:
                        failed.append(feed.name)
                        continue
                    for entry in entries:
                        for term in matching_keywords(entry.title, entry.body, keywords):
                            statement = (
                                insert(Match)
                                .values(
                                    keyword_id=keywords[term], source=feed.name,
                                    title=entry.title, url=entry.url,
                                )
                                .on_conflict_do_nothing(index_elements=[Match.keyword_id, Match.url])
                                .returning(Match.id)
                            )
                            if await session.scalar(statement) is not None:
                                added += 1
                await session.commit()

            self.last_result = ScanResult(added, tuple(failed))

    async def _read_feed(self, feed: Feed) -> list[Entry] | None:
        try:
            return await fetch_feed(self.client, feed)
        except (httpx.HTTPError, ParseError, ValueError) as error:
            logger.warning("Could not scan %s: %s", feed.name, error)
            return None
