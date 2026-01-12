import streamlit as st
import os
from database import SessionLocal, APICredentials, Position
from database_utils import get_db_session
from okx_client import OKXTestnetClient
from constants import CacheConstants, EnvVars

@st.cache_resource(ttl=CacheConstants.CLIENT_CACHE_TTL)
def get_cached_client():
    return OKXTestnetClient()

@st.cache_data(ttl=CacheConstants.SYMBOLS_CACHE_TTL)
def get_cached_symbols():
    client = get_cached_client()
    return client.get_all_swap_symbols()

def get_cached_price(symbol: str):
    client = get_cached_client()
    return client.get_symbol_price(symbol)

@st.cache_data(ttl=CacheConstants.POSITIONS_CACHE_TTL)
def get_cached_positions():
    with get_db_session() as db:
        positions = db.query(Position).order_by(Position.opened_at.desc()).all()
        return [{'id': p.id, 'symbol': p.symbol, 'side': p.side, 'amount_usdt': p.amount_usdt,
                 'leverage': p.leverage, 'tp_usdt': p.tp_usdt, 'sl_usdt': p.sl_usdt,
                 'entry_price': p.entry_price, 'quantity': p.quantity, 'is_open': p.is_open,
                 'position_side': p.position_side, 'opened_at': p.opened_at, 'position_id': p.position_id,
                 'recovery_count': p.recovery_count} for p in positions]

def clear_position_cache():
    get_cached_positions.clear()

def check_api_keys():
    if all(os.getenv(var) for var in [EnvVars.OKX_DEMO_API_KEY, EnvVars.OKX_DEMO_API_SECRET, EnvVars.OKX_DEMO_PASSPHRASE]):
        return True
    with get_db_session() as db:
        return db.query(APICredentials).first() is not None
