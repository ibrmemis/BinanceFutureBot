import streamlit as st
import pandas as pd
from datetime import datetime, timezone
from typing import cast
from database import init_db, SessionLocal, Position, APICredentials, Settings
from okx_client import OKXTestnetClient
from trading_strategy import Try1Strategy
from background_scheduler import get_monitor, stop_monitor, start_monitor
import os

st.set_page_config(
    page_title="OKX Futures Trading Bot (Demo)",
    page_icon="📈",
    layout="wide"
)

init_db()

monitor = get_monitor()

def check_api_keys():
    api_key = os.getenv("OKX_DEMO_API_KEY")
    api_secret = os.getenv("OKX_DEMO_API_SECRET")
    passphrase = os.getenv("OKX_DEMO_PASSPHRASE")
    
    if api_key and api_secret and passphrase:
        return True
    
    db = SessionLocal()
    try:
        creds = db.query(APICredentials).first()
        return creds is not None
    finally:
        db.close()
    
    return False

def main():
    if 'auto_reopen_delay_minutes' not in st.session_state:
        # Load from database, default to 1 minute if not set
        db = SessionLocal()
        try:
            setting = db.query(Settings).filter(Settings.key == "auto_reopen_delay_minutes").first()
            if setting:
                st.session_state.auto_reopen_delay_minutes = int(setting.value)
            else:
                # Default to 1 minute
                st.session_state.auto_reopen_delay_minutes = 1
                # Try to save default to database (ignore if already exists)
                try:
                    setting = Settings(key="auto_reopen_delay_minutes", value="1")
                    db.add(setting)
                    db.commit()
                except Exception:
                    db.rollback()
                    # Setting already exists, just use default
                    pass
        finally:
            db.close()
    
    st.title("📈 OKX Futures Trading Bot (Demo Trading)")
    st.caption("OKX Demo Trading üzerinde çalışan otomatik futures trading botu")
    
    with st.sidebar:
        st.header("🤖 Bot Kontrolü")
        
        monitor = get_monitor()
        bot_running = monitor.is_running() if monitor else False
        
        if bot_running:
            st.success("✅ Bot Çalışıyor")
            st.caption("Pozisyonlar otomatik takip ediliyor")
            if st.button("⏹️ Botu Durdur", type="primary", width="stretch"):
                if stop_monitor():
                    st.success("Bot durduruldu!")
                    st.rerun()
                else:
                    st.error("Bot durdurulamadı!")
        else:
            st.error("⏸️ Bot Durdu")
            st.caption("Pozisyonlar takip edilmiyor")
            if st.button("▶️ Botu Başlat", type="primary", width="stretch"):
                reopen_delay = st.session_state.get('auto_reopen_delay_minutes', 3)
                if start_monitor(reopen_delay):
                    st.success(f"Bot başlatıldı! (Auto-reopen: {reopen_delay} dk)")
                    st.rerun()
                else:
                    st.error("Bot başlatılamadı!")
        
        st.divider()
        st.caption("⚠️ Bot durduğunda:")
        st.caption("• Pozisyon takibi yapılmaz")
        st.caption("• Otomatik yeniden açma çalışmaz")
        st.caption("• TP/SL emirleri OKX'te aktif kalır")
    
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
    
    tabs = st.tabs(["🎯 Yeni İşlem", "📊 Aktif Pozisyonlar", "📋 Emirler", "📈 Geçmiş İşlemler", "⚙️ Ayarlar", "💾 Database"])
    
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
    st.header("💾 Veritabanı Görüntüleyici")
    st.caption("Sistemdeki tüm tabloları ve verileri buradan inceleyebilirsiniz.")
    
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
    st.header("🎯 Yeni İşlem Aç")
    
    client = OKXTestnetClient()
    all_symbols = client.get_all_swap_symbols()
    
    popular_coins = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    other_coins = [s for s in all_symbols if s not in popular_coins]
    ordered_symbols = popular_coins + other_coins
    
    with st.container(border=True):
        col1, col2, col3 = st.columns(3)
        
        with col1:
            symbol = st.selectbox("Coin", ordered_symbols, help=f"{len(all_symbols)} çift mevcut")
            current_price = client.get_symbol_price(symbol)
            if current_price:
                st.caption(f"Fiyat: **${current_price:,.2f}**")
        
        with col2:
            side = st.selectbox("Yön", ["LONG", "SHORT"])
            side_emoji = "🟢" if side == "LONG" else "🔴"
            st.caption(f"{side_emoji} {side}")
        
        with col3:
            leverage = st.number_input("Kaldıraç", min_value=1, max_value=125, value=20, step=1)
        
        col4, col5, col6 = st.columns(3)
        
        with col4:
            amount_usdt = st.number_input("Pozisyon (USDT)", min_value=1.0, value=1111.0, step=10.0)
        
        with col5:
            tp_usdt = st.number_input("TP (USDT)", min_value=0.1, value=5.0, step=1.0, help="Kar hedefi")
        
        with col6:
            sl_usdt = st.number_input("SL (USDT)", min_value=0.1, value=115.0, step=1.0, help="Zarar limiti")
        
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
                                tp_order_id=None, sl_order_id=None, is_open=True, parent_position_id=None
                            )
                            db.add(position)
                            db.commit()
                            st.success(f"✅ Kaydedildi (ID: {position.id})")
                    except Exception as e:
                        db.rollback()
                        st.error(f"❌ Hata: {e}")
                    finally:
                        db.close()
    
    st.subheader("📋 Pozisyonlar")
    
    client = OKXTestnetClient()
    
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
            
            with st.expander("🔧 Pozisyon Kontrolü", expanded=False):
                st.caption("Bot'un auto-reopen davranışını kontrol edin veya pozisyonları silin")
                
                col_bulk1, col_bulk2, col_bulk3, col_bulk4 = st.columns(4)
                
                with col_bulk1:
                    if st.button("🟢 Tümünü Aç", use_container_width=True, key="bulk_open_all"):
                        for pos in all_positions:
                            setattr(pos, 'is_open', True)
                            setattr(pos, 'closed_at', None)
                        db.commit()
                        st.rerun()
                
                with col_bulk2:
                    if st.button("⚫ Tümünü Kapat", use_container_width=True, key="bulk_close_all"):
                        for pos in all_positions:
                            setattr(pos, 'is_open', False)
                            setattr(pos, 'closed_at', datetime.now(timezone.utc))
                        db.commit()
                        st.rerun()
                
                with col_bulk3:
                    if st.button("🗑️ Kapalıları Sil", use_container_width=True, key="bulk_delete_closed"):
                        closed_positions = [p for p in all_positions if not p.is_open]
                        for pos in closed_positions:
                            db.delete(pos)
                        db.commit()
                        st.rerun()
                
                with col_bulk4:
                    if st.button("🔄 Yenile", use_container_width=True, key="bulk_refresh"):
                        st.rerun()
                
                from background_scheduler import get_monitor
                monitor = get_monitor()
                
                for pos in all_positions:
                    col1, col2, col3, col4 = st.columns([3, 1, 0.5, 0.5])
                    
                    with col1:
                        status_icon = "🟢" if bool(pos.is_open) else "⚫"
                        reopen_info = ""
                        if monitor and pos.id in monitor.closed_positions_for_reopen:
                            from datetime import timedelta
                            closed_time = monitor.closed_positions_for_reopen[pos.id]
                            reopen_time = closed_time + timedelta(minutes=monitor.auto_reopen_delay_minutes)
                            remaining = reopen_time - datetime.now(timezone.utc)
                            if remaining.total_seconds() > 0:
                                mins = int(remaining.total_seconds() // 60)
                                secs = int(remaining.total_seconds() % 60)
                                reopen_info = f" ⏱️ {mins}:{secs:02d}"
                        st.write(f"{status_icon} #{pos.id} {pos.symbol} {pos.side}{reopen_info}")
                    
                    with col2:
                        tp_str = f"${pos.tp_usdt:.0f}" if pos.tp_usdt else "—"
                        sl_str = f"${pos.sl_usdt:.0f}" if pos.sl_usdt else "—"
                        st.caption(f"TP:{tp_str} SL:{sl_str}")
                    
                    with col3:
                        if bool(pos.is_open):
                            if st.button("⚫", key=f"close_{pos.id}"):
                                setattr(pos, 'is_open', False)
                                setattr(pos, 'closed_at', datetime.now(timezone.utc))
                                db.commit()
                                st.rerun()
                        else:
                            if st.button("🟢", key=f"open_{pos.id}"):
                                setattr(pos, 'is_open', True)
                                setattr(pos, 'closed_at', None)
                                db.commit()
                                st.rerun()
                    
                    with col4:
                        if st.button("🗑️", key=f"delete_{pos.id}", help="Sil"):
                            db.delete(pos)
                            db.commit()
                            st.rerun()
    finally:
        db.close()

def show_active_positions_page():
    st.header("📊 Aktif Pozisyonlar (Real-Time OKX)")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("🔄 Yenile", width="stretch"):
            st.rerun()
    
    client = OKXTestnetClient()
    
    if not client.is_configured():
        st.error("OKX API yapılandırılmamış. Lütfen API anahtarlarınızı girin.")
        return
    
    usdt_balance = client.get_account_balance("USDT")
    
    if usdt_balance:
        st.subheader("💰 USDT Asset Bilgisi")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Equity (Toplam Bakiye)", 
                f"${usdt_balance['equity']:.2f}",
                help="Toplam USDT bakiyeniz (kullanılan + kullanılabilir)"
            )
        
        with col2:
            st.metric(
                "Kullanılabilir", 
                f"${usdt_balance['available']:.2f}",
                help="Yeni pozisyon açmak için kullanılabilir USDT"
            )
        
        with col3:
            pnl_color = "normal" if usdt_balance['unrealized_pnl'] >= 0 else "inverse"
            st.metric(
                "Floating PnL", 
                f"${usdt_balance['unrealized_pnl']:.2f}",
                delta_color=pnl_color,
                help="Açık pozisyonlarınızın toplam gerçekleşmemiş kar/zarar"
            )
        
        with col4:
            st.metric(
                "Kullanımda (Margin)", 
                f"${usdt_balance['margin_used']:.2f}",
                help="Açık pozisyonlar için kullanılan margin"
            )
        
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
                    "Giriş": f"${entry_price:.4f}",
                    "Şu an": f"${current_price:.4f}" if current_price else "N/A",
                    "PnL": f"{pnl_icon} ${unrealized_pnl:.2f}",
                    "TP Hedef": f"${tp_price:.4f}" if tp_price else "N/A",
                    "SL Hedef": f"${sl_price:.4f}" if sl_price else "N/A",
                    "PosID": pos_id
                })
            
            df = pd.DataFrame(table_data)
            st.dataframe(df, width="stretch", hide_index=True)
        finally:
            db.close()
    

