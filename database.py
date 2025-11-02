import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from cryptography.fernet import Fernet
import base64

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is required")

engine = create_engine(
    DATABASE_URL,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=3600,
    connect_args={
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

_cipher = None

def get_cipher():
    global _cipher
    if _cipher is None:
        encryption_key = os.getenv("SESSION_SECRET")
        if not encryption_key:
            raise ValueError("SESSION_SECRET environment variable is required for API key encryption")
        key = base64.urlsafe_b64encode(encryption_key.encode()[:32].ljust(32, b'0'))
        _cipher = Fernet(key)
    return _cipher

class APICredentials(Base):
    __tablename__ = "api_credentials"
    
    id = Column(Integer, primary_key=True, index=True)
    api_key_encrypted = Column(Text, nullable=False)
    api_secret_encrypted = Column(Text, nullable=False)
    passphrase_encrypted = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def set_credentials(self, api_key: str, api_secret: str, passphrase: str):
        cipher = get_cipher()
        self.api_key_encrypted = cipher.encrypt(api_key.encode()).decode()
        self.api_secret_encrypted = cipher.encrypt(api_secret.encode()).decode()
        self.passphrase_encrypted = cipher.encrypt(passphrase.encode()).decode()
    
    def get_credentials(self) -> tuple:
        cipher = get_cipher()
        api_key = cipher.decrypt(self.api_key_encrypted.encode()).decode()
        api_secret = cipher.decrypt(self.api_secret_encrypted.encode()).decode()
        passphrase = cipher.decrypt(self.passphrase_encrypted.encode()).decode()
        return api_key, api_secret, passphrase

class Position(Base):
    __tablename__ = "positions"
    
    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    amount_usdt = Column(Float, nullable=False)
    leverage = Column(Integer, nullable=False)
    tp_usdt = Column(Float, nullable=False)
    sl_usdt = Column(Float, nullable=False)
    entry_price = Column(Float)
    quantity = Column(Float)
    order_id = Column(String)
    position_id = Column(String)
    position_side = Column(String)
    tp_order_id = Column(String, nullable=True)
    sl_order_id = Column(String, nullable=True)
    is_open = Column(Boolean, default=True)
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    pnl = Column(Float, nullable=True)
    close_reason = Column(String, nullable=True)
    reopen_count = Column(Integer, default=0)
    parent_position_id = Column(Integer, nullable=True)
    
    def __repr__(self):
        return f"<Position {self.symbol} {self.side} ${self.amount_usdt}>"

def init_db():
    Base.metadata.create_all(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
