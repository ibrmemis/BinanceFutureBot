import os
from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, Index, ForeignKey
from sqlalchemy.orm import declarative_base, sessionmaker
from cryptography.fernet import Fernet
import base64
from functools import lru_cache

# Database URL'i environment variable'dan al, yoksa PostgreSQL default kullan
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Local development için PostgreSQL bağlantısı
    DATABASE_URL = "postgresql://postgres:Deneme11@localhost:5432/trading_bot"
    print("⚠️  DATABASE_URL environment variable bulunamadı, PostgreSQL default kullanılıyor:", DATABASE_URL)

# Optimized engine configuration for PostgreSQL
engine = create_engine(
    DATABASE_URL,
    pool_size=10,  # Connection pool size
    max_overflow=20,  # Max overflow connections
    pool_pre_ping=True,  # Validate connections before use
    pool_recycle=3600,  # Recycle connections every hour
    connect_args={
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    } if DATABASE_URL.startswith("postgresql") else {"check_same_thread": False},
    echo=False  # Set to True for SQL debugging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


@lru_cache(maxsize=1)
def get_cipher() -> Fernet:
    """
    Get encryption cipher with caching.
    Uses functools.lru_cache instead of global variable.
    """
    encryption_key = os.getenv("SESSION_SECRET")
    if not encryption_key:
        # Local development için default secret (güvenli değil, sadece test için)
        encryption_key = "default_local_development_secret_key_not_secure_change_this"
        print("⚠️  SESSION_SECRET environment variable bulunamadı, default kullanılıyor")
    
    key = base64.urlsafe_b64encode(encryption_key.encode()[:32].ljust(32, b'0'))
    return Fernet(key)


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
        
        if is_demo:
            self.demo_api_key_encrypted = cipher.encrypt(api_key.encode()).decode()
            self.demo_api_secret_encrypted = cipher.encrypt(api_secret.encode()).decode()
            self.demo_passphrase_encrypted = cipher.encrypt(passphrase.encode()).decode()
        else:
            self.real_api_key_encrypted = cipher.encrypt(api_key.encode()).decode()
            self.real_api_secret_encrypted = cipher.encrypt(api_secret.encode()).decode()
            self.real_passphrase_encrypted = cipher.encrypt(passphrase.encode()).decode()
        
        # Also update legacy fields for backward compatibility
        self.api_key_encrypted = cipher.encrypt(api_key.encode()).decode()
        self.api_secret_encrypted = cipher.encrypt(api_secret.encode()).decode()
        self.passphrase_encrypted = cipher.encrypt(passphrase.encode()).decode()
    
    def get_credentials(self, is_demo: bool = None) -> Tuple[str, str, str]:
        """Get decrypted credentials for demo or real account"""
        cipher = get_cipher()
        
        # If is_demo not specified, use current mode
        if is_demo is None:
            is_demo = self.is_demo
        
        try:
            if is_demo:
                # Try to get demo credentials
                if self.demo_api_key_encrypted:
                    api_key = cipher.decrypt(self.demo_api_key_encrypted.encode()).decode()
                    api_secret = cipher.decrypt(self.demo_api_secret_encrypted.encode()).decode()
                    passphrase = cipher.decrypt(self.demo_passphrase_encrypted.encode()).decode()
                    return api_key, api_secret, passphrase
            else:
                # Try to get real credentials
                if self.real_api_key_encrypted:
                    api_key = cipher.decrypt(self.real_api_key_encrypted.encode()).decode()
                    api_secret = cipher.decrypt(self.real_api_secret_encrypted.encode()).decode()
                    passphrase = cipher.decrypt(self.real_passphrase_encrypted.encode()).decode()
                    return api_key, api_secret, passphrase
        except:
            pass
        
        # Fallback to legacy fields
        api_key = cipher.decrypt(self.api_key_encrypted.encode()).decode()
        api_secret = cipher.decrypt(self.api_secret_encrypted.encode()).decode()
        passphrase = cipher.decrypt(self.passphrase_encrypted.encode()).decode()
        return api_key, api_secret, passphrase


class Position(Base, TimestampMixin):
    """Trading position model with optimized indexes"""
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), nullable=False, index=True)  # Added length and index
    side = Column(String(10), nullable=False, index=True)  # Added length and index
    amount_usdt = Column(Float, nullable=False)
    leverage = Column(Integer, nullable=False)
    tp_usdt = Column(Float, nullable=False)
    sl_usdt = Column(Float, nullable=False)
    original_tp_usdt = Column(Float, nullable=True)
    original_sl_usdt = Column(Float, nullable=True)
    entry_price = Column(Float)
    quantity = Column(Float)
    order_id = Column(String(50))  # Added length
    position_id = Column(String(50), index=True)  # Added length and index
    position_side = Column(String(10))  # Added length
    tp_order_id = Column(String(50), nullable=True)  # Added length
    sl_order_id = Column(String(50), nullable=True)  # Added length
    is_open = Column(Boolean, default=True, nullable=False, index=True)  # Added index
    opened_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    closed_at = Column(DateTime, nullable=True)
    pnl = Column(Float, nullable=True)
    close_reason = Column(String(20), nullable=True)  # Added length
    parent_position_id = Column(Integer, ForeignKey('positions.id'), nullable=True)  # Added FK
    recovery_count = Column(Integer, default=0, nullable=False)
    last_recovery_at = Column(DateTime, nullable=True)
    orders_disabled = Column(Boolean, default=False, nullable=False)  # Disable TP/SL order restoration until bot restart
    
    # Composite indexes for common queries
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
    inst_id = Column(String(30), nullable=False, index=True)  # Added length and index
    pos_id = Column(String(50), nullable=False, index=True)  # Added length and index
    mgn_mode = Column(String(20))  # Added length
    pos_side = Column(String(10))  # Added length
    open_avg_px = Column(Float)
    close_avg_px = Column(Float)
    open_max_pos = Column(Float)
    close_total_pos = Column(Float)
    pnl = Column(Float)
    pnl_ratio = Column(Float)
    leverage = Column(Integer)
    close_type = Column(String(20))  # Added length
    c_time = Column(DateTime, index=True)
    u_time = Column(DateTime)
    
    # Composite index for uniqueness and common queries
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
    key = Column(String(100), nullable=False, unique=True, index=True)  # Added length
    value = Column(Text, nullable=False)  # Changed to Text for longer values
    
    def __repr__(self) -> str:
        return f"<Settings {self.key}={self.value}>"


def init_db() -> None:
    """Initialize database with all tables"""
    Base.metadata.create_all(bind=engine)


def get_db() -> SessionLocal:
    """Get database session (for FastAPI compatibility)"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
