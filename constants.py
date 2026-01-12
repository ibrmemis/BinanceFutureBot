"""
Application constants and enums for better type safety and maintainability
"""
from enum import Enum, StrEnum
from typing import Final


class OrderSide(StrEnum):
    """Order side enumeration"""
    LONG = "LONG"
    SHORT = "SHORT"
    BUY = "buy"
    SELL = "sell"


class PositionSide(StrEnum):
    """Position side enumeration"""
    LONG = "long"
    SHORT = "short"


class OrderType(StrEnum):
    """Order type enumeration"""
    MARKET = "market"
    LIMIT = "limit"
    TRIGGER = "trigger"
    CONDITIONAL = "conditional"
    ICEBERG = "iceberg"
    TWAP = "twap"


class CloseReason(StrEnum):
    """Position close reason enumeration"""
    TP = "TP"  # Take Profit
    SL = "SL"  # Stop Loss
    MANUAL = "MANUAL"
    LIQUIDATION = "LIQUIDATION"


class TradingMode(StrEnum):
    """Trading mode enumeration"""
    CROSS = "cross"
    ISOLATED = "isolated"


class AccountType(StrEnum):
    """Account type enumeration"""
    DEMO = "Demo Hesap (Simüle)"
    REAL = "Gerçek Hesap (Live)"


# UI Constants
class UIConstants:
    """UI related constants"""
    
    # Page titles and icons
    PAGE_TITLE: Final = "OKX Futures Trading Bot (Demo)"
    PAGE_ICON: Final = "📈"
    
    # Tab names
    TAB_NEW_TRADE: Final = "🎯 Yeni İşlem"
    TAB_ACTIVE_POSITIONS: Final = "📊 Aktif Pozisyonlar"
    TAB_ORDERS: Final = "📋 Emirler"
    TAB_HISTORY: Final = "📈 Geçmiş İşlemler"
    TAB_SETTINGS: Final = "⚙️ Ayarlar"
    TAB_DATABASE: Final = "💾 Database"
    
    # Button texts
    BTN_START_BOT: Final = "▶️ Botu Başlat"
    BTN_STOP_BOT: Final = "⏹️ Botu Durdur"
    BTN_OPEN_POSITION: Final = "🚀 Pozisyon Aç"
    BTN_SAVE: Final = "💾 Kaydet"
    BTN_DELETE: Final = "🗑️ Sil"
    BTN_REFRESH: Final = "🔄 Yenile"
    
    # Status indicators
    STATUS_RUNNING: Final = "✅ Bot Çalışıyor"
    STATUS_STOPPED: Final = "⏸️ Bot Durdu"
    STATUS_OPEN: Final = "🟢 AÇIK"
    STATUS_CLOSED: Final = "⚫ KAPALI"
    
    # Direction indicators
    DIRECTION_LONG: Final = "🟢 LONG"
    DIRECTION_SHORT: Final = "🔴 SHORT"


# API Constants
class APIConstants:
    """API related constants"""
    
    # OKX API endpoints
    OKX_FLAG_DEMO: Final = "1"
    OKX_FLAG_LIVE: Final = "0"
    
    # Instrument types
    INST_TYPE_SWAP: Final = "SWAP"
    INST_TYPE_FUTURES: Final = "FUTURES"
    INST_TYPE_SPOT: Final = "SPOT"
    
    # Default values
    DEFAULT_LEVERAGE: Final = 20
    DEFAULT_POSITION_SIZE: Final = 1111.0
    DEFAULT_TP_USDT: Final = 8.0
    DEFAULT_SL_USDT: Final = 500.0
    
    # Limits
    MAX_LEVERAGE: Final = 125
    MIN_LEVERAGE: Final = 1
    MIN_POSITION_SIZE: Final = 1.0
    MAX_POSITION_SIZE: Final = 50000.0


# Database Constants
class DatabaseConstants:
    """Database related constants"""
    
    # Table names
    TABLE_POSITIONS: Final = "positions"
    TABLE_API_CREDENTIALS: Final = "api_credentials"
    TABLE_SETTINGS: Final = "settings"
    TABLE_POSITION_HISTORY: Final = "position_history"
    
    # Setting keys
    SETTING_AUTO_REOPEN_DELAY: Final = "auto_reopen_delay_minutes"
    SETTING_RECOVERY_ENABLED: Final = "recovery_enabled"
    SETTING_RECOVERY_TP_USDT: Final = "recovery_tp_usdt"
    SETTING_RECOVERY_SL_USDT: Final = "recovery_sl_usdt"
    
    # Recovery step keys (1-5)
    RECOVERY_STEP_TRIGGER: Final = "recovery_step_{}_trigger"
    RECOVERY_STEP_ADD: Final = "recovery_step_{}_add"
    RECOVERY_STEP_TP: Final = "recovery_step_{}_tp"
    RECOVERY_STEP_SL: Final = "recovery_step_{}_sl"


