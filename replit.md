# Binance Futures Trading Bot (Testnet)

## Overview

This is an automated cryptocurrency futures trading bot designed for Binance Testnet (demo.binance.com). The application provides a web interface built with Streamlit for monitoring and controlling automated trading positions on Binance Futures. The bot implements a custom trading strategy (Try1Strategy) that automatically opens, monitors, and manages futures positions with configurable take-profit and stop-loss levels. It includes background monitoring for position updates and automatic position reopening capabilities.

## User Preferences

Preferred communication style: Simple, everyday language.

## System Architecture

### Frontend Architecture
- **Framework**: Streamlit web application
- **Purpose**: Provides a user-friendly dashboard for monitoring trading positions and bot status
- **Key Features**: Wide layout configuration, real-time position tracking, API key validation
- **Rationale**: Streamlit was chosen for its simplicity in creating data-driven dashboards without complex frontend development, making it ideal for rapid prototyping and deployment of trading interfaces

### Backend Architecture
- **Language**: Python
- **Core Components**:
  - **BinanceTestnetClient**: Wrapper around python-binance library for interacting with Binance Futures Testnet API
  - **Try1Strategy**: Trading strategy implementation that manages position entry/exit logic with take-profit and stop-loss calculations
  - **PositionMonitor**: Background scheduler that periodically checks positions and handles automatic reopening of closed positions
  - **Database Layer**: SQLAlchemy ORM for persistence

- **Design Pattern**: Separation of concerns with distinct modules for API communication, trading logic, database operations, and background tasks
- **Rationale**: Modular architecture allows independent testing and modification of trading strategies, API clients, and monitoring logic

### Data Storage
- **Technology**: PostgreSQL (via DATABASE_URL environment variable)
- **ORM**: SQLAlchemy
- **Key Tables**:
  - `api_credentials`: Stores encrypted Binance API keys and secrets
  - `positions`: Tracks all trading positions (open/closed status, entry/exit prices, PnL, etc.)

- **Security**: API credentials are encrypted using Fernet (symmetric encryption) with a key derived from SESSION_SECRET environment variable
- **Rationale**: 
  - PostgreSQL provides ACID compliance and reliability for financial data
  - Encryption ensures API keys are never stored in plaintext
  - SQLAlchemy abstracts database operations and enables easy migration to other databases if needed

### Authentication & Authorization
- **API Key Management**: Dual-source credential loading (environment variables take precedence over database)
- **Encryption**: Cryptography library (Fernet) for symmetric encryption of sensitive credentials
- **Security Approach**: 
  - API keys loaded from BINANCE_TESTNET_API_KEY and BINANCE_TESTNET_API_SECRET environment variables
  - Fallback to encrypted database storage if environment variables not set
  - SESSION_SECRET environment variable required for encryption/decryption operations
- **Rationale**: Environment variables provide secure, deployment-friendly credential management while database storage offers a fallback option with encryption for security

### Background Processing
- **Technology**: APScheduler (BackgroundScheduler)
- **Purpose**: Continuously monitor open positions and handle automatic position reopening
- **Implementation**: Singleton pattern via `get_monitor()` function ensures single scheduler instance
- **Key Features**:
  - Periodic position checks and updates
  - Tracking of recently closed positions (10-minute window)
  - Automatic reopening logic for closed positions
- **Rationale**: Background scheduling decouples monitoring from user interaction, enabling autonomous operation while the Streamlit interface remains responsive

## External Dependencies

### Third-Party Services
- **Binance Futures Testnet**: Primary trading platform
  - API URL: https://testnet.binancefuture.com
  - Purpose: Execute futures trades in a risk-free testing environment
  - Authentication: API key and secret pair
  - Key Features Used: Hedge mode, leverage configuration, margin type settings, order placement

### Libraries & Frameworks
- **streamlit**: Web application framework for the user interface
- **python-binance**: Official Binance API client library for cryptocurrency exchange operations
- **SQLAlchemy**: ORM for database abstraction and operations
- **APScheduler**: Background job scheduling for position monitoring
- **pandas**: Data manipulation (likely for displaying position data in tables)
- **cryptography (Fernet)**: Symmetric encryption for API credential security

### Database
- **PostgreSQL**: Relational database for persistent storage
- **Connection**: Via DATABASE_URL environment variable
- **Purpose**: Store trading positions history and encrypted API credentials

### Environment Variables Required
- `DATABASE_URL`: PostgreSQL connection string
- `BINANCE_TESTNET_API_KEY`: Binance Testnet API key (optional if stored in database)
- `BINANCE_TESTNET_API_SECRET`: Binance Testnet API secret (optional if stored in database)
- `SESSION_SECRET`: Encryption key for securing stored API credentials