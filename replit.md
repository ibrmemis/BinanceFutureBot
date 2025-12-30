# OKX Futures Trading Bot (Demo Trading)

## Overview

This is an automated cryptocurrency futures trading bot designed for OKX Demo Trading platform. The application provides a web interface built with Streamlit for monitoring and controlling automated trading positions on OKX perpetual futures (SWAP). The bot implements a custom trading strategy (Try1Strategy) that automatically opens, monitors, and manages futures positions on SOL-USDT-SWAP, BTC-USDT-SWAP, and ETH-USDT-SWAP pairs with configurable take-profit and stop-loss levels in USDT (PnL). It includes background monitoring for position updates every 1 minute and automatic position reopening capabilities after 5 minutes of closure.

**Migration Note**: Originally built for Binance Testnet, the system was migrated to OKX due to geographic restrictions on Binance testnet affecting Replit servers. OKX Demo Trading offers unrestricted global access and similar testing capabilities.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Framework**: Streamlit web application
- **Purpose**: Provides a user-friendly dashboard for monitoring trading positions and bot status
- **Key Features**: 
  - Wide layout configuration
  - Real-time position tracking with live OKX API data
  - **USDT Asset Dashboard**: Active Positions page displays real-time USDT account metrics (equity, available balance, floating PnL, margin used)
  - API key validation with passphrase support
  - Manual order management (create, edit, cancel TP/SL orders)
  - Five main tabs: New Trade, Active Positions, Orders, History, Settings
  - **OKX Position History Integration**: History tab shows complete trading history synced from OKX API with manual sync button
- **Rationale**: Streamlit was chosen for its simplicity in creating data-driven dashboards without complex frontend development, making it ideal for rapid prototyping and deployment of trading interfaces

### Backend Architecture
- **Language**: Python
- **Core Components**:
  - **OKXTestnetClient**: Wrapper around python-okx library for interacting with OKX V5 API with demo trading flag
  - **Try1Strategy**: Trading strategy implementation that manages position entry/exit logic with take-profit and stop-loss monitoring
  - **PositionMonitor**: Background scheduler that periodically checks positions every 1 minute, handles automatic reopening of closed positions after configurable delay, and monitors for recovery triggers
  - **Recovery System**: Automatic position recovery when PNL drops below threshold - cancels existing orders, adds to position, recalculates TP/SL
  - **Database Layer**: SQLAlchemy ORM for persistence

- **Design Pattern**: Separation of concerns with distinct modules for API communication, trading logic, database operations, and background tasks
- **Rationale**: Modular architecture allows independent testing and modification of trading strategies, API clients, and monitoring logic

### Data Storage
- **Technology**: PostgreSQL (via DATABASE_URL environment variable)
- **ORM**: SQLAlchemy
- **Key Tables**:
  - `api_credentials`: Stores encrypted OKX API keys, secrets, and passphrases
  - `positions`: Tracks **ALL positions** (manual and auto-reopened)
    - **Position ID Tracking**: Each position stores OKX's unique `posId` field in the `position_id` column
    - **Position Identification**: Positions are tracked by their unique OKX `posId`, not by order/trade IDs
    - **Open/Closed Status**: Position status is determined by checking if the `posId` exists in OKX and has non-zero position amount
    - **Infinite Reopen**: When a position closes, the SAME database record is updated and reopened (no new record created)
    - **parent_position_id**: Field exists for historical data but no longer used (positions update in place)
    - **recovery_count**: Tracks how many times recovery was triggered for this position
    - **last_recovery_at**: Timestamp of the last recovery execution

- **Database vs OKX**:
  - **New Trade Page**: Shows positions from database (all positions)
  - **Active Positions Page**: Shows ALL positions from OKX in real-time
  - **Auto-reopened positions**: SAME database record is updated with new OKX position data
  - **Manual positions**: Created as new database records when user opens a trade

- **Security**: API credentials are encrypted using Fernet (symmetric encryption) with a key derived from SESSION_SECRET environment variable
- **Rationale**: 
  - PostgreSQL provides ACID compliance and reliability for financial data
  - Encryption ensures API keys are never stored in plaintext
  - SQLAlchemy abstracts database operations and enables easy migration to other databases if needed
  - Using OKX's `posId` ensures accurate position tracking even when positions are reopened or modified
  - Storing only manual positions keeps database clean and prevents duplicate tracking

