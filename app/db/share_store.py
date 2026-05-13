# app/db/share_store.py
import json
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import config


class Base(DeclarativeBase):
    pass


class SharePlan(Base):
    __tablename__ = "share_plans"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plan = Column(Text, nullable=False)
    structured_plan = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


def _get_engine():
    db_url = config.share_db_url
    if db_url.startswith("sqlite:///"):
        db_path = db_url[len("sqlite:///"):]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(
        db_url,
        connect_args={"check_same_thread": False} if "sqlite" in db_url else {},
    )


_engine = _get_engine()


def create_tables() -> None:
    Base.metadata.create_all(_engine)


def save_share(plan: str, structured_plan: dict) -> str:
    """Persist a share and return its UUID."""
    share_id = str(uuid.uuid4())
    with Session(_engine) as session:
        row = SharePlan(
            id=share_id,
            plan=plan,
            structured_plan=json.dumps(structured_plan, ensure_ascii=False),
        )
        session.add(row)
        session.commit()
    return share_id


def get_share(share_id: str) -> dict | None:
    """Return {plan, structured_plan} or None if not found."""
    with Session(_engine) as session:
        row = session.get(SharePlan, share_id)
        if row is None:
            return None
        return {
            "plan": row.plan,
            "structured_plan": json.loads(row.structured_plan),
        }
