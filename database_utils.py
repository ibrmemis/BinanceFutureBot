"""
Modern database utilities with context managers and optimizations
"""
from contextlib import contextmanager
from typing import Generator, Optional, Any
from sqlalchemy.orm import Session
from database import SessionLocal
from utils import setup_logger

logger = setup_logger("database_utils")

@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database sessions.
    Automatically handles session cleanup and error rollback.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def with_db_session(func):
    """
    Decorator that automatically provides a database session as the first argument.
    Usage: @with_db_session
           def my_function(db: Session, other_args...):
    """
    def wrapper(*args, **kwargs):
        with get_db_session() as db:
            return func(db, *args, **kwargs)
    return wrapper


class DatabaseManager:
    """Centralized database operations with optimizations"""
    
    @staticmethod
    def get_positions_batch(position_ids: list[int]) -> list:
        """Get multiple positions in a single query"""
        with get_db_session() as db:
            from database import Position
            return db.query(Position).filter(Position.id.in_(position_ids)).all()
    
    @staticmethod
    def update_positions_batch(updates: list[dict[str, Any]]) -> bool:
        """Update multiple positions in a single transaction"""
        try:
            with get_db_session() as db:
                from database import Position
                for update in updates:
                    pos_id = update.pop('id')
                    db.query(Position).filter(Position.id == pos_id).update(update)
                db.commit()
                return True
        except Exception as e:
            logger.error(f"Batch update error: {e}")
            return False
    
    @staticmethod
    def get_setting(key: str, default: Any = None) -> Any:
        """Get a single setting value with caching"""
        with get_db_session() as db:
            from database import Settings
            setting = db.query(Settings).filter(Settings.key == key).first()
            return setting.value if setting else default
    
    @staticmethod
    def set_setting(key: str, value: str) -> bool:
        """Set a setting value with upsert logic"""
        try:
            with get_db_session() as db:
                from database import Settings
                from datetime import datetime, timezone
                
                setting = db.query(Settings).filter(Settings.key == key).first()
                if setting:
                    setting.value = value
                    setting.updated_at = datetime.now(timezone.utc)
                else:
                    setting = Settings(key=key, value=value)
                    db.add(setting)
                db.commit()
                return True
        except Exception as e:
            logger.error(f"Set setting error: {e}")
            return False