# Trading Constants
class TradingConstants:
    """Trading related constants"""
    
    # Popular trading pairs
    POPULAR_SYMBOLS: Final = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    
    # Contract values (for calculation)
    CONTRACT_VALUES: Final = {
        "BTCUSDT": 0.01,
        "ETHUSDT": 0.1,
        "SOLUSDT": 1.0,
    }
    
    # Default lot sizes
    DEFAULT_LOT_SIZE: Final = 1.0
    
    # Price precision
    DEFAULT_TICK_SIZE: Final = "0.0001"
    
    # Timeouts and delays
    ORDER_DELAY_SECONDS: Final = 2
    TP_ORDER_DELAY_SECONDS: Final = 5
    POSITION_CHECK_GRACE_PERIOD: Final = 120  # seconds
    
    # Recovery settings
    MAX_RECOVERY_STEPS: Final = 5
    DEFAULT_RECOVERY_DELAY: Final = 1  # minutes


# Cache Constants
class CacheConstants:
    """Caching related constants"""
    
    # TTL values in seconds
    CLIENT_CACHE_TTL: Final = 300  # 5 minutes
    SYMBOLS_CACHE_TTL: Final = 60  # 1 minute
    POSITIONS_CACHE_TTL: Final = 30  # 30 seconds
    PRICE_CACHE_TTL: Final = 0  # No cache for live prices
    
    # Cache keys
    CACHE_KEY_CLIENT: Final = "okx_client"
    CACHE_KEY_SYMBOLS: Final = "swap_symbols"
    CACHE_KEY_POSITIONS: Final = "db_positions"


# Scheduler Constants
class SchedulerConstants:
    """Background scheduler constants"""
    
    # Job intervals in seconds
    POSITION_CHECK_INTERVAL: Final = 30
    ORDER_CLEANUP_INTERVAL: Final = 60
    POSITION_REOPEN_INTERVAL: Final = 30
    RECOVERY_CHECK_INTERVAL: Final = 15
    
    # Job settings
    MAX_WORKERS: Final = 3
    MISFIRE_GRACE_TIME: Final = 30
    COALESCE_JOBS: Final = True
    MAX_INSTANCES: Final = 1


# Environment Variables
class EnvVars:
    """Environment variable names"""
    
    DATABASE_URL: Final = "DATABASE_URL"
    SESSION_SECRET: Final = "SESSION_SECRET"
    
    # OKX API Keys
    OKX_DEMO_API_KEY: Final = "OKX_DEMO_API_KEY"
    OKX_DEMO_API_SECRET: Final = "OKX_DEMO_API_SECRET"
    OKX_DEMO_PASSPHRASE: Final = "OKX_DEMO_PASSPHRASE"
    
    # PostgreSQL
    PGHOST: Final = "PGHOST"
    PGPORT: Final = "PGPORT"
    PGDATABASE: Final = "PGDATABASE"
    PGUSER: Final = "PGUSER"
    PGPASSWORD: Final = "PGPASSWORD"


# Error Messages
class ErrorMessages:
    """Standardized error messages"""
    
    API_NOT_CONFIGURED: Final = "OKX API anahtarları yapılandırılmamış"
    DATABASE_CONNECTION_FAILED: Final = "Veritabanı bağlantısı başarısız"
    POSITION_NOT_FOUND: Final = "Pozisyon bulunamadı"
    INVALID_POSITION_SIZE: Final = "Geçersiz pozisyon büyüklüğü"
    ORDER_FAILED: Final = "Emir başarısız"
    PRICE_NOT_AVAILABLE: Final = "Fiyat bilgisi alınamadı"
    INSUFFICIENT_BALANCE: Final = "Yetersiz bakiye"
    POSITION_ALREADY_CLOSED: Final = "Pozisyon zaten kapalı"
    RECOVERY_FAILED: Final = "Kurtarma işlemi başarısız"


# Success Messages
class SuccessMessages:
    """Standardized success messages"""
    
    POSITION_OPENED: Final = "Pozisyon başarıyla açıldı"
    POSITION_CLOSED: Final = "Pozisyon başarıyla kapatıldı"
    ORDER_PLACED: Final = "Emir başarıyla yerleştirildi"
    ORDER_CANCELLED: Final = "Emir başarıyla iptal edildi"
    SETTINGS_SAVED: Final = "Ayarlar başarıyla kaydedildi"
    BOT_STARTED: Final = "Bot başarıyla başlatıldı"
    BOT_STOPPED: Final = "Bot başarıyla durduruldu"
    RECOVERY_COMPLETED: Final = "Kurtarma işlemi tamamlandı"