### Authentication & Authorization
- **API Key Management**: Dual-source credential loading (environment variables take precedence over database)
- **Encryption**: Cryptography library (Fernet) for symmetric encryption of sensitive credentials
- **Security Approach**: 
  - API keys loaded from OKX_DEMO_API_KEY, OKX_DEMO_API_SECRET, and OKX_DEMO_PASSPHRASE environment variables
  - Fallback to encrypted database storage if environment variables not set
  - SESSION_SECRET environment variable required for encryption/decryption operations
- **OKX Authentication**: Requires 3 parameters (API key, secret, passphrase) compared to Binance's 2-parameter authentication
- **Rationale**: Environment variables provide secure, deployment-friendly credential management while database storage offers a fallback option with encryption for security

### Background Processing
- **Technology**: APScheduler (BackgroundScheduler)
- **Purpose**: Continuously monitor open positions and handle automatic position reopening
- **Implementation**: Singleton pattern via `get_monitor()` function ensures single scheduler instance
- **Manual Start Required**: Bot does NOT auto-start on program restart - user must click "▶️ Botu Başlat" button
- **Key Features**:
  - Periodic position checks and updates every 1 minute
  - Tracking of recently closed positions (10-minute window)
  - **UNLIMITED automatic reopening**: Closed positions reopen infinitely after configurable delay (default 5 min)
  - **Configurable Auto-Reopen Delay**: User can set 1-60 minutes delay via Settings page
  - **Retry on Failure**: Failed reopen attempts stay in queue and retry every 30 seconds until success
  - Start/Stop controls via Settings page or sidebar
  - `manually_stopped` flag persists stop state across function calls
- **Infinite Auto-Reopen Mechanism** (Updated Nov 2025):
  - **NO LIMIT**: Positions reopen infinitely - each closure triggers a new reopen after configured delay
  - **UPDATE In-Place**: Closed positions are UPDATED (not new records) - same DB ID, refreshed with new OKX data
  - **Single Record Per Position**: Each manual trade creates ONE database record that gets reused infinitely
  - **OKX Position ID Updated**: After each reopen, the OKX `posId` field updates to new position ID
  - **Retry Logic**: API/network failures keep position in reopen queue, retry every 30 sec until success
  - **User Requested**: Explicitly requested unlimited reopen with UPDATE instead of INSERT
- **Rationale**: Background scheduling decouples monitoring from user interaction, enabling autonomous operation while the Streamlit interface remains responsive. Manual start prevents unwanted background activity on deployment restarts. Infinite reopen enables continuous trading without manual intervention.

### Recovery System (Added Dec 2025)
- **Purpose**: Automatically recover losing positions by adding to them and recalculating TP/SL
- **Trigger**: When a position's unrealized PNL drops below configurable threshold (default -50 USDT)
- **Recovery Process**:
  1. Cancel all existing TP/SL orders for the position
  2. Add to the position with configurable amount (default 100 USDT)
  3. Calculate new TP/SL prices based on the updated total position size
  4. Place new TP/SL orders
  5. Update database with new position details and increment recovery_count
- **Configurable Settings** (via Settings page):
  - `recovery_enabled`: Enable/disable the feature
  - `recovery_trigger_pnl`: PNL threshold that triggers recovery (default -50 USDT)
  - `recovery_add_amount`: Amount to add when recovery triggers (default 100 USDT)
  - `recovery_tp_usdt`: New TP target after recovery (default 50 USDT)
  - `recovery_sl_usdt`: New SL limit after recovery (default 100 USDT)
- **Safety Features**:
  - Validates position exists on OKX before proceeding
  - Prevents duplicate triggers with `positions_in_recovery` set
  - Clears recovery set on exception to allow retries
  - Tracks recovery count per position for monitoring
- **Scheduler Job**: Runs every 15 seconds to check for positions needing recovery

## External Dependencies

### Third-Party Services
- **OKX Demo Trading**: Primary trading platform
  - API URL: https://www.okx.com/api/v5
  - Demo Trading Flag: x-simulated-trading: 1 (header)
  - Purpose: Execute futures trades in a risk-free simulated environment
  - Authentication: API key, secret, and passphrase (3-parameter authentication)
  - Key Features Used: Long/short position mode, leverage configuration (cross margin via tdMode), market orders, position tracking
  - Instrument Format: Perpetual futures use format "BTC-USDT-SWAP" (not "BTCUSDT")
  - **Geographic Access**: No restrictions - global access including from Replit servers

