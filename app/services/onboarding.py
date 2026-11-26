from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Keyword


async def add_keyword(session: AsyncSession, value: str) -> str:
    term = value.strip()
    if not 1 <= len(term) <= 100:
        return "Enter a keyword between 1 and 100 characters."

    statement = (
        insert(Keyword)
        .values(term=term, folded=term.casefold())
        .on_conflict_do_nothing(index_elements=[Keyword.folded])
        .returning(Keyword.id)
    )
    created = await session.scalar(statement)
    await session.commit()
    return "Keyword added." if created is not None else "Keyword already exists."
