import streamlit as st
import pandas as pd
from datetime import datetime
from typing import cast
from database import init_db, SessionLocal, Position, APICredentials
from binance_client import BinanceTestnetClient
from trading_strategy import Try1Strategy
from background_scheduler import get_monitor
import os

st.set_page_config(
    page_title="Binance Futures Trading Bot",
    page_icon="📈",
    layout="wide"
)

init_db()

monitor = get_monitor()

def check_api_keys():
    api_key = os.getenv("BINANCE_TESTNET_API_KEY")
    api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")
    
    if api_key and api_secret:
        return True
    
    db = SessionLocal()
    try:
        creds = db.query(APICredentials).first()
        return creds is not None
    finally:
        db.close()
    
    return False

def main():
    st.title("📈 Binance Futures Trading Bot (Testnet)")
    st.caption("demo.binance.com üzerinde çalışan otomatik futures trading botu")
    
    if not check_api_keys():
        st.error("⚠️ Binance API anahtarları yapılandırılmamış!")
        st.info("""
        **API Anahtarlarını Yapılandırma:**
        
        1. Binance Testnet'e gidin: https://demo.binance.com
        2. API anahtarlarınızı oluşturun
        3. Replit Secrets bölümünden aşağıdaki değişkenleri ekleyin:
           - `BINANCE_TESTNET_API_KEY`
           - `BINANCE_TESTNET_API_SECRET`
        4. Sayfayı yenileyin
        """)
        
        with st.expander("🔧 API Key Kaydetme (Veritabanı)"):
            st.info("API anahtarlarınız şifrelenmiş olarak veritabanına kaydedilecek.")
            api_key_input = st.text_input("API Key", type="password", key="api_key_input")
            api_secret_input = st.text_input("API Secret", type="password", key="api_secret_input")
            
            if st.button("Veritabanına Kaydet"):
                if api_key_input and api_secret_input:
                    db = SessionLocal()
                    try:
                        creds = db.query(APICredentials).first()
                        if creds:
                            creds.set_credentials(api_key_input, api_secret_input)
                        else:
                            creds = APICredentials()
                            creds.set_credentials(api_key_input, api_secret_input)
                            db.add(creds)
                        db.commit()
                        st.success("✅ API anahtarları veritabanına kaydedildi! Sayfa yenileniyor...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Hata: {e}")
                    finally:
                        db.close()
                else:
                    st.warning("Lütfen her iki alanı da doldurun.")
        return
    
    tabs = st.tabs(["🎯 Yeni İşlem", "📊 Aktif Pozisyonlar", "📈 Geçmiş İşlemler", "⚙️ Ayarlar"])
    
    with tabs[0]:
        show_new_trade_page()
    
    with tabs[1]:
        show_active_positions_page()
    
    with tabs[2]:
        show_history_page()
    
    with tabs[3]:
        show_settings_page()