### Libraries & Frameworks
- **streamlit**: Web application framework for the user interface
- **python-okx**: OKX API client library for cryptocurrency exchange operations (V5 API)
- **SQLAlchemy**: ORM for database abstraction and operations
- **APScheduler**: Background job scheduling for position monitoring
- **pandas**: Data manipulation for displaying position data in tables
- **cryptography (Fernet)**: Symmetric encryption for API credential security

### Database
- **PostgreSQL**: Relational database for persistent storage
- **Connection**: Via DATABASE_URL environment variable
- **Purpose**: Store trading positions history and encrypted API credentials

### Environment Variables Required
- `DATABASE_URL`: PostgreSQL connection string
- `OKX_DEMO_API_KEY`: OKX Demo Trading API key (optional if stored in database)
- `OKX_DEMO_API_SECRET`: OKX Demo Trading API secret (optional if stored in database)
- `OKX_DEMO_PASSPHRASE`: OKX Demo Trading API passphrase (optional if stored in database)
- `SESSION_SECRET`: Encryption key for securing stored API credentials

## Trading Strategy Details

### Try1 Strategy Configuration
- **Supported Pairs**: SOL-USDT-SWAP, BTC-USDT-SWAP, ETH-USDT-SWAP
- **Position Mode**: Long/Short mode (separate long and short positions)
- **Margin Type**: Cross margin (tdMode="cross")
- **Order Type**: Market orders for entry
- **Position Value & Margin Calculation**:
  - User inputs **Position Value** (total position size in USDT)
  - Example: 1000 USDT position with 10x leverage
  - Margin used: `position_value / leverage` = 1000 / 10 = **100 USDT**
  - Contracts: `int(position_value / current_price)` = 1000 / 187 ≈ **5 contracts**
  - UI displays calculated margin automatically
- **TP/SL Implementation**: 
  - Automatic TP/SL algo orders placed immediately after market order execution
  - TP/SL calculated from USDT PnL targets: `price = entry ± (pnl_usdt / quantity)`
  - Uses OKX trigger algo orders (ordType="trigger")
  - TP/SL order IDs stored in database for tracking
- **Position Tracking**: 
  - Each position is identified by OKX's unique `posId` (retrieved after market order execution)
  - `posId` is stored in database `position_id` column for precise tracking
  - Position open/closed status determined by matching `posId` and checking position amount
  - Real-time unrealized PnL monitoring and position status updates
  - 2-second delay after order placement to ensure `posId` is available from OKX API
- **Auto-Reopen**: Positions automatically reopen 5 minutes after closure with identical parameters

## Migration from Binance to OKX

### Reasons for Migration
1. **Geographic Restrictions**: Binance testnet blocked access from Replit server locations
2. **Better Global Access**: OKX Demo Trading has no geographic restrictions
3. **Stable API**: OKX V5 API is well-documented and reliable
4. **Similar Functionality**: Both support perpetual futures, leverage, and demo/testnet trading

### Key Changes Made
1. **API Client**: Replaced `python-binance` with `python-okx`
2. **Authentication**: Added passphrase (third authentication parameter)
3. **Instrument Format**: Changed from "BTCUSDT" to "BTC-USDT-SWAP"
4. **Position Mode**: Changed from hedge mode to long/short mode
5. **Margin Configuration**: Integrated into order placement (tdMode parameter) instead of separate API call
6. **TP/SL Mechanism**: Implemented automatic TP/SL algo orders using OKX conditional orders API
7. **Database Schema**: 
   - Added passphrase_encrypted column to api_credentials table
   - TP/SL order IDs (tp_order_id, sl_order_id) stored for tracking
8. **Environment Variables**: Renamed from BINANCE_TESTNET_* to OKX_DEMO_*

### Technical Differences
- **OKX Position Sides**: "long" and "short" (lowercase) vs Binance's "LONG" and "SHORT"
- **OKX Contract Size**: Integer contract count vs Binance's decimal quantities
- **Order Response**: Different JSON structure requiring adapter layer
- **Demo Flag**: OKX uses header flag instead of different endpoint URL
