import os
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.engine import URL
from sqlalchemy.orm import declarative_base

url = URL.create(
    drivername="postgresql+psycopg2",
    username=os.environ.get("DB_USER", "postgres"),
    password=os.environ.get("DB_PASS", "12345"),
    host=os.environ.get("DB_HOST", "localhost"),
    database=os.environ.get("DB_NAME", "postgres"),
)

engine = create_engine(url)
Base = declarative_base()


class User(Base):
    __tablename__ = "user"

    id = Column(Integer(), primary_key=True)
    user_id = Column(BigInteger(), nullable=False)
    full_name = Column(String())
    user_name = Column(String())
    phone = Column(String())
    blocked = Column(Boolean(), default=False)
    blocked_reason = Column(String(), default="")


class Valentine(Base):
    __tablename__ = "valentine"

    id = Column(Integer(), primary_key=True)
    sender = Column(Integer(), ForeignKey("user.id"))
    recipient = Column(String())
    text = Column(Text(), nullable=False)
    # Возможно могут быть траблы с date из-за таймзоны. Если так и будет, то нужно будет везде убрать timezone.utc
    date = Column(DateTime(), default=datetime.now(timezone.utc))
    admin_message_id = Column(Integer())


# Base.metadata.drop_all(engine)

Base.metadata.create_all(engine)
