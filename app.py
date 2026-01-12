import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from typing import cast
from database import init_db, SessionLocal, Position, APICredentials, Settings
from database_utils import get_db_session, DatabaseManager
from okx_client import OKXTestnetClient
from trading_strategy import Try1Strategy
from background_scheduler import get_monitor, stop_monitor, start_monitor
from constants import (
    UIConstants, APIConstants, DatabaseConstants, TradingConstants,
    CacheConstants, ErrorMessages, SuccessMessages, EnvVars
)
import os

st.set_page_config(
    page_title=UIConstants.PAGE_TITLE,
    page_icon=UIConstants.PAGE_ICON,
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Load custom CSS for compact UI
def load_css():
    try:
        with open('.streamlit/style.css') as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except FileNotFoundError:
        pass

load_css()

init_db()

monitor = get_monitor()

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

def main():
    if 'auto_reopen_delay_minutes' not in st.session_state:
        delay = DatabaseManager.get_setting(
            DatabaseConstants.SETTING_AUTO_REOPEN_DELAY,
            TradingConstants.DEFAULT_RECOVERY_DELAY
        )
        try:
            st.session_state.auto_reopen_delay_minutes = int(delay)
        except (ValueError, TypeError):
            st.session_state.auto_reopen_delay_minutes = TradingConstants.DEFAULT_RECOVERY_DELAY
            DatabaseManager.set_setting(DatabaseConstants.SETTING_AUTO_REOPEN_DELAY, str(TradingConstants.DEFAULT_RECOVERY_DELAY))
    
    with get_db_session() as db:
        creds_check = db.query(APICredentials).first()
        is_demo_mode = not creds_check or creds_check.is_demo
    
    if is_demo_mode:
        st.markdown("### 📈 OKX Futures Bot (Demo)")
    else:
        st.markdown("### 💰 OKX Futures Bot (GERÇEK)")
    
    with st.sidebar:
        st.markdown("#### 🔐 Hesap")
        
        db = SessionLocal()
        try:
            creds = db.query(APICredentials).first()
            current_mode = "demo" if (not creds or creds.is_demo) else "real"
        finally:
            db.close()
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🧪", type="primary" if current_mode == "demo" else "secondary", use_container_width=True, key="btn_demo", help="Demo Mode"):
                db = SessionLocal()
                try:
                    creds = db.query(APICredentials).first()
                    if creds:
                        creds.is_demo = True
                        db.commit()
                        st.rerun()
                finally:
                    db.close()
        with col2:
            if st.button("💰", type="primary" if current_mode == "real" else "secondary", use_container_width=True, key="btn_real", help="Real Mode"):
                db = SessionLocal()
                try:
                    creds = db.query(APICredentials).first()
                    if creds:
                        creds.is_demo = False
                        db.commit()
                        st.rerun()
                    else:
                        st.warning("API key gerekli")
                finally:
                    db.close()
        
        st.divider()
        st.markdown("#### 🤖 Bot")
        
        monitor = get_monitor()
        bot_running = monitor.is_running() if monitor else False
        
        if bot_running:
            st.success("✅ Çalışıyor")
            if st.button("⏹️ Durdur", type="primary", use_container_width=True, key="btn_stop_bot"):
                if stop_monitor():
                    st.rerun()
        else:
            st.error("⏸️ Durdu")
            if st.button("▶️ Başlat", type="primary", use_container_width=True, key="btn_start_bot"):
                reopen_delay = st.session_state.get('auto_reopen_delay_minutes', 3)
                if start_monitor(reopen_delay):
                    st.rerun()
    
    if not check_api_keys():
        st.error("⚠️ OKX API anahtarları yapılandırılmamış!")
        st.info("""
        **API Anahtarlarını Yapılandırma:**
        
        1. OKX hesabınıza giriş yapın: https://www.okx.com
        2. Trade → Demo Trading → Personal Center
        3. Demo Trading API → Create V5 API Key for Demo Trading
        4. API Key, Secret Key ve Passphrase'i oluşturun
        5. Aşağıdaki forma girin veya Replit Secrets'a ekleyin:
           - `OKX_DEMO_API_KEY`
           - `OKX_DEMO_API_SECRET`
           - `OKX_DEMO_PASSPHRASE`
        """)
        
        with st.expander("🔧 API Key Kaydetme (Veritabanı)"):
            st.info("API anahtarlarınız şifrelenmiş olarak veritabanına kaydedilecek.")
            api_key_input = st.text_input("API Key", type="password", key="api_key_input")
            api_secret_input = st.text_input("API Secret", type="password", key="api_secret_input")
            passphrase_input = st.text_input("Passphrase", type="password", key="passphrase_input")
            
            if st.button("Veritabanına Kaydet"):
                if api_key_input and api_secret_input and passphrase_input:
                    db = SessionLocal()
                    try:
                        creds = db.query(APICredentials).first()
                        if creds:
                            creds.set_credentials(api_key_input, api_secret_input, passphrase_input)
                        else:
                            creds = APICredentials()
                            creds.set_credentials(api_key_input, api_secret_input, passphrase_input)
                            db.add(creds)
                        db.commit()
                        st.success("✅ API anahtarları veritabanına kaydedildi! Sayfa yenileniyor...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Hata: {e}")
                    finally:
                        db.close()
                else:
                    st.warning("Lütfen tüm alanları doldurun.")
        return
    
    tabs = st.tabs([
        UIConstants.TAB_NEW_TRADE, 
        UIConstants.TAB_ACTIVE_POSITIONS, 
        UIConstants.TAB_ORDERS, 
        UIConstants.TAB_HISTORY, 
        UIConstants.TAB_SETTINGS, 
        UIConstants.TAB_DATABASE
    ])
    
    with tabs[0]:
        show_new_trade_page()
    
    with tabs[1]:
        show_active_positions_page()
    
    with tabs[2]:
        show_orders_page()
    
    with tabs[3]:
        show_history_page()
    
    with tabs[4]:
        show_settings_page()
    
    with tabs[5]:
        show_database_page()

def show_database_page():
    st.markdown("#### 💾 Database")
    
    db = SessionLocal()
    try:
        # Tables to display
        tables = {
            "Positions (Pozisyonlar)": Position,
            "API Credentials (API Bilgileri)": APICredentials,
            "Settings (Ayarlar)": Settings
        }
        
        selected_table_name = st.selectbox("Görüntülemek istediğiniz tabloyu seçin:", list(tables.keys()))
        model_class = tables[selected_table_name]
        
        # Query all records from the selected table
        records = db.query(model_class).all()
        
        if not records:
            st.info(f"{selected_table_name} tablosunda henüz veri bulunmuyor.")
        else:
            # Convert to list of dictionaries for DataFrame
            data = []
            for record in records:
                row = {}
                for column in record.__table__.columns:
                    val = getattr(record, column.name)
                    # Mask sensitive fields if it's the credentials table
                    if model_class == APICredentials and column.name in ['api_key_encrypted', 'api_secret_encrypted', 'passphrase_encrypted']:
                        row[column.name] = "******** (Şifreli)"
                    else:
                        row[column.name] = val
                data.append(row)
            
            df = pd.DataFrame(data)
            st.dataframe(df, width="stretch")
            
            st.write(f"Toplam Kayıt: **{len(records)}**")
            
            # Refresh button
            if st.button("🔄 Verileri Yenile"):
                st.rerun()
                
    except Exception as e:
        st.error(f"Veritabanı okuma hatası: {e}")
    finally:
        db.close()

def show_new_trade_page():
    st.markdown("#### 🎯 Yeni İşlem")
    
    client = get_cached_client()
    all_symbols = get_cached_symbols()
    
    popular_coins = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    other_coins = [s for s in all_symbols if s not in popular_coins]
    ordered_symbols = popular_coins + other_coins
    
    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            symbol = st.selectbox("Coin", ordered_symbols, help=f"{len(all_symbols)} çift mevcut")
            current_price = get_cached_price(symbol)
            if current_price:
                st.caption(f"Fiyat: **${current_price:,.2f}**")
        
        with col2:
            side = st.selectbox("Yön", ["LONG", "SHORT"])
            side_emoji = "🟢" if side == "LONG" else "🔴"
            st.caption(f"{side_emoji} {side}")
        
        with col3:
            leverage = st.number_input(
                "Kaldıraç", 
                min_value=APIConstants.MIN_LEVERAGE, 
                max_value=APIConstants.MAX_LEVERAGE, 
                value=APIConstants.DEFAULT_LEVERAGE, 
                step=1
            )
        
        col4, col5, col6 = st.columns(3)
        
        with col4:
            amount_usdt = st.number_input(
                "Pozisyon (USDT)", 
                min_value=APIConstants.MIN_POSITION_SIZE, 
                value=APIConstants.DEFAULT_POSITION_SIZE, 
                step=10.0
            )
        
        with col5:
            tp_usdt = st.number_input(
                "TP (USDT)", 
                min_value=0.1, 
                value=APIConstants.DEFAULT_TP_USDT, 
                step=1.0, 
                help="Kar hedefi"
            )
        
        with col6:
            sl_usdt = st.number_input(
                "SL (USDT)", 
                min_value=0.1, 
                value=APIConstants.DEFAULT_SL_USDT, 
                step=1.0, 
                help="Zarar limiti"
            )
        
        if current_price:
            contract_value = client.get_contract_value(symbol)
            contract_usdt_value = contract_value * current_price
            exact_contracts = amount_usdt / contract_usdt_value
            actual_contracts = max(0.01, round(exact_contracts, 2))
            actual_position_value = actual_contracts * contract_usdt_value
            margin_used = actual_position_value / leverage
            
            st.caption(f"Marjin: **${margin_used:.2f}** | Kontrat: **{actual_contracts}**")
        
        btn_col1, btn_col2 = st.columns([2, 1])
        
        with btn_col1:
            if st.button("🚀 Pozisyon Aç", type="primary", use_container_width=True):
                with st.spinner("Açılıyor..."):
                    strategy = Try1Strategy()
                    success, message, position_id = strategy.open_position(
                        symbol=symbol, side=side, amount_usdt=amount_usdt,
                        leverage=leverage, tp_usdt=tp_usdt, sl_usdt=sl_usdt
                    )
                    if success:
                        st.success(f"✅ {message}")
                        st.balloons()
                    else:
                        st.error(f"❌ {message}")
        
        with btn_col2:
            with st.popover("Diğer"):
                if st.button("💾 Sadece Kaydet", use_container_width=True, help="OKX'de açmadan kaydet"):
                    db = SessionLocal()
                    try:
                        if not current_price:
                            st.error("Fiyat alınamadı")
                        else:
                            position_side = "long" if side == "LONG" else "short"
                            position = Position(
                                symbol=symbol, side=side, amount_usdt=amount_usdt,
                                leverage=leverage, tp_usdt=tp_usdt, sl_usdt=sl_usdt,
                                entry_price=current_price, quantity=0.0, order_id=None,
                                position_id=None, position_side=position_side,
                                tp_order_id=None, sl_order_id=None, is_open=False, parent_position_id=None
                            )
                            db.add(position)
                            db.commit()
                            st.success(f"✅ Kaydedildi (ID: {position.id})")
                    except Exception as e:
                        db.rollback()
                        st.error(f"❌ Hata: {e}")
                    finally:
                        db.close()
    
    st.markdown("##### 📋 Pozisyonlar")
    
    client = get_cached_client()
    
    if not client.is_configured():
        st.warning("OKX API yapılandırılmamış.")
        return
    
    db = SessionLocal()
    try:
        all_positions = db.query(Position).order_by(Position.opened_at.desc()).all()
        
        if not all_positions:
            st.info("Şu anda strateji ile oluşturulmuş pozisyon bulunmuyor.")
        else:
            active_count = sum(1 for p in all_positions if p.is_open)
            closed_count = len(all_positions) - active_count
            st.success(f"Toplam {len(all_positions)} pozisyon: {active_count} açık, {closed_count} kapalı")
            
            table_data = []
            for pos in all_positions:
                position_side = pos.position_side if pos.position_side else ("long" if pos.side == "LONG" else "short")
                direction = "🔼 LONG" if pos.side == "LONG" else "🔽 SHORT"
                
                # DATABASE values (always show these)
                db_entry_price = pos.entry_price if pos.entry_price is not None else 0
                db_quantity = pos.quantity if pos.quantity is not None else 0
                db_leverage = pos.leverage if pos.leverage is not None else 1
                db_amount = pos.amount_usdt if pos.amount_usdt is not None else 0
                db_tp = pos.tp_usdt if pos.tp_usdt is not None else 0
                db_sl = pos.sl_usdt if pos.sl_usdt is not None else 0
                
                # Status and real-time data
                if pos.is_open:
                    status = "🟢 AÇIK"
                    
                    # Try to get real-time data from OKX
                    okx_pos = client.get_position(str(pos.symbol), position_side)
                    if okx_pos and float(okx_pos.get('positionAmt', 0)) != 0:
                        current_price = float(okx_pos.get('markPrice', 0))
                        unrealized_pnl = float(okx_pos.get('unrealizedProfit', 0))
                        pnl_display = f"{'🟢' if unrealized_pnl >= 0 else '🔴'} ${unrealized_pnl:.2f}"
                        current_price_display = f"${current_price:.4f}"
                    else:
                        current_price = client.get_symbol_price(str(pos.symbol)) or 0
                        pnl_display = "—"
                        current_price_display = f"${current_price:.4f}" if current_price > 0 else "—"
                else:
                    status = "⚫ KAPALI"
                    # For closed positions, current price is not meaningful
                    current_price_display = "—"
                    # Show final PnL from database
                    if pos.pnl is not None:
                        pnl_display = f"{'🟢' if pos.pnl >= 0 else '🔴'} ${pos.pnl:.2f}"
                    else:
                        pnl_display = "—"
                
                # Parent indicator (reopen chain)
                parent_badge = " 🔗" if pos.parent_position_id else ""
                
                table_data.append({
                    "ID": pos.id,
                    "Durum": status + parent_badge,
                    "Coin": pos.symbol,
                    "Yön": direction,
                    "Kaldıraç": f"{db_leverage}x",
                    "Değer (USDT)": f"${db_amount:.2f}",
                    "PnL": pnl_display,
                    "TP": f"${db_tp:.2f}",
                    "SL": f"${db_sl:.2f}",
                    "Açılış": pos.opened_at.strftime('%Y-%m-%d %H:%M')
                })
            
            df = pd.DataFrame(table_data)
            st.dataframe(
                df,
                width="stretch",
                hide_index=True,
                column_config={
                    "ID": st.column_config.NumberColumn("ID", width="small"),
                    "Durum": st.column_config.TextColumn("Durum", width="medium"),
                    "Coin": st.column_config.TextColumn("Coin", width="small"),
                    "Yön": st.column_config.TextColumn("Yön", width="small"),
                    "Kaldıraç": st.column_config.TextColumn("Kaldıraç", width="small"),
                    "Değer (USDT)": st.column_config.TextColumn("Değer (USDT)", width="small"),
                    "PnL": st.column_config.TextColumn("PnL", width="small"),
                    "TP": st.column_config.TextColumn("TP (USDT)", width="small"),
                    "SL": st.column_config.TextColumn("SL (USDT)", width="small"),
                    "Açılış": st.column_config.TextColumn("Açılış", width="medium")
                }
            )
            
            st.divider()
            st.markdown("##### 🎮 Kontrol")
            
            from background_scheduler import get_monitor
            monitor = get_monitor()
            
            # Separate open and closed positions
            open_positions = [p for p in all_positions if bool(p.is_open)]
            closed_positions = [p for p in all_positions if not bool(p.is_open)]
            
            # Quick stats
            col_stat1, col_stat2, col_stat3 = st.columns(3)
            with col_stat1:
                st.metric("Açık Pozisyon", len(open_positions), delta=None)
            with col_stat2:
                st.metric("Kapalı Pozisyon", len(closed_positions), delta=None)
            with col_stat3:
                st.metric("Toplam", len(all_positions), delta=None)
            
            # Tabs for Open/Closed positions
            tab_open, tab_closed = st.tabs(["🟢 Açık Pozisyonlar", "⚫ Kapalı Pozisyonlar"])
            
            with tab_open:
                if not open_positions:
                    st.info("Açık pozisyon bulunmuyor")
                else:
                    for pos in open_positions:
                        direction_icon = "🟢" if pos.side == "LONG" else "🔴"
                        reopen_info = ""
                        if monitor and pos.id in monitor.closed_positions_for_reopen:
                            from datetime import timedelta
                            closed_time = monitor.closed_positions_for_reopen[pos.id]
                            reopen_time = closed_time + timedelta(minutes=monitor.auto_reopen_delay_minutes)
                            remaining = reopen_time - datetime.now(timezone.utc)
                            if remaining.total_seconds() > 0:
                                mins = int(remaining.total_seconds() // 60)
                                secs = int(remaining.total_seconds() % 60)
                                reopen_info = f" ⏱️{mins}:{secs:02d}"
                        
                        with st.expander(f"{direction_icon} {pos.symbol} {pos.side} #{pos.id}{reopen_info}", expanded=False):
                            col_info, col_edit = st.columns([1, 2])
                            
                            with col_info:
                                st.caption(f"Değer: ${pos.amount_usdt:.0f}" if pos.amount_usdt else "Değer: —")
                                st.caption(f"Kaldıraç: {pos.leverage}x" if pos.leverage else "")
                                st.caption(f"Recovery: {pos.recovery_count or 0}")
                            
                            with col_edit:
                                edit_col1, edit_col2 = st.columns(2)
                                with edit_col1:
                                    new_tp = st.number_input(
                                        "TP (USDT)", 
                                        value=float(pos.tp_usdt) if pos.tp_usdt else 10.0,
                                        min_value=0.0,
                                        step=5.0,
                                        key=f"edit_tp_{pos.id}"
                                    )
                                with edit_col2:
                                    new_sl = st.number_input(
                                        "SL (USDT)", 
                                        value=float(pos.sl_usdt) if pos.sl_usdt else 10.0,
                                        min_value=0.0,
                                        step=5.0,
                                        key=f"edit_sl_{pos.id}"
                                    )
                                
                                new_amount = st.number_input(
                                    "Değer (USDT)", 
                                    value=float(pos.amount_usdt) if pos.amount_usdt else 100.0,
                                    min_value=10.0,
                                    step=50.0,
                                    key=f"edit_amount_{pos.id}"
                                )
                            
                            btn_col1, btn_col2, btn_col3 = st.columns(3)
                            with btn_col1:
                                if st.button("💾 Kaydet", key=f"save_{pos.id}", use_container_width=True, type="primary"):
                                    pos.tp_usdt = new_tp
                                    pos.sl_usdt = new_sl
                                    pos.amount_usdt = new_amount
                                    db.commit()
                                    clear_position_cache()
                                    st.success("Kaydedildi!")
                                    st.rerun()
                            with btn_col2:
                                if st.button("⏹️ Durdur", key=f"close_{pos.id}", use_container_width=True):
                                    setattr(pos, 'is_open', False)
                                    setattr(pos, 'closed_at', datetime.now(timezone.utc))
                                    db.commit()
                                    st.rerun()
                            with btn_col3:
                                if st.button("🗑️ Sil", key=f"delete_open_{pos.id}", use_container_width=True):
                                    db.delete(pos)
                                    db.commit()
                                    st.rerun()
                    
                    st.divider()
                    if st.button("⏹️ Tümünü Durdur", key="close_all_open", type="secondary", use_container_width=True):
                        for pos in open_positions:
                            setattr(pos, 'is_open', False)
                            setattr(pos, 'closed_at', datetime.now(timezone.utc))
                        db.commit()
                        st.rerun()
            
            with tab_closed:
                if not closed_positions:
                    st.info("Kapalı pozisyon bulunmuyor")
                else:
                    for pos in closed_positions:
                        direction_icon = "🟢" if pos.side == "LONG" else "🔴"
                        
                        with st.expander(f"{direction_icon} {pos.symbol} {pos.side} #{pos.id}", expanded=False):
                            col_info, col_edit = st.columns([1, 2])
                            
                            with col_info:
                                st.caption(f"Değer: ${pos.amount_usdt:.0f}" if pos.amount_usdt else "Değer: —")
                                st.caption(f"Kaldıraç: {pos.leverage}x" if pos.leverage else "")
                                st.caption(f"Recovery: {pos.recovery_count or 0}")
                            
                            with col_edit:
                                edit_col1, edit_col2 = st.columns(2)
                                with edit_col1:
                                    new_tp = st.number_input(
                                        "TP (USDT)", 
                                        value=float(pos.tp_usdt) if pos.tp_usdt else 10.0,
                                        min_value=0.0,
                                        step=5.0,
                                        key=f"edit_tp_closed_{pos.id}"
                                    )
                                with edit_col2:
                                    new_sl = st.number_input(
                                        "SL (USDT)", 
                                        value=float(pos.sl_usdt) if pos.sl_usdt else 10.0,
                                        min_value=0.0,
                                        step=5.0,
                                        key=f"edit_sl_closed_{pos.id}"
                                    )
                                
                                new_amount = st.number_input(
                                    "Değer (USDT)", 
                                    value=float(pos.amount_usdt) if pos.amount_usdt else 100.0,
                                    min_value=10.0,
                                    step=50.0,
                                    key=f"edit_amount_closed_{pos.id}"
                                )
                            
                            btn_col1, btn_col2, btn_col3 = st.columns(3)
                            with btn_col1:
                                if st.button("💾 Kaydet", key=f"save_closed_{pos.id}", use_container_width=True, type="primary"):
                                    pos.tp_usdt = new_tp
                                    pos.sl_usdt = new_sl
                                    pos.amount_usdt = new_amount
                                    db.commit()
                                    clear_position_cache()
                                    st.success("Kaydedildi!")
                                    st.rerun()
                            with btn_col2:
                                if st.button("▶️ Başlat", key=f"open_{pos.id}", use_container_width=True):
                                    setattr(pos, 'is_open', True)
                                    setattr(pos, 'closed_at', None)
                                    db.commit()
                                    st.rerun()
                            with btn_col3:
                                if st.button("🗑️ Sil", key=f"delete_closed_{pos.id}", use_container_width=True):
                                    db.delete(pos)
                                    db.commit()
                                    st.rerun()
                    
                    st.divider()
                    col_bulk1, col_bulk2 = st.columns(2)
                    with col_bulk1:
                        if st.button("▶️ Tümünü Başlat", key="open_all_closed", type="primary", use_container_width=True):
                            for pos in closed_positions:
                                setattr(pos, 'is_open', True)
                                setattr(pos, 'closed_at', None)
                            db.commit()
                            st.rerun()
                    with col_bulk2:
                        if st.button("🗑️ Tümünü Sil", key="delete_all_closed", use_container_width=True):
                            for pos in closed_positions:
                                db.delete(pos)
                            db.commit()
                            st.rerun()
    finally:
        db.close()

def show_active_positions_page():
    st.markdown("#### 📊 Aktif Pozisyonlar")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("🔄 Yenile", width="stretch"):
            st.rerun()
    
    client = get_cached_client()
    
    if not client.is_configured():
        st.error("OKX API yapılandırılmamış. Lütfen API anahtarlarınızı girin.")
        return
    
    usdt_balance = client.get_account_balance("USDT")
    
    if usdt_balance:
        st.markdown("##### 💰 USDT Bakiye")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Equity", f"${usdt_balance['equity']:.2f}")
        
        with col2:
            st.metric("Kullanılabilir", f"${usdt_balance['available']:.2f}")
        
        with col3:
            pnl_color = "normal" if usdt_balance['unrealized_pnl'] >= 0 else "inverse"
            st.metric("PnL", f"${usdt_balance['unrealized_pnl']:.2f}", delta_color=pnl_color)
        
        st.divider()
    else:
        st.warning("⚠️ USDT bakiye bilgisi alınamadı. OKX API bağlantısını kontrol edin.")
        st.divider()
    
    okx_positions = client.get_all_positions()
    
    if not okx_positions:
        st.info("Şu anda OKX'te aktif pozisyon bulunmuyor.")
    else:
        st.success(f"Toplam {len(okx_positions)} aktif pozisyon (OKX'ten)")
        
        db = SessionLocal()
        try:
            table_data = []
            
            for okx_pos in okx_positions:
                inst_id = okx_pos.get('instId', '')
                symbol = inst_id.replace('-USDT-SWAP', '').replace('-', '')
                position_side_raw = okx_pos.get('posSide', 'long')
                side = "LONG" if position_side_raw == "long" else "SHORT"
                
                entry_price = float(okx_pos.get('entryPrice', 0))
                unrealized_pnl = float(okx_pos.get('unrealizedProfit', 0))
                leverage = okx_pos.get('leverage', '1')
                position_amt = abs(float(okx_pos.get('positionAmt', 0)))
                pos_id = okx_pos.get('posId', 'N/A')
                
                current_price = client.get_symbol_price(symbol)
                # notionalUsd API'den string olarak gelebilir, float'a güvenli çevir
                try:
                    notional_usd = float(okx_pos.get('notionalUsd', 0))
                except (ValueError, TypeError):
                    notional_usd = 0.0
                
                # Eğer notionalUsd 0 ise alternatif olarak positionAmt * markPrice hesapla
                if notional_usd == 0 and position_amt > 0:
                    try:
                        # okx_client'ta markPrice anahtarıyla geliyor
                        mark_price = float(okx_pos.get('markPrice', okx_pos.get('last', current_price or 0)))
                        contract_val = client.get_contract_value(symbol)
                        notional_usd = position_amt * contract_val * mark_price
                    except:
                        pass
                
                tp_price = None
                sl_price = None
                db_position = db.query(Position).filter(Position.position_id == pos_id).first()
                if db_position and position_amt > 0 and db_position.tp_usdt and db_position.sl_usdt:
                    contract_value = client.get_contract_value(symbol)
                    crypto_amount = position_amt * contract_value
                    
                    price_change_tp = db_position.tp_usdt / crypto_amount
                    price_change_sl = db_position.sl_usdt / crypto_amount
                    
                    if side == "LONG":
                        tp_price = entry_price + price_change_tp
                        sl_price = entry_price - price_change_sl
                    else:
                        tp_price = entry_price - price_change_tp
                        sl_price = entry_price + price_change_sl
                
                direction_icon = "🟢" if side == "LONG" else "🔴"
                pnl_icon = "🟢" if unrealized_pnl >= 0 else "🔴"
                
                table_data.append({
                    "Coin": symbol,
                    "Yön": f"{direction_icon} {side}",
                    "Kaldıraç": f"{leverage}x",
                    "Büyüklük (USDT)": f"${notional_usd:.2f}",
                    "Giriş": f"${entry_price:.2f}",
                    "Şu an": f"${current_price:.2f}" if current_price else "N/A",
                    "PnL": f"{pnl_icon} ${unrealized_pnl:.2f}",
                    "TP Hedef": f"${tp_price:.2f}" if tp_price else "N/A",
                    "SL Hedef": f"${sl_price:.2f}" if sl_price else "N/A"
                })
            
            df = pd.DataFrame(table_data)
            st.dataframe(df, width="stretch", hide_index=True)
        finally:
            db.close()
    

def show_history_page():
    st.markdown("#### 📈 Geçmiş")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col2:
        if st.button("🔄 Yenile ", width="stretch"):
            st.rerun()
    
    with col3:
        if st.button("📥 OKX'ten Çek", width="stretch"):
            with st.spinner("OKX'ten position history alınıyor..."):
                from sync_okx_history import sync_okx_position_history
                count, error = sync_okx_position_history()
                if error:
                    st.error(f"❌ Hata: {error}")
                else:
                    st.success(f"✅ {count} pozisyon OKX'ten alındı!")
                    st.rerun()
    
    from database import PositionHistory
    
    tab1, tab2 = st.tabs(["📊 OKX Position History", "📋 Manuel Pozisyonlar (Database)"])
    
    with tab1:
        st.markdown("##### OKX History")
        
        from datetime import date, timedelta
        
        col_filter1, col_filter2 = st.columns(2)
        
        with col_filter1:
            start_date = st.date_input(
                "Başlangıç Tarihi",
                value=date.today() - timedelta(days=30),
                help="Görmek istediğiniz işlemlerin başlangıç tarihi"
            )
        
        with col_filter2:
            end_date = st.date_input(
                "Bitiş Tarihi",
                value=date.today(),
                help="Görmek istediğiniz işlemlerin bitiş tarihi"
            )
        
        db = SessionLocal()
        try:
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())
            
            total_count = db.query(PositionHistory).count()
            filtered_count = db.query(PositionHistory).filter(
                PositionHistory.u_time >= start_datetime,
                PositionHistory.u_time <= end_datetime
            ).count()
            
            st.caption(f"OKX'ten alınan tüm geçmiş pozisyonlar. Database'de toplam {total_count} kayıt (filtrelendi: {filtered_count}). 'OKX'ten Çek' butonuna basarak güncelleyin.")
            st.info("⏰ Saatler UTC (GMT+0) formatındadır. Yerel saat için +3 saat ekleyin.")
            
            history_records = db.query(PositionHistory).filter(
                PositionHistory.u_time >= start_datetime,
                PositionHistory.u_time <= end_datetime
            ).order_by(PositionHistory.u_time.desc()).all()
            
            if not history_records:
                st.info("Henüz OKX'ten veri alınmamış. Yukarıdaki '📥 OKX'ten Çek' butonuna tıklayın.")
            else:
                total_pnl = sum([rec.pnl for rec in history_records if rec.pnl])
                winning_trades = len([rec for rec in history_records if rec.pnl and rec.pnl > 0])
                losing_trades = len([rec for rec in history_records if rec.pnl and rec.pnl < 0])
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Toplam İşlem", total_count)
                
                with col2:
                    st.metric("Kazanan", winning_trades, delta=f"%{(winning_trades/len(history_records)*100):.1f}" if history_records else "0%")
                
                with col3:
                    st.metric("Kaybeden", losing_trades, delta=f"%{(losing_trades/len(history_records)*100):.1f}" if history_records else "0%")
                
                with col4:
                    pnl_color = "normal" if total_pnl >= 0 else "inverse"
                    st.metric("Toplam PnL", f"${total_pnl:.2f}", delta_color=pnl_color)
                
                st.divider()
                
                data = []
                for rec in history_records:
                    symbol = rec.inst_id.replace('-USDT-SWAP', '') if rec.inst_id else 'N/A'
                    pnl_value = rec.pnl if rec.pnl is not None else 0
                    pnl_display = f"${pnl_value:.2f}" if rec.pnl is not None else "-"
                    
                    if pnl_value > 0:
                        pnl_colored = f"🟢 {pnl_display}"
                    elif pnl_value < 0:
                        pnl_colored = f"🔴 {pnl_display}"
                    else:
                        pnl_colored = pnl_display
                    
                    data.append({
                        "Coin": symbol,
                        "Yön": rec.pos_side.upper() if rec.pos_side else 'N/A',
                        "Kaldıraç": f"{rec.leverage}x" if rec.leverage else 'N/A',
                        "Giriş": f"${rec.open_avg_px:.4f}" if rec.open_avg_px else "-",
                        "Çıkış": f"${rec.close_avg_px:.4f}" if rec.close_avg_px else "-",
                        "Miktar": f"{rec.close_total_pos:.2f}" if rec.close_total_pos else "-",
                        "PnL": pnl_colored,
                        "PnL %": f"{rec.pnl_ratio*100:.2f}%" if rec.pnl_ratio is not None else "-",
                        "Kapanış (UTC)": rec.u_time.strftime('%Y-%m-%d %H:%M:%S') if rec.u_time else "-"
                    })
                
                df = pd.DataFrame(data)
                st.dataframe(df, width="stretch", hide_index=True)
        finally:
            db.close()
    
    with tab2:
        st.markdown("##### Manuel Pozisyonlar")
        
        db = SessionLocal()
        try:
            closed_positions = db.query(Position).filter(Position.is_open == False).order_by(Position.closed_at.desc()).limit(50).all()
            
            if not closed_positions:
                st.info("Henüz kapanmış manuel pozisyon bulunmuyor.")
            else:
                total_pnl = sum([(cast(float, pos.pnl) if pos.pnl is not None else 0.0) for pos in closed_positions])
                winning_trades = len([pos for pos in closed_positions if pos.pnl is not None and cast(float, pos.pnl) > 0])
                losing_trades = len([pos for pos in closed_positions if pos.pnl is not None and cast(float, pos.pnl) < 0])
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("Toplam İşlem", len(closed_positions))
                
                with col2:
                    st.metric("Kazanan", winning_trades, delta=f"%{(winning_trades/len(closed_positions)*100):.1f}")
                
                with col3:
                    st.metric("Kaybeden", losing_trades, delta=f"%{(losing_trades/len(closed_positions)*100):.1f}")
                
                with col4:
                    pnl_color = "normal" if total_pnl >= 0 else "inverse"
                    st.metric("Toplam PnL", f"${total_pnl:.2f}", delta_color=pnl_color)
                
                st.divider()
                
                data = []
                for pos in closed_positions:
                    pnl_value = cast(float, pos.pnl) if pos.pnl is not None else 0.0
                    pnl_display = f"${pnl_value:.2f}" if pos.pnl is not None else "-"
                    
                    if pnl_value > 0:
                        pnl_colored = f"🟢 {pnl_display}"
                    elif pnl_value < 0:
                        pnl_colored = f"🔴 {pnl_display}"
                    else:
                        pnl_colored = pnl_display
                    
                    # Parent pozisyon var mı kontrolü (reopen chain)
                    parent_indicator = "🔗 Evet" if pos.parent_position_id else "—"
                    
                    data.append({
                        "Coin": str(pos.symbol),
                        "Yön": str(pos.side),
                        "Miktar": f"${cast(float, pos.amount_usdt):.2f}",
                        "Kaldıraç": f"{cast(int, pos.leverage)}x",
                        "Giriş": f"${cast(float, pos.entry_price):.4f}" if pos.entry_price is not None else "-",
                        "PnL": pnl_colored,
                        "Kapanış Nedeni": str(pos.close_reason) if pos.close_reason is not None else "-",
                        "Açılış": pos.opened_at.strftime('%Y-%m-%d %H:%M'),
                        "Kapanış": pos.closed_at.strftime('%Y-%m-%d %H:%M') if pos.closed_at is not None else "-",
                        "Reopen Zinciri": parent_indicator
                    })
                
                df = pd.DataFrame(data)
                st.dataframe(df, width="stretch", hide_index=True)
        finally:
            db.close()

def show_orders_page():
    # Auto-refresh every 60 seconds (if module available)
    try:
        from streamlit_autorefresh import st_autorefresh
        st_autorefresh(interval=60000, key="orders_autorefresh")
    except ImportError:
        pass  # Module not available, skip auto-refresh
    
    st.markdown("#### 📋 Emirler")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("🔄 Yenile  ", width="stretch"):
            st.rerun()
    
    client = get_cached_client()
    
    if not client.is_configured():
        st.error("OKX API yapılandırılmamış. Lütfen API anahtarlarınızı girin.")
        return
    
    with st.spinner("OKX'ten emirler ve pozisyonlar alınıyor..."):
        algo_orders = client.get_all_open_orders()
        positions = client.get_all_positions()
    
    position_map = {}
    mark_price_map = {}
    for pos in positions:
        inst_id = pos.get('instId', '')
        pos_side = pos.get('posSide', '')
        entry_px = pos.get('entryPrice', '0')
        mark_px = pos.get('markPrice', '0')
        try:
            position_map[f"{inst_id}_{pos_side}"] = float(entry_px)
            mark_price_map[inst_id] = float(mark_px)
        except (ValueError, TypeError):
            pass
    
    if not algo_orders:
        st.info("Şu anda aktif emir bulunmuyor.")
    else:
        st.success(f"Toplam {len(algo_orders)} aktif emir")
        
        table_data = []
        for order in algo_orders:
            inst_id = order.get('instId', 'N/A')
            algo_id = order.get('algoId', 'N/A')
            order_type = order.get('ordType', 'N/A')
            side = order.get('side', 'N/A')
            pos_side = order.get('posSide', 'N/A')
            trigger_px = order.get('triggerPx', '0')
            size = order.get('sz', '0')
            state = order.get('state', 'N/A')
            
            entry_price = position_map.get(f"{inst_id}_{pos_side}", None)
            
            if entry_price is None or entry_price == 0:
                trigger_type = "❓ Bilinmiyor"
            else:
                try:
                    trigger_price_float = float(trigger_px)
                    
                    if pos_side == "long":
                        trigger_type = "🎯 TP" if trigger_price_float > entry_price else "🛡️ SL"
                    elif pos_side == "short":
                        trigger_type = "🎯 TP" if trigger_price_float < entry_price else "🛡️ SL"
                    else:
                        trigger_type = "❓ Bilinmiyor"
                except (ValueError, TypeError):
                    trigger_type = "❓ Bilinmiyor"
            
            direction_color = "🟢" if pos_side == "long" else "🔴"
            state_emoji = "✅" if state == "live" else "⏸️"
            
            try:
                trigger_display = f"${float(trigger_px):.2f}" if trigger_px and trigger_px != '' else "N/A"
            except (ValueError, TypeError):
                trigger_display = "N/A"
            
            # Calculate expected PNL if this order triggers
            # Get contract value dynamically from OKX API
            symbol_base = inst_id.replace('-USDT-SWAP', 'USDT') if inst_id else ''
            ct_val = client.get_contract_value(symbol_base) if symbol_base else 1.0
            
            # Calculate position size in USDT
            position_size_usdt = "N/A"
            try:
                if size and entry_price and entry_price > 0:
                    size_float = float(size)
                    position_value = size_float * ct_val * entry_price
                    position_size_usdt = f"${position_value:.2f}"
            except (ValueError, TypeError):
                position_size_usdt = size
            
            expected_pnl = "N/A"
            try:
                if entry_price and entry_price > 0 and trigger_px and size:
                    trigger_price_float = float(trigger_px)
                    size_float = float(size)
                    if pos_side == "long":
                        pnl_value = (trigger_price_float - entry_price) * size_float * ct_val
                    else:  # short
                        pnl_value = (entry_price - trigger_price_float) * size_float * ct_val
                    pnl_color = "🟢" if pnl_value >= 0 else "🔴"
                    expected_pnl = f"{pnl_color} ${pnl_value:+.2f}"
            except (ValueError, TypeError):
                expected_pnl = "N/A"
            
            # Calculate distance to trigger as percentage (0-100)
            distance_pct = 0.0
            distance_usdt = 0.0
            is_tp = "TP" in trigger_type
            try:
                current_price = mark_price_map.get(inst_id, 0)
                trigger_price_float = float(trigger_px) if trigger_px else 0
                
                if current_price > 0 and trigger_price_float > 0 and entry_price and entry_price > 0:
                    # Total distance from entry to trigger
                    total_distance = abs(trigger_price_float - entry_price)
                    # Remaining distance from current to trigger
                    remaining_distance = abs(trigger_price_float - current_price)
                    
                    if total_distance > 0:
                        # Percentage of distance covered (100% = at trigger, 0% = at entry)
                        distance_pct = max(0, min(100, (1 - remaining_distance / total_distance) * 100))
                    
                    # Calculate remaining distance in USDT
                    if size:
                        size_float = float(size)
                        distance_usdt = remaining_distance * size_float * ct_val
            except (ValueError, TypeError, ZeroDivisionError):
                pass
            
            table_data.append({
                "Coin": inst_id,
                "Pozisyon": f"{direction_color} {pos_side.upper()}",
                "Tür": trigger_type,
                "Trigger Fiyat": trigger_display,
                "Pozisyon Değeri": position_size_usdt,
                "Tetik Mesafesi": distance_pct,
                "Kalan USDT": distance_usdt,
                "is_tp": is_tp,
                "Beklenen PNL": expected_pnl
            })
        
        df = pd.DataFrame(table_data)
        
        # Use column_config with ProgressColumn for distance visualization
        st.dataframe(
            df,
            width="stretch",
            hide_index=True,
            column_config={
                "Tetik Mesafesi": st.column_config.ProgressColumn(
                    "Tetik Mesafesi",
                    help="Trigger fiyata yakınlık (100% = tetiklendi)",
                    format="%.0f%%",
                    min_value=0,
                    max_value=100,
                ),
                "Kalan USDT": st.column_config.NumberColumn(
                    "Kalan $",
                    format="$%.2f"
                ),
                "is_tp": None,  # Hide this helper column
            }
        )
        
        st.divider()
        st.markdown("##### 🛠️ İşlemler")
        
        order_ids = [order.get('algoId', 'N/A') for order in algo_orders]
        order_map = {order.get('algoId'): order for order in algo_orders}
        
        selected_order_id = st.selectbox(
            "İşlem yapmak istediğiniz emri seçin:",
            options=order_ids,
            format_func=lambda x: f"{order_map[x].get('instId', 'N/A')} - {order_map[x].get('algoId', 'N/A')}"
        )
        
        if selected_order_id:
            selected_order = order_map[selected_order_id]
            inst_id = selected_order.get('instId', 'N/A')
            trigger_px = selected_order.get('triggerPx', '0')
            size = selected_order.get('sz', '0')
            
            col_action1, col_action2 = st.columns(2)
            
            with col_action1:
                st.write("**🗑️ Emri İptal Et**")
                if st.button("🗑️ İptal Et", key=f"cancel_{selected_order_id}", width="stretch"):
                    with st.spinner("İptal ediliyor..."):
                        symbol_base = inst_id.replace('-USDT-SWAP', 'USDT')
                        success = client.cancel_algo_order(symbol_base, selected_order_id)
                        if success:
                            st.success("✅ Emir iptal edildi!")
                            st.rerun()
                        else:
                            st.error("❌ İptal edilemedi")
            
            with col_action2:
                st.write("**✏️ Emri Düzenle**")
                try:
                    trigger_value = float(trigger_px) if trigger_px and trigger_px != '' else 1.0
                except (ValueError, TypeError):
                    trigger_value = 1.0
                
                new_trigger_px = st.number_input(
                    "Yeni Trigger Fiyat",
                    min_value=0.0001,
                    value=trigger_value,
                    step=0.0001,
                    key=f"edit_trigger_{selected_order_id}"
                )
                
                try:
                    size_value = max(0.01, float(size)) if size and size != '' else 0.01
                except (ValueError, TypeError):
                    size_value = 0.01
                
                new_size = st.number_input(
                    "Yeni Miktar",
                    min_value=0.01,
                    value=size_value,
                    step=0.01,
                    format="%.2f",
                    key=f"edit_size_{selected_order_id}"
                )
                
                if st.button("💾 Kaydet", key=f"save_{selected_order_id}", width="stretch"):
                    with st.spinner("Güncelleniyor..."):
                        symbol_base = inst_id.replace('-USDT-SWAP', 'USDT')
                        success = client.amend_algo_order(
                            symbol_base,
                            selected_order_id,
                            new_trigger_px,
                            new_size
                        )
                        if success:
                            st.success("✅ Emir güncellendi!")
                            st.rerun()
                        else:
                            st.error("❌ Güncellenemedi")
                
                st.divider()
    
    st.divider()
    
    with st.expander("➕ Yeni Manuel TP/SL Emri Oluştur"):
        st.info("Mevcut pozisyonlar için manuel TP veya SL emri oluşturabilirsiniz.")
        
        col1, col2 = st.columns(2)
        
        with col1:
            manual_symbol = st.selectbox(
                "Coin Çifti",
                ["SOLUSDT", "BTCUSDT", "ETHUSDT"],
                key="manual_symbol"
            )
            
            manual_pos_side = st.selectbox(
                "Pozisyon Yönü",
                ["long", "short"],
                key="manual_pos_side"
            )
            
            manual_order_type = st.selectbox(
                "Emir Türü",
                ["TP (Take Profit)", "SL (Stop Loss)"],
                key="manual_order_type"
            )
        
        with col2:
            manual_trigger_px = st.number_input(
                "Trigger Fiyat",
                min_value=0.0001,
                value=100.0,
                step=0.0001,
                key="manual_trigger_px"
            )
            
            manual_size = st.number_input(
                "Miktar (Kontrat)",
                min_value=1,
                value=1,
                step=1,
                key="manual_size"
            )
        
        if st.button("📤 Manuel Emir Oluştur"):
            with st.spinner("Emir oluşturuluyor..."):
                close_side = "sell" if manual_pos_side == "long" else "buy"
                inst_id = client.convert_symbol_to_okx(manual_symbol)
                
                try:
                    result = client.trade_api.place_algo_order(
                        instId=inst_id,
                        tdMode="cross",
                        side=close_side,
                        posSide=manual_pos_side,
                        ordType="trigger",
                        sz=str(manual_size),
                        triggerPx=str(round(manual_trigger_px, 4)),
                        orderPx="-1"
                    )
                    
                    if result.get('code') == '0':
                        st.success(f"✅ Manuel emir oluşturuldu! ID: {result['data'][0]['algoId']}")
                        st.rerun()
                    else:
                        st.error(f"❌ Hata: {result.get('msg', 'Bilinmeyen hata')}")
                except Exception as e:
                    st.error(f"❌ Hata: {e}")

def show_settings_page():
    st.markdown("#### ⚙️ Ayarlar")
    
    db = SessionLocal()
    try:
        # Load existing credentials
        creds = db.query(APICredentials).first()
        
        # Demo credentials
        demo_api_key = ""
        demo_api_secret = ""
        demo_passphrase = ""
        
        # Real credentials
        real_api_key = ""
        real_api_secret = ""
        real_passphrase = ""
        
        existing_is_demo = True
        
        if creds:
            try:
                # Try to load demo credentials
                if creds.demo_api_key_encrypted:
                    demo_api_key, demo_api_secret, demo_passphrase = creds.get_credentials(is_demo=True)
                
                # Try to load real credentials
                if creds.real_api_key_encrypted:
                    real_api_key, real_api_secret, real_passphrase = creds.get_credentials(is_demo=False)
                
                existing_is_demo = getattr(creds, 'is_demo', True)
            except:
                pass
        
        st.markdown("##### 🔑 API")
        
        # Create tabs for Demo and Real accounts
        api_tab_demo, api_tab_real = st.tabs(["🧪 Demo Hesap API", "💰 Gerçek Hesap API"])
        
        with api_tab_demo:
            st.info("Demo hesap API anahtarlarınızı buraya girin (flag=1)")
            
            col_demo1, col_demo2, col_demo3 = st.columns(3)
            with col_demo1:
                demo_key_input = st.text_input("Demo API Key", value=demo_api_key, type="password", key="demo_api_key")
            with col_demo2:
                demo_secret_input = st.text_input("Demo API Secret", value=demo_api_secret, type="password", key="demo_api_secret")
            with col_demo3:
                demo_pass_input = st.text_input("Demo Passphrase", value=demo_passphrase, type="password", key="demo_passphrase")
            
            if st.button("💾 Demo API Kaydet", key="save_demo_api", type="primary"):
                if not demo_key_input or not demo_secret_input or not demo_pass_input:
                    st.error("Lütfen tüm alanları doldurun.")
                else:
                    if not creds:
                        creds = APICredentials(is_demo=True)
                        db.add(creds)
                    
                    creds.set_credentials(demo_key_input, demo_secret_input, demo_pass_input, is_demo=True)
                    db.commit()
                    st.success("✅ Demo API anahtarları kaydedildi!")
                    st.rerun()
        
        with api_tab_real:
            st.warning("⚠️ GERÇEK hesap API anahtarlarınızı buraya girin (flag=0)")
            st.caption("Gerçek hesap ile işlem yaparken çok dikkatli olun!")
            
            col_real1, col_real2, col_real3 = st.columns(3)
            with col_real1:
                real_key_input = st.text_input("Gerçek API Key", value=real_api_key, type="password", key="real_api_key")
            with col_real2:
                real_secret_input = st.text_input("Gerçek API Secret", value=real_api_secret, type="password", key="real_api_secret")
            with col_real3:
                real_pass_input = st.text_input("Gerçek Passphrase", value=real_passphrase, type="password", key="real_passphrase")
            
            if st.button("💾 Gerçek API Kaydet", key="save_real_api", type="primary"):
                if not real_key_input or not real_secret_input or not real_pass_input:
                    st.error("Lütfen tüm alanları doldurun.")
                else:
                    if not creds:
                        creds = APICredentials(is_demo=False)
                        db.add(creds)
                    
                    creds.set_credentials(real_key_input, real_secret_input, real_pass_input, is_demo=False)
                    db.commit()
                    st.success("✅ Gerçek API anahtarları kaydedildi!")
                    st.rerun()
        
        st.divider()
        
        st.markdown("##### 🔑 Durum")
        
        client = get_cached_client()
        if client.is_configured():
            st.success(f"✅ OKX API bağlantısı aktif ({'Demo' if getattr(creds, 'is_demo', True) else 'Gerçek'})")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Position Mode'u Kontrol Et ve Aktifleştir"):
                    success = client.set_position_mode("long_short_mode")
                    if success:
                        st.success("✅ Long/Short position mode aktif")
                    else:
                        st.error("❌ Position mode aktif edilemedi")
            
            with col2:
                if creds:
                    if st.button("🗑️ API Anahtarlarını Sil"):
                        db.delete(creds)
                        db.commit()
                        st.success("API anahtarları silindi. Sayfa yenileniyor...")
                        st.rerun()
        else:
            st.error("❌ API bağlantısı kurulamadı")
            
        st.divider()
        
        st.markdown("##### 🤖 Scheduler")
        
        st.info("⚙️ **Auto-Reopen Ayarları**")
    finally:
        db.close()
    
    auto_reopen_delay = st.number_input(
        "Pozisyon kapandıktan kaç dakika sonra yeniden açılsın?",
        min_value=1,
        max_value=60,
        value=st.session_state.auto_reopen_delay_minutes,
        step=1,
        help="Pozisyon kapandıktan sonra bu süre kadar beklenip otomatik olarak yeniden açılır",
        key="auto_reopen_delay_input"
    )
    
    if auto_reopen_delay != st.session_state.auto_reopen_delay_minutes:
        old_delay = st.session_state.auto_reopen_delay_minutes
        st.session_state.auto_reopen_delay_minutes = auto_reopen_delay
        
        # Save to database
        db = SessionLocal()
        try:
            from database import Settings
            setting = db.query(Settings).filter(Settings.key == "auto_reopen_delay_minutes").first()
            if setting:
                setting.value = str(auto_reopen_delay)
                # updated_at otomatik olarak TimestampMixin tarafından güncellenir
            else:
                setting = Settings(key="auto_reopen_delay_minutes", value=str(auto_reopen_delay))
                db.add(setting)
            db.commit()
        finally:
            db.close()
        
        # Otomatik restart: Bot çalışıyorsa restart et
        from background_scheduler import get_monitor, stop_monitor, start_monitor
        monitor = get_monitor()
        if monitor and monitor.is_running():
            st.info(f"⚙️ Ayar değişti: {old_delay} dk → {auto_reopen_delay} dk. Bot yeniden başlatılıyor...")
            stop_monitor()
            import time
            time.sleep(1)
            if start_monitor(auto_reopen_delay):
                st.success(f"✅ Bot yeni ayarla yeniden başlatıldı! (Auto-reopen: {auto_reopen_delay} dakika)")
            else:
                st.error("❌ Bot yeniden başlatılamadı. Lütfen manuel olarak başlatın.")
        else:
            st.success(f"✅ Auto-reopen süresi **{auto_reopen_delay} dakika** olarak güncellendi!")
            st.info("💡 Bot başlatıldığında bu ayar kullanılacak.")
    else:
        st.caption(f"📌 Mevcut ayar: **{st.session_state.auto_reopen_delay_minutes} dakika**")
    
    st.divider()
    
    from background_scheduler import get_monitor, stop_monitor, start_monitor
    
    monitor = get_monitor()
    is_running = monitor.is_running() if monitor else False
    
    if is_running:
        st.success(f"✅ Çalışıyor (Auto-reopen: {st.session_state.auto_reopen_delay_minutes} dk)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("⏸️ Botu Durdur", type="secondary", width="stretch"):
                if stop_monitor():
                    st.success("✅ Background scheduler durduruldu!")
                    st.rerun()
                else:
                    st.error("❌ Durdurulamadı")
        
        with col2:
            st.caption("Scheduler çalışıyor")
    
    else:
        st.error("⚠️ Durmuş - Otomatik izleme kapalı")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("▶️ Botu Başlat", type="primary", width="stretch"):
                reopen_delay = st.session_state.get('auto_reopen_delay_minutes', 5)
                if start_monitor(reopen_delay):
                    st.success(f"✅ Background scheduler başlatıldı! (Auto-reopen: {reopen_delay} dakika)")
                    st.rerun()
                else:
                    st.error("❌ Başlatılamadı")
        
        with col2:
            st.caption("Scheduler durmuş")
    
    st.divider()
    
    st.markdown("##### 🛡️ Recovery")
    
    st.caption("Pozisyon zarar seviyelerine göre basamaklı kurtarma (max 5 basamak)")
    
    # Load current recovery settings from database
    db_recovery = SessionLocal()
    try:
        from database import Settings
        
        enabled_setting = db_recovery.query(Settings).filter(Settings.key == "recovery_enabled").first()
        tp_setting = db_recovery.query(Settings).filter(Settings.key == "recovery_tp_usdt").first()
        sl_setting = db_recovery.query(Settings).filter(Settings.key == "recovery_sl_usdt").first()
        
        current_enabled = enabled_setting.value.lower() == 'true' if enabled_setting else True
        current_tp = float(tp_setting.value) if tp_setting else 50.0
        current_sl = float(sl_setting.value) if sl_setting else 100.0
        
        # Load multi-step settings with per-step TP/SL
        steps_data = []
        for i in range(1, 6):
            trigger = db_recovery.query(Settings).filter(Settings.key == f"recovery_step_{i}_trigger").first()
            add_amt = db_recovery.query(Settings).filter(Settings.key == f"recovery_step_{i}_add").first()
            tp_step = db_recovery.query(Settings).filter(Settings.key == f"recovery_step_{i}_tp").first()
            sl_step = db_recovery.query(Settings).filter(Settings.key == f"recovery_step_{i}_sl").first()
            if trigger and add_amt:
                steps_data.append({
                    'trigger': float(trigger.value),
                    'add': float(add_amt.value),
                    'tp': float(tp_step.value) if tp_step else 50.0,
                    'sl': float(sl_step.value) if sl_step else 100.0
                })
        
        # If no steps, use default values
        if not steps_data:
            steps_data = [
                {'trigger': -50.0, 'add': 3000.0, 'tp': 30.0, 'sl': 1200.0}
            ]
    finally:
        db_recovery.close()
    
    recovery_enabled = st.toggle("🔄 Kurtarma Özelliği Aktif", value=current_enabled, 
                                  help="Bot başladığında otomatik açılır, sadece manuel kapatılabilir")
    
    st.markdown("##### 📊 Basamak Ayarları")
    
    num_steps = st.number_input("Basamak Sayısı", min_value=1, max_value=5, value=len(steps_data), step=1)
    
    step_triggers = []
    step_adds = []
    step_tps = []
    step_sls = []
    
    for i in range(int(num_steps)):
        st.markdown(f"**Basamak {i+1}**")
        col1, col2, col3, col4 = st.columns(4)
        default_trigger = steps_data[i]['trigger'] if i < len(steps_data) else -50.0 * (i + 1)
        default_add = steps_data[i]['add'] if i < len(steps_data) else 100.0 * (i + 1)
        default_tp = steps_data[i]['tp'] if i < len(steps_data) else current_tp
        default_sl = steps_data[i]['sl'] if i < len(steps_data) else current_sl
        
        with col1:
            trigger = st.number_input(
                f"Tetikleme PNL",
                min_value=-10000.0,
                max_value=0.0,
                value=default_trigger,
                step=10.0,
                key=f"step_{i}_trigger",
                help=f"Basamak {i+1} için tetikleme değeri"
            )
            step_triggers.append(trigger)
        
        with col2:
            add = st.number_input(
                f"Ekleme (USDT)",
                min_value=10.0,
                max_value=50000.0,
                value=default_add,
                step=50.0,
                key=f"step_{i}_add",
                help=f"Basamak {i+1} tetiklendiğinde eklenecek miktar"
            )
            step_adds.append(add)
        
        with col3:
            tp = st.number_input(
                f"🎯 TP (USDT)",
                min_value=1.0,
                max_value=10000.0,
                value=default_tp,
                step=10.0,
                key=f"step_{i}_tp",
                help=f"Basamak {i+1} sonrası yeni kar hedefi"
            )
            step_tps.append(tp)
        
        with col4:
            sl = st.number_input(
                f"🛑 SL (USDT)",
                min_value=1.0,
                max_value=10000.0,
                value=default_sl,
                step=10.0,
                key=f"step_{i}_sl",
                help=f"Basamak {i+1} sonrası yeni zarar limiti"
            )
            step_sls.append(sl)
    
    if st.button("💾 Kurtarma Ayarlarını Kaydet", type="primary"):
        db_save = SessionLocal()
        try:
            from database import Settings
            from datetime import datetime, timezone
            
            settings_to_save = [
                ("recovery_enabled", str(recovery_enabled).lower())
            ]
            
            # Save step settings with per-step TP/SL
            for i in range(int(num_steps)):
                settings_to_save.append((f"recovery_step_{i+1}_trigger", str(step_triggers[i])))
                settings_to_save.append((f"recovery_step_{i+1}_add", str(step_adds[i])))
                settings_to_save.append((f"recovery_step_{i+1}_tp", str(step_tps[i])))
                settings_to_save.append((f"recovery_step_{i+1}_sl", str(step_sls[i])))
            
            # Clear unused steps
            for i in range(int(num_steps) + 1, 6):
                for suffix in ['trigger', 'add', 'tp', 'sl']:
                    existing = db_save.query(Settings).filter(Settings.key == f"recovery_step_{i}_{suffix}").first()
                    if existing:
                        db_save.delete(existing)
            
            for key, value in settings_to_save:
                existing = db_save.query(Settings).filter(Settings.key == key).first()
                if existing:
                    existing.value = value
                    # updated_at otomatik olarak TimestampMixin tarafından güncellenir
                else:
                    new_setting = Settings(key=key, value=value)
                    db_save.add(new_setting)
            
            db_save.commit()
            st.success("✅ Basamaklı kurtarma ayarları kaydedildi!")
            
            if recovery_enabled:
                step_info = "\n".join([f"  - Basamak {i+1}: PNL ≤ {step_triggers[i]} → +{step_adds[i]} USDT | TP:{step_tps[i]} SL:{step_sls[i]}" for i in range(int(num_steps))])
                st.info(f"""
**Aktif Kurtarma Ayarları:**
{step_info}
                """)
        except Exception as e:
            db_save.rollback()
            st.error(f"❌ Hata: {str(e)}")
        finally:
            db_save.close()
    
    st.divider()
    
    with st.expander("🌐 OKX Info"):
        st.caption("Demo: https://www.okx.com/trade-demo")
        st.caption("API: https://www.okx.com/api/v5")
    
    st.divider()
    
    st.markdown("##### 📊 Database")
    
    db = SessionLocal()
    try:
        total_positions = db.query(Position).count()
        active_positions = db.query(Position).filter(Position.is_open == True).count()
        closed_positions = db.query(Position).filter(Position.is_open == False).count()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Toplam Kayıt", total_positions)
        
        with col2:
            st.metric("Aktif", active_positions)
        
        with col3:
            st.metric("Kapanmış", closed_positions)
    finally:
        db.close()

    st.divider()
    st.markdown("##### 🛠️ SQL")
    st.warning("⚠️ **DİKKAT:** Bu bölüm doğrudan veritabanı sorguları çalıştırmanızı sağlar. Sadece ne yaptığınızdan eminseniz kullanın.")
    
    with st.expander("📝 SQL Komutu Çalıştır"):
        sql_input = st.text_area("SQL Sorgusu", placeholder="ALTER TABLE api_credentials ADD COLUMN ...", height=100)
        col1, col2 = st.columns([1, 4])
        with col1:
            run_sql = st.button("🚀 Çalıştır", type="primary")
        
        if run_sql and sql_input:
            from sqlalchemy import text
            import pandas as pd
            db = SessionLocal()
            try:
                # DML/DDL işlemleri için execute kullanıyoruz
                result = db.execute(text(sql_input))
                
                # Eğer bir SELECT sorgusuysa sonuçları göster
                if sql_input.strip().upper().startswith("SELECT"):
                    df = pd.DataFrame(result.fetchall(), columns=result.keys())
                    if not df.empty:
                        st.dataframe(df)
                        st.success(f"✅ Sorgu başarılı! {len(df)} kayıt bulundu.")
                    else:
                        st.info("ℹ️ Sorgu başarılı ancak sonuç dönmedi.")
                else:
                    db.commit()
                    st.success("✅ SQL komutu başarıyla çalıştırıldı!")
                    if result.rowcount > 0:
                        st.info(f"ℹ️ Etkilenen satır sayısı: {result.rowcount}")
            except Exception as e:
                db.rollback()
                st.error(f"❌ SQL Hatası: {str(e)}")
            finally:
                db.close()

if __name__ == "__main__":
    main()
