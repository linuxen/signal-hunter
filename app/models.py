from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Keyword(Base):
    __tablename__ = "keywords"

    id: Mapped[int] = mapped_column(primary_key=True)
    term: Mapped[str] = mapped_column(String(100))
    folded: Mapped[str] = mapped_column(unique=True)


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("keyword_id", "url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    keyword_id: Mapped[int] = mapped_column(ForeignKey("keywords.id", ondelete="CASCADE"))
    source: Mapped[str]
    title: Mapped[str]
    url: Mapped[str]