def show_new_trade_page():
    st.header("🎯 Yeni İşlem Aç - try1 Stratejisi")
    
    col1, col2 = st.columns(2)
    
    with col1:
        symbol = st.selectbox(
            "Coin Çifti",
            ["SOLUSDT", "BTCUSDT", "ETHUSDT"]
        )
        
        amount_usdt = st.number_input(
            "İşlem Miktarı (USDT)",
            min_value=1.0,
            value=100.0,
            step=10.0
        )
        
        leverage = st.number_input(
            "Kaldıraç",
            min_value=1,
            max_value=125,
            value=10,
            step=1
        )
    
    with col2:
        side = st.selectbox(
            "İşlem Yönü",
            ["LONG", "SHORT"]
        )
        
        tp_usdt = st.number_input(
            "Take Profit (USDT - PnL)",
            min_value=0.1,
            value=10.0,
            step=1.0
        )
        
        sl_usdt = st.number_input(
            "Stop Loss (USDT - PnL)",
            min_value=0.1,
            value=5.0,
            step=1.0
        )
    
    st.divider()
    
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("🚀 Pozisyon Aç", type="primary", use_container_width=True):
            with st.spinner("Pozisyon açılıyor..."):
                strategy = Try1Strategy()
                success, message, position_id = strategy.open_position(
                    symbol=symbol,
                    side=side,
                    amount_usdt=amount_usdt,
                    leverage=leverage,
                    tp_usdt=tp_usdt,
                    sl_usdt=sl_usdt
                )
                
                if success:
                    st.success(f"✅ {message}")
                    st.balloons()
                else:
                    st.error(f"❌ {message}")
    
    with col2:
        client = BinanceTestnetClient()
        if st.button("🔄 Mevcut Fiyat", use_container_width=True):
            price = client.get_symbol_price(symbol)
            if price:
                st.info(f"{symbol}: ${price:,.2f}")
            else:
                st.error("Fiyat alınamadı")
    
    st.divider()
    
    with st.expander("ℹ️ try1 Stratejisi Hakkında"):
        st.markdown("""
        **try1 Stratejisi Özellikleri:**
        
        - ✅ Cross Margin modunda işlem
        - ✅ Market emri ile anında açılış
        - ✅ TP ve SL USDT cinsinden PnL değeri olarak belirlenir
        - ✅ Hedge mode aktif (LONG ve SHORT aynı anda açılabilir)
        - ✅ Pozisyon kapandığında **5 dakika sonra** otomatik olarak aynı parametrelerle yeniden açılır
        - ✅ Her 1 dakikada pozisyonlar kontrol edilir
        - ✅ Yeni işlem açılmadan önce eski işlemin kapanması beklenir
        """)

def show_active_positions_page():
    st.header("📊 Aktif Pozisyonlar")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("🔄 Yenile", use_container_width=True):
            st.rerun()
    
    db = SessionLocal()
    try:
        active_positions = db.query(Position).filter(Position.is_open == True).order_by(Position.opened_at.desc()).all()
        
        if not active_positions:
            st.info("Şu anda aktif pozisyon bulunmuyor.")
        else:
            st.success(f"Toplam {len(active_positions)} aktif pozisyon")
            
            for pos in active_positions:
                with st.container():
                    col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 2, 1])
                    
                    with col1:
                        st.metric("Coin", str(pos.symbol))
                    
                    with col2:
                        side_value = str(pos.side)
                        direction_color = "🟢" if side_value == "LONG" else "🔴"
                        st.metric("Yön", f"{direction_color} {side_value}")
                    
                    with col3:
                        leverage_val = cast(int, pos.leverage)
                        st.metric("Kaldıraç", f"{leverage_val}x")
                    
                    with col4:
                        amount_val = cast(float, pos.amount_usdt)
                        st.metric("Miktar", f"${amount_val:.2f}")
                    
                    with col5:
                        reopen_val = cast(int, pos.reopen_count) if pos.reopen_count is not None else 0
                        if reopen_val > 0:
                            st.metric("Yeniden Açılma", reopen_val)
                    
                    col1, col2, col3, col4 = st.columns(4)
                    
                    with col1:
                        st.caption(f"Giriş: ${pos.entry_price:.4f}")
                    
                    with col2:
                        st.caption(f"Miktar: {pos.quantity}")
                    
                    with col3:
                        st.caption(f"TP: ${pos.tp_usdt:.2f}")
                    
                    with col4:
                        st.caption(f"SL: ${pos.sl_usdt:.2f}")
                    
                    st.caption(f"Açılış: {pos.opened_at.strftime('%Y-%m-%d %H:%M:%S')} UTC")
                    st.divider()
    finally:
        db.close()

