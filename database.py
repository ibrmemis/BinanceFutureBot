import os
import base64
from datetime import datetime, timezone
from typing import Tuple, Generator
from functools import lru_cache

from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, Index, ForeignKey, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from cryptography.fernet import Fernet

from utils import setup_logger

logger = setup_logger("database")

# Database URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    logger.warning("DATABASE_URL not found in environment variables.")
    # Fallback to SQLite for local development if no Postgres URL is provided
    # This is safer than hardcoding Postgres credentials
    DATABASE_URL = "sqlite:///./trading_bot.db"
    logger.info(f"Using SQLite fallback: {DATABASE_URL}")

# Configure engine based on database type
connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
    engine_args = {}
else:
    # PostgreSQL optimized settings
    engine_args = {
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,
        "pool_recycle": 3600,
    }
    connect_args = {
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }

engine = create_engine(
    DATABASE_URL,
    connect_args=connect_args,
    **engine_args
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

@lru_cache(maxsize=1)
def get_cipher() -> Fernet:
    """
    Get encryption cipher with caching.
    """
    encryption_key = os.getenv("SESSION_SECRET")
    if not encryption_key:
        logger.warning("SESSION_SECRET not found, using insecure default for development only!")
        encryption_key = "default_local_development_secret_key_not_secure_change_this"
    
    # Ensure key is 32 bytes base64 encoded
    try:
        key = base64.urlsafe_b64encode(encryption_key.encode()[:32].ljust(32, b'0'))
        return Fernet(key)
    except Exception as e:
        logger.error(f"Error creating cipher: {e}")
        raise

class TimestampMixin:
    """Mixin class for created_at and updated_at timestamps"""
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), 
                       onupdate=lambda: datetime.now(timezone.utc), nullable=False)

class APICredentials(Base, TimestampMixin):
    """API credentials with encryption - supports both demo and real accounts"""
    __tablename__ = "api_credentials"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Demo account credentials
    demo_api_key_encrypted = Column(Text, nullable=True)
    demo_api_secret_encrypted = Column(Text, nullable=True)
    demo_passphrase_encrypted = Column(Text, nullable=True)
    
    # Real account credentials
    real_api_key_encrypted = Column(Text, nullable=True)
    real_api_secret_encrypted = Column(Text, nullable=True)
    real_passphrase_encrypted = Column(Text, nullable=True)
    
    # Legacy fields for backward compatibility
    api_key_encrypted = Column(Text, nullable=True)
    api_secret_encrypted = Column(Text, nullable=True)
    passphrase_encrypted = Column(Text, nullable=True)
    
    is_demo = Column(Boolean, default=True, nullable=False)
    
    def set_credentials(self, api_key: str, api_secret: str, passphrase: str, is_demo: bool = True) -> None:
        """Set encrypted credentials for demo or real account"""
        cipher = get_cipher()
        
        encrypted_key = cipher.encrypt(api_key.encode()).decode()
        encrypted_secret = cipher.encrypt(api_secret.encode()).decode()
        encrypted_pass = cipher.encrypt(passphrase.encode()).decode()
        
        if is_demo:
            self.demo_api_key_encrypted = encrypted_key
            self.demo_api_secret_encrypted = encrypted_secret
            self.demo_passphrase_encrypted = encrypted_pass
        else:
            self.real_api_key_encrypted = encrypted_key
            self.real_api_secret_encrypted = encrypted_secret
            self.real_passphrase_encrypted = encrypted_pass
        
        # Update legacy fields
        self.api_key_encrypted = encrypted_key
        self.api_secret_encrypted = encrypted_secret
        self.passphrase_encrypted = encrypted_pass
    
    def get_credentials(self, is_demo: bool = None) -> Tuple[str, str, str]:
        """Get decrypted credentials for demo or real account"""
        cipher = get_cipher()
        
        if is_demo is None:
            is_demo = self.is_demo
        
        try:
            if is_demo:
                if self.demo_api_key_encrypted:
                    return (
                        cipher.decrypt(self.demo_api_key_encrypted.encode()).decode(),
                        cipher.decrypt(self.demo_api_secret_encrypted.encode()).decode(),
                        cipher.decrypt(self.demo_passphrase_encrypted.encode()).decode()
                    )
            else:
                if self.real_api_key_encrypted:
                    return (
                        cipher.decrypt(self.real_api_key_encrypted.encode()).decode(),
                        cipher.decrypt(self.real_api_secret_encrypted.encode()).decode(),
                        cipher.decrypt(self.real_passphrase_encrypted.encode()).decode()
                    )
        except Exception as e:
            logger.error(f"Error decrypting credentials: {e}")
        
        # Fallback to legacy fields
        try:
            return (
                cipher.decrypt(self.api_key_encrypted.encode()).decode(),
                cipher.decrypt(self.api_secret_encrypted.encode()).decode(),
                cipher.decrypt(self.passphrase_encrypted.encode()).decode()
            )
        except Exception as e:
            logger.error(f"Error decrypting legacy credentials: {e}")
            return "", "", ""

