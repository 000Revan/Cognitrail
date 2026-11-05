"""个人外链访问记录，仅表示点击入口，不表示完成学习。"""

from datetime import datetime

from sqlalchemy import ForeignKeyConstraint, Index
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import TABLE_OPTIONS, Base


class ResourceVisit(Base):
    __tablename__ = "resource_visits"
    __table_args__ = (
        ForeignKeyConstraint(
            ["session_id", "release_id"],
            ["learning_sessions.id", "learning_sessions.release_id"],
            name="fk_resource_visits_session",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["release_id", "release_resource_id"],
            ["release_resources.release_id", "release_resources.id"],
            name="fk_resource_visits_resource",
            ondelete="RESTRICT",
            onupdate="RESTRICT",
        ),
        Index("idx_resource_visits_session", "session_id", "release_id"),
        Index("idx_resource_visits_resource", "release_id", "release_resource_id"),
        TABLE_OPTIONS,
    )
    session_id: Mapped[int] = mapped_column(mysql.BIGINT(unsigned=True), primary_key=True)
    release_resource_id: Mapped[int] = mapped_column(mysql.BIGINT(unsigned=True), primary_key=True)
    release_id: Mapped[int] = mapped_column(mysql.BIGINT(unsigned=True), nullable=False)
    first_visited_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    last_visited_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