def show_history_page():
    st.header("📈 Geçmiş İşlemler")
    
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
        st.subheader("OKX Position History (Tüm Kapanmış Pozisyonlar)")
        
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
            from datetime import datetime as dt_module
            start_datetime = dt_module.combine(start_date, dt_module.min.time())
            end_datetime = dt_module.combine(end_date, dt_module.max.time())
            
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
        st.subheader("Manuel Oluşturulan Pozisyonlar (Database)")
        st.caption("Bu uygulama üzerinden manuel olarak açılmış pozisyonlar.")
        
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
    st.header("📋 Strateji Emirleri (TP/SL)")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("🔄 Yenile  ", width="stretch"):
            st.rerun()
    
    client = OKXTestnetClient()
    
    if not client.is_configured():
        st.error("OKX API yapılandırılmamış. Lütfen API anahtarlarınızı girin.")
        return
    
    with st.spinner("OKX'ten emirler ve pozisyonlar alınıyor..."):
        algo_orders = client.get_all_open_orders()
        positions = client.get_all_positions()
    
    position_map = {}
    for pos in positions:
        inst_id = pos.get('instId', '')
        pos_side = pos.get('posSide', '')
        entry_px = pos.get('entryPrice', '0')
        try:
            position_map[f"{inst_id}_{pos_side}"] = float(entry_px)
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
                trigger_display = f"${float(trigger_px):.4f}" if trigger_px and trigger_px != '' else "N/A"
            except (ValueError, TypeError):
                trigger_display = "N/A"
            
            table_data.append({
                "Coin": inst_id,
                "Pozisyon": f"{direction_color} {pos_side.upper()}",
                "Tür": trigger_type,
                "Trigger Fiyat": trigger_display,
                "Miktar": size,
                "Durum": f"{state_emoji} {state}",
                "Emir ID": algo_id
            })
        
        df = pd.DataFrame(table_data)
        st.dataframe(df, width="stretch", hide_index=True)
        
        st.divider()
        st.subheader("🛠️ Emir İşlemleri")
        
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
    st.header("⚙️ Sistem Ayarları")
    
    db = SessionLocal()
    try:
        # Load existing credentials
        creds = db.query(APICredentials).first()
        existing_api_key = ""
        existing_api_secret = ""
        existing_passphrase = ""
        existing_is_demo = True
        
        if creds:
            try:
                existing_api_key, existing_api_secret, existing_passphrase = creds.get_credentials()
                existing_is_demo = getattr(creds, 'is_demo', True)
            except:
                pass
        
        st.subheader("🔑 OKX API Yapılandırması")
        
        # Account Type Selection
        account_type = st.radio(
            "Hesap Türü",
            ["Demo Hesap (Simüle)", "Gerçek Hesap (Live)"],
            index=0 if existing_is_demo else 1,
            help="Demo hesap için flag=1, Gerçek hesap için flag=0 kullanılır."
        )
        is_demo = (account_type == "Demo Hesap (Simüle)")
        
        col_api1, col_api2, col_api3 = st.columns(3)
        with col_api1:
            new_api_key = st.text_input("API Key", value=existing_api_key, type="password", key="new_settings_api_key")
        with col_api2:
            new_api_secret = st.text_input("API Secret", value=existing_api_secret, type="password", key="new_settings_api_secret")
        with col_api3:
            new_passphrase = st.text_input("Passphrase", value=existing_passphrase, type="password", key="new_settings_passphrase")
        
        if st.button("💾 API Bilgilerini Kaydet", key="save_api_creds_btn"):
            if not new_api_key or not new_api_secret or not new_passphrase:
                st.error("Lütfen tüm alanları doldurun.")
            else:
                if creds:
                    creds.set_credentials(new_api_key, new_api_secret, new_passphrase)
                    creds.is_demo = is_demo
                    creds.updated_at = datetime.utcnow()
                else:
                    creds = APICredentials(is_demo=is_demo)
                    creds.set_credentials(new_api_key, new_api_secret, new_passphrase)
                    db.add(creds)
                
                db.commit()
                st.success(f"API bilgileri ({account_type}) başarıyla kaydedildi! Değişikliklerin uygulanması için botu yeniden başlatmanız gerekebilir.")
                st.rerun()
        
        st.divider()
        
        st.subheader("🔑 API Bağlantı Durumu")
        
        client = OKXTestnetClient()
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
        
        st.subheader("🤖 Arka Plan İzleme (Background Scheduler)")
        
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
                setting.updated_at = datetime.utcnow()
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
        st.success("✅ **Background Scheduler ÇALIŞIYOR**")
        
        current_delay = st.session_state.auto_reopen_delay_minutes
        st.info(f"""
        **Otomatik İzleme Sistemi Aktif:**
        
        - ✅ Pozisyonlar her **1 dakikada** kontrol ediliyor
        - ✅ Orphaned emirler her **1 dakikada** temizleniyor
        - ✅ Kapanan pozisyonlar **{current_delay} dakika** sonra otomatik yeniden açılıyor
        - ✅ Tüm işlemler veritabanına kaydediliyor
        """)
        
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
        st.error("⚠️ **Background Scheduler DURMUŞ**")
        
        st.warning("""
        **Otomatik izleme sistemi kapalı:**
        
        - ❌ Pozisyonlar otomatik kontrol edilmiyor
        - ❌ Orphaned emirler temizlenmiyor
        - ❌ Auto-reopen çalışmıyor
        
        **Botu başlatmak için aşağıdaki butona tıklayın:**
        """)
        
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
    
    st.subheader("🛡️ Kurtarma (Recovery) Ayarları")
    
    st.info("""
    **Kurtarma Özelliği Nedir?**
    
    Pozisyonunuz belirli bir zarar seviyesine ulaştığında otomatik olarak:
    1. Mevcut TP/SL emirlerini iptal eder
    2. Pozisyona ekleme yaparak ortalama maliyeti düşürür
    3. Yeni toplam miktara göre TP/SL emirleri yerleştirir
    """)
    
    # Load current recovery settings from database
    db_recovery = SessionLocal()
    try:
        from database import Settings
        
        enabled_setting = db_recovery.query(Settings).filter(Settings.key == "recovery_enabled").first()
        trigger_setting = db_recovery.query(Settings).filter(Settings.key == "recovery_trigger_pnl").first()
        add_amount_setting = db_recovery.query(Settings).filter(Settings.key == "recovery_add_amount").first()
        tp_setting = db_recovery.query(Settings).filter(Settings.key == "recovery_tp_usdt").first()
        sl_setting = db_recovery.query(Settings).filter(Settings.key == "recovery_sl_usdt").first()
        
        current_enabled = enabled_setting.value.lower() == 'true' if enabled_setting else False
        current_trigger = float(trigger_setting.value) if trigger_setting else -50.0
        current_add_amount = float(add_amount_setting.value) if add_amount_setting else 100.0
        current_tp = float(tp_setting.value) if tp_setting else 50.0
        current_sl = float(sl_setting.value) if sl_setting else 100.0
    finally:
        db_recovery.close()
    
    recovery_enabled = st.toggle("🔄 Kurtarma Özelliği Aktif", value=current_enabled, 
                                  help="Açık olduğunda, pozisyonlar zarar eşiğine ulaştığında otomatik kurtarma devreye girer")
    
    col1, col2 = st.columns(2)
    
    with col1:
        recovery_trigger = st.number_input(
            "📉 Tetikleme PNL (USDT)",
            min_value=-1000.0,
            max_value=0.0,
            value=current_trigger,
            step=10.0,
            help="Pozisyon PNL'i bu değere düştüğünde kurtarma tetiklenir (örn: -50 USDT)"
        )
        
        recovery_add_amount = st.number_input(
            "➕ Ekleme Miktarı (USDT)",
            min_value=10.0,
            max_value=10000.0,
            value=current_add_amount,
            step=50.0,
            help="Kurtarma tetiklendiğinde pozisyona eklenecek miktar"
        )
    
    with col2:
        recovery_tp = st.number_input(
            "🎯 Yeni TP (USDT)",
            min_value=1.0,
            max_value=10000.0,
            value=current_tp,
            step=10.0,
            help="Kurtarma sonrası yeni kar hedefi (toplam pozisyon için)"
        )
        
        recovery_sl = st.number_input(
            "🛑 Yeni SL (USDT)",
            min_value=1.0,
            max_value=10000.0,
            value=current_sl,
            step=10.0,
            help="Kurtarma sonrası yeni zarar limiti (toplam pozisyon için)"
        )
    
    if st.button("💾 Kurtarma Ayarlarını Kaydet", type="primary"):
        db_save = SessionLocal()
        try:
            from database import Settings
            from datetime import datetime, timezone
            
            settings_to_save = [
                ("recovery_enabled", str(recovery_enabled).lower()),
                ("recovery_trigger_pnl", str(recovery_trigger)),
                ("recovery_add_amount", str(recovery_add_amount)),
                ("recovery_tp_usdt", str(recovery_tp)),
                ("recovery_sl_usdt", str(recovery_sl))
            ]
            
            for key, value in settings_to_save:
                existing = db_save.query(Settings).filter(Settings.key == key).first()
                if existing:
                    existing.value = value
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    new_setting = Settings(key=key, value=value)
                    db_save.add(new_setting)
            
            db_save.commit()
            st.success("✅ Kurtarma ayarları kaydedildi!")
            
            if recovery_enabled:
                st.info(f"""
                **Aktif Kurtarma Ayarları:**
                - Tetikleme: PNL ≤ {recovery_trigger} USDT
                - Ekleme: {recovery_add_amount} USDT
                - Yeni TP: {recovery_tp} USDT | Yeni SL: {recovery_sl} USDT
                """)
        except Exception as e:
            db_save.rollback()
            st.error(f"❌ Hata: {str(e)}")
        finally:
            db_save.close()
    
    st.divider()
    
    st.subheader("🌐 OKX Demo Trading Bilgileri")
    
    st.markdown("""
    - **Demo Trading URL:** https://www.okx.com/trade-demo
    - **API Endpoint:** https://www.okx.com/api/v5
    - **Mod:** Demo Trading (Simüle Edilmiş İşlemler)
    - **Avantaj:** Coğrafi kısıtlama yok, global erişim
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

    st.divider()
    st.subheader("🛠️ Veritabanı SQL Araçları")
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
