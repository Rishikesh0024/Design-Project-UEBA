from pathlib import Path
import logging
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class Base(DeclarativeBase):
    pass


def _create_app_engine():
    engine_options = {"pool_pre_ping": True}
    if not settings.DATABASE_URL.startswith("sqlite"):
        engine_options.update(pool_size=10, max_overflow=20)

    try:
        eng = create_engine(settings.DATABASE_URL, **engine_options)
        with eng.connect():
            pass
        return eng
    except Exception as exc:
        if settings.ENVIRONMENT.lower() != "production":
            logger.warning(
                "Configured DATABASE_URL is unreachable (%s); using local SQLite fallback for development.",
                exc,
            )
            Path("data").mkdir(parents=True, exist_ok=True)
            sqlite_engine = create_engine(
                "sqlite:///data/ueba.db",
                connect_args={"check_same_thread": False},
            )
            return sqlite_engine
        raise


engine = _create_app_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    import app.models_db.models as db_models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    if "is_demo" not in {
        column["name"] for column in inspect(engine).get_columns("datasets")
    }:
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE datasets ADD COLUMN is_demo BOOLEAN NOT NULL DEFAULT FALSE"
            ))
    try:
        with SessionLocal() as db:
            if not db.query(db_models.AppUser).filter(db_models.AppUser.email == "analyst.dev@ueba.local").first():
                dev_user = db_models.AppUser(
                    id=1,
                    email="analyst.dev@ueba.local",
                    full_name="Development Analyst",
                    hashed_pw="dev_bypass_pw",
                    role="analyst",
                    is_active=True,
                )
                db.add(dev_user)
                db.commit()
    except Exception:
        pass


# Auto-initialize tables on startup if using SQLite
if engine.dialect.name == "sqlite":
    init_db()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
