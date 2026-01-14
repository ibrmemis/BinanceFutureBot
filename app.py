import streamlit as st
import os
from dotenv import load_dotenv

# Load environment variables explicitly
load_dotenv()

from database import init_db, SessionLocal, APICredentials
from database_utils import DatabaseManager, get_db_session
from background_scheduler import get_monitor, stop_monitor, start_monitor
from constants import (
    UIConstants, DatabaseConstants, TradingConstants, EnvVars
)
from services import check_api_keys

# Import UI pages
from ui.trade import show_new_trade_page
from ui.dashboard import show_active_positions_page
from ui.orders import show_orders_page
from ui.history import show_history_page
from ui.settings import show_settings_page
from ui.database_view import show_database_page

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
        
        with get_db_session() as db:
            creds = db.query(APICredentials).first()
            current_mode = "demo" if (not creds or creds.is_demo) else "real"
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🧪", type="primary" if current_mode == "demo" else "secondary", use_container_width=True, key="btn_demo", help="Demo Mode"):
                with get_db_session() as db:
                    creds = db.query(APICredentials).first()
                    if creds:
                        creds.is_demo = True
                        db.commit()
                        st.rerun()
        with col2:
            if st.button("💰", type="primary" if current_mode == "real" else "secondary", use_container_width=True, key="btn_real", help="Real Mode"):
                with get_db_session() as db:
                    creds = db.query(APICredentials).first()
                    if creds:
                        creds.is_demo = False
                        db.commit()
                        st.rerun()
                    else:
                        st.warning("API key gerekli")
        
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
                    try:
                        with get_db_session() as db:
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

if __name__ == "__main__":
    main()