class Position(Base, TimestampMixin):
    """Trading position model with optimized indexes"""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    side = Column(String(10), nullable=False, index=True)
    amount_usdt = Column(Float, nullable=False)
    leverage = Column(Integer, nullable=False)
    tp_usdt = Column(Float, nullable=False)
    sl_usdt = Column(Float, nullable=False)
    original_tp_usdt = Column(Float, nullable=True)
    original_sl_usdt = Column(Float, nullable=True)
    entry_price = Column(Float)
    quantity = Column(Float)
    order_id = Column(String(50))
    position_id = Column(String(50), index=True)
    position_side = Column(String(10))
    tp_order_id = Column(String(50), nullable=True)
    sl_order_id = Column(String(50), nullable=True)
    is_open = Column(Boolean, default=True, nullable=False, index=True)
    opened_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    closed_at = Column(DateTime, nullable=True)
    pnl = Column(Float, nullable=True)
    close_reason = Column(String(20), nullable=True)
    parent_position_id = Column(Integer, ForeignKey('positions.id'), nullable=True)
    recovery_count = Column(Integer, default=0, nullable=False)
    last_recovery_at = Column(DateTime, nullable=True)
    orders_disabled = Column(Boolean, default=False, nullable=False)
    
    __table_args__ = (
        Index('idx_symbol_is_open', 'symbol', 'is_open'),
        Index('idx_position_id_side', 'position_id', 'position_side'),
        Index('idx_opened_at_desc', 'opened_at'),
    )
    
    def __repr__(self) -> str:
        return f"<Position {self.symbol} {self.side} ${self.amount_usdt}>"

class PositionHistory(Base, TimestampMixin):
    """OKX position history with optimized structure"""
    __tablename__ = "position_history"
    
    id = Column(Integer, primary_key=True, index=True)
    inst_id = Column(String(30), nullable=False, index=True)
    pos_id = Column(String(50), nullable=False, index=True)
    mgn_mode = Column(String(20))
    pos_side = Column(String(10))
    open_avg_px = Column(Float)
    close_avg_px = Column(Float)
    open_max_pos = Column(Float)
    close_total_pos = Column(Float)
    pnl = Column(Float)
    pnl_ratio = Column(Float)
    leverage = Column(Integer)
    close_type = Column(String(20))
    c_time = Column(DateTime, index=True)
    u_time = Column(DateTime)
    
    __table_args__ = (
        Index('idx_pos_id_ctime', 'pos_id', 'c_time'),
        Index('idx_inst_id_utime', 'inst_id', 'u_time'),
    )
    
    def __repr__(self) -> str:
        return f"<PositionHistory {self.inst_id} {self.pos_side} PnL: ${self.pnl}>"

class Settings(Base, TimestampMixin):
    """Application settings with optimized key lookup"""
    __tablename__ = "settings"
    
    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), nullable=False, unique=True, index=True)
    value = Column(Text, nullable=False)
    
    def __repr__(self) -> str:
        return f"<Settings {self.key}={self.value}>"

def init_db() -> None:
    """Initialize database with all tables"""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise

def get_db() -> Generator[Session, None, None]:
    """Get database session (for FastAPI/Dependency Injection compatibility)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
