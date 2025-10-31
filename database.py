import os
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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