def show_history_page():
    st.header("📈 Geçmiş İşlemler")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("🔄 Yenile ", use_container_width=True):
            st.rerun()
    
    db = SessionLocal()
    try:
        closed_positions = db.query(Position).filter(Position.is_open == False).order_by(Position.closed_at.desc()).limit(50).all()
        
        if not closed_positions:
            st.info("Henüz kapanmış pozisyon bulunmuyor.")
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
                data.append({
                    "Coin": str(pos.symbol),
                    "Yön": str(pos.side),
                    "Miktar": f"${cast(float, pos.amount_usdt):.2f}",
                    "Kaldıraç": f"{cast(int, pos.leverage)}x",
                    "Giriş": f"${cast(float, pos.entry_price):.4f}" if pos.entry_price is not None else "-",
                    "PnL": f"${cast(float, pos.pnl):.2f}" if pos.pnl is not None else "-",
                    "Kapanış Nedeni": str(pos.close_reason) if pos.close_reason is not None else "-",
                    "Açılış": pos.opened_at.strftime('%Y-%m-%d %H:%M'),
                    "Kapanış": pos.closed_at.strftime('%Y-%m-%d %H:%M') if pos.closed_at is not None else "-",
                    "Yeniden Açılma": cast(int, pos.reopen_count)
                })
            
            df = pd.DataFrame(data)
            st.dataframe(df, use_container_width=True, hide_index=True)
    finally:
        db.close()

def show_settings_page():
    st.header("⚙️ Sistem Ayarları")
    
    client = BinanceTestnetClient()
    
    st.subheader("🔑 API Bağlantı Durumu")
    
    if client.is_configured():
        st.success("✅ Binance API bağlantısı aktif")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Hedge Mode'u Kontrol Et ve Aktifleştir"):
                success = client.set_hedge_mode()
                if success:
                    st.success("✅ Hedge mode aktif")
                else:
                    st.error("❌ Hedge mode aktif edilemedi")
        
        with col2:
            db = SessionLocal()
            try:
                creds = db.query(APICredentials).first()
                if creds:
                    if st.button("🗑️ API Anahtarlarını Sil"):
                        db.delete(creds)
                        db.commit()
                        st.success("API anahtarları silindi. Sayfa yenileniyor...")
                        st.rerun()
            finally:
                db.close()
    else:
        st.error("❌ API bağlantısı kurulamadı")
        
        with st.expander("🔧 API Anahtarlarını Güncelle"):
            api_key_input = st.text_input("API Key", type="password", key="settings_api_key")
            api_secret_input = st.text_input("API Secret", type="password", key="settings_api_secret")
            
            if st.button("Kaydet ve Bağlan"):
                if api_key_input and api_secret_input:
                    db = SessionLocal()
                    try:
                        creds = db.query(APICredentials).first()
                        if creds:
                            creds.set_credentials(api_key_input, api_secret_input)
                        else:
                            creds = APICredentials()
                            creds.set_credentials(api_key_input, api_secret_input)
                            db.add(creds)
                        db.commit()
                        st.success("✅ API anahtarları kaydedildi! Sayfa yenileniyor...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Hata: {e}")
                    finally:
                        db.close()
    
    st.divider()
    
    st.subheader("🤖 Arka Plan İzleme")
    
    st.info("""
    **Otomatik İzleme Sistemi Aktif:**
    
    - ✅ Pozisyonlar her **1 dakikada** kontrol ediliyor
    - ✅ Kapanan pozisyonlar **5 dakika** sonra otomatik yeniden açılıyor
    - ✅ Tüm işlemler veritabanına kaydediliyor
    """)
    
    st.divider()
    
    st.subheader("🌐 Binance Testnet Bilgileri")
    
    st.markdown("""
    - **Testnet URL:** https://demo.binance.com
    - **API Endpoint:** demo.binance.com
    - **Mod:** Futures Testnet (Demo Trading)
    - **Ülke:** Avrupa sunucuları üzerinden erişim
    """)
    
    st.divider()
    
    st.subheader("📊 Veritabanı Durumu")
    
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

if __name__ == "__main__":
    main()
