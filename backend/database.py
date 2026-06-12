from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.orm import declarative_base, sessionmaker

from backend.core.config import get_settings

settings = get_settings()
DATABASE_URL = settings.database_url

PRODUCTION_POOL_SETTINGS = {
    "pool_size": 3,
    "max_overflow": 2,
    "pool_timeout": 30,
    "pool_recycle": 1800,
    "pool_pre_ping": True,
}

engine_kwargs = {
    "pool_pre_ping": True,
    "future": True,
}

if settings.is_sqlite:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs.update(PRODUCTION_POOL_SETTINGS)

engine = create_engine(DATABASE_URL, **engine_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def database_host() -> str:
    try:
        url = make_url(DATABASE_URL)
        return url.host or url.database or "local"
    except Exception:
        return "unknown"


def db_pool_settings() -> dict:
    if settings.is_sqlite:
        return {
            "pool_pre_ping": True,
            "sqlite": True,
            "database_host": database_host(),
        }
    return {
        **PRODUCTION_POOL_SETTINGS,
        "database_host": database_host(),
    }


@contextmanager
def session_scope():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
