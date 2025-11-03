import streamlit as st
import pandas as pd
from datetime import datetime
from typing import cast
from database import init_db, SessionLocal, Position, APICredentials
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
        st.session_state.auto_reopen_delay_minutes = 5
    
    st.title("📈 OKX Futures Trading Bot (Demo Trading)")
    st.caption("OKX Demo Trading üzerinde çalışan otomatik futures trading botu")
    
    with st.sidebar:
        st.header("🤖 Bot Kontrolü")
        
        monitor = get_monitor()
        bot_running = monitor.is_running() if monitor else False
        
        if bot_running:
            st.success("✅ Bot Çalışıyor")
            st.caption("Pozisyonlar otomatik takip ediliyor")
            if st.button("⏹️ Botu Durdur", type="primary", use_container_width=True):
                if stop_monitor():
                    st.success("Bot durduruldu!")
                    st.rerun()
                else:
                    st.error("Bot durdurulamadı!")
        else:
            st.error("⏸️ Bot Durdu")
            st.caption("Pozisyonlar takip edilmiyor")
            if st.button("▶️ Botu Başlat", type="primary", use_container_width=True):
                reopen_delay = st.session_state.get('auto_reopen_delay_minutes', 5)
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
    
    tabs = st.tabs(["🎯 Yeni İşlem", "📊 Aktif Pozisyonlar", "📋 Emirler", "📈 Geçmiş İşlemler", "⚙️ Ayarlar"])
    
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

def show_new_trade_page():
    st.header("🎯 Yeni İşlem Aç - try1 Stratejisi")
    
    col1, col2 = st.columns(2)
    
    with col1:
        symbol = st.selectbox(
            "Coin Çifti",
            ["SOLUSDT", "BTCUSDT", "ETHUSDT"]
        )
        
        amount_usdt = st.number_input(
            "Pozisyon Değeri (USDT)",
            min_value=1.0,
            value=1111.0,
            step=10.0,
            help="Toplam pozisyon büyüklüğü (örn: 1000 USDT)"
        )
        
        leverage = st.number_input(
            "Kaldıraç",
            min_value=1,
            max_value=125,
            value=20,
            step=1
        )
        
        # Calculate real position value using correct contract specifications
        client = OKXTestnetClient()
        current_price = client.get_symbol_price(symbol)
        if current_price:
            # Get contract value (e.g., ETH: 0.1, BTC: 0.01, SOL: 1)
            contract_value = client.get_contract_value(symbol)
            contract_usdt_value = contract_value * current_price
            
            # Calculate exact contracts and round to 2 decimals
            exact_contracts = amount_usdt / contract_usdt_value
            actual_contracts = max(0.01, round(exact_contracts, 2))
            actual_position_value = actual_contracts * contract_usdt_value
            
            margin_used = actual_position_value / leverage
            st.caption(f"💰 Kullanılacak Marjin: ${margin_used:.2f} USDT")
            st.caption(f"📊 Kontrat: {actual_contracts} (1 kontrat = {contract_value} {symbol[:3]} = ${contract_usdt_value:.2f})")
            
            # Show info if actual value differs
            diff_pct = abs(actual_position_value - amount_usdt) / amount_usdt * 100
            if diff_pct > 5:  # >5% difference
                st.info(f"ℹ️ **Gerçek Pozisyon Değeri: ${actual_position_value:.2f}** (Fark: {diff_pct:.1f}%)")
        else:
            margin_used = amount_usdt / leverage
            st.caption(f"💰 Kullanılacak Marjin: ${margin_used:.2f} USDT")
    
    with col2:
        side = st.selectbox(
            "İşlem Yönü",
            ["LONG", "SHORT"]
        )
        
        tp_usdt = st.number_input(
            "Take Profit (USDT - PnL)",
            min_value=0.1,
            value=5.0,
            step=1.0
        )
        
        sl_usdt = st.number_input(
            "Stop Loss (USDT - PnL)",
            min_value=0.1,
            value=115.0,
            step=1.0
        )
    
    st.divider()
    
    col1, col2, col3 = st.columns([1, 1, 2])
    
    with col1:
        if st.button("🚀 Pozisyon Aç", type="primary", width="stretch"):
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
        client = OKXTestnetClient()
        if st.button("🔄 Mevcut Fiyat", width="stretch"):
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
        - ✅ Pozisyon Değeri: Toplam pozisyon büyüklüğü (örn: 1000 USDT)
        - ✅ Marjin: Pozisyon Değeri / Kaldıraç (örn: 1000 / 10 = 100 USDT marjin kullanılır)
        - ✅ TP ve SL USDT cinsinden PnL değeri olarak belirlenir
        - ✅ Long/Short mode aktif (LONG ve SHORT ayrı pozisyonlar olarak açılabilir)
        - ✅ Pozisyon kapandığında **5 dakika sonra** otomatik olarak aynı parametrelerle yeniden açılır
        - ✅ Her 1 dakikada pozisyonlar kontrol edilir
        - ✅ Yeni işlem açılmadan önce eski işlemin kapanması beklenir
        """)
    
    st.divider()
    st.subheader("📋 Strateji ile Oluşturulmuş Pozisyonlar")
    
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
                    "Kontrat": f"{db_quantity:.2f}",
                    "Değer": f"${db_amount:.2f}",
                    "Giriş": f"${db_entry_price:.4f}",
                    "Şu an": current_price_display,
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
                    "Kontrat": st.column_config.TextColumn("Kontrat", width="small"),
                    "Değer": st.column_config.TextColumn("Değer (USDT)", width="small"),
                    "Giriş": st.column_config.TextColumn("Giriş", width="medium"),
                    "Şu an": st.column_config.TextColumn("Şu an", width="medium"),
                    "PnL": st.column_config.TextColumn("PnL", width="small"),
                    "TP": st.column_config.TextColumn("TP (USDT)", width="small"),
                    "SL": st.column_config.TextColumn("SL (USDT)", width="small"),
                    "Açılış": st.column_config.TextColumn("Açılış", width="medium")
                }
            )
            
            st.divider()
            st.subheader("🔧 Pozisyon Kontrolü - Aç/Kapat")
            st.caption("Her pozisyonun durumunu değiştirerek bot'un auto-reopen davranışını kontrol edin")
            
            for pos in all_positions:
                col1, col2, col3, col4 = st.columns([3, 2, 1, 1])
                
                with col1:
                    status_icon = "🟢" if pos.is_open else "⚫"
                    st.write(f"{status_icon} **#{pos.id} - {pos.symbol} {pos.side}**")
                
                with col2:
                    # Safely format nullable fields
                    tp_str = f"${pos.tp_usdt:.2f}" if pos.tp_usdt is not None else "—"
                    sl_str = f"${pos.sl_usdt:.2f}" if pos.sl_usdt is not None else "—"
                    st.caption(f"TP: {tp_str} | SL: {sl_str}")
                
                with col3:
                    status_text = "AÇIK" if pos.is_open else "KAPALI"
                    st.caption(f"**{status_text}**")
                
                with col4:
                    if pos.is_open:
                        if st.button("⚫", key=f"close_{pos.id}", help="Kapat", use_container_width=True):
                            pos.is_open = False
                            pos.closed_at = datetime.utcnow()
                            db.commit()
                            st.rerun()
                    else:
                        if st.button("🟢", key=f"open_{pos.id}", help="Aç", use_container_width=True):
                            pos.is_open = True
                            pos.closed_at = None
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
                    "Kontrat": int(position_amt),
                    "Giriş": f"${entry_price:.4f}",
                    "Şu an": f"${current_price:.4f}" if current_price else "N/A",
                    "PnL": f"{pnl_icon} ${unrealized_pnl:.2f}",
                    "TP Hedef": f"${tp_price:.4f}" if tp_price else "N/A",
                    "SL Hedef": f"${sl_price:.4f}" if sl_price else "N/A",
                    "PosID": pos_id
                })
            
            df = pd.DataFrame(table_data)
            st.dataframe(df, use_container_width=True, hide_index=True)
        finally:
            db.close()
    

def show_history_page():
    st.header("📈 Geçmiş İşlemler")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col2:
        if st.button("🔄 Yenile ", use_container_width=True):
            st.rerun()
    
    with col3:
        if st.button("📥 OKX'ten Çek", use_container_width=True):
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
                st.dataframe(df, use_container_width=True, hide_index=True)
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
                st.dataframe(df, use_container_width=True, hide_index=True)
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
        st.dataframe(df, use_container_width=True, hide_index=True)
        
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
                if st.button("🗑️ İptal Et", key=f"cancel_{selected_order_id}", use_container_width=True):
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
                
                if st.button("💾 Kaydet", key=f"save_{selected_order_id}", use_container_width=True):
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
    
    client = OKXTestnetClient()
    
    st.subheader("🔑 API Bağlantı Durumu")
    
    if client.is_configured():
        st.success("✅ OKX API bağlantısı aktif")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("🔄 Position Mode'u Kontrol Et ve Aktifleştir"):
                success = client.set_position_mode("long_short_mode")
                if success:
                    st.success("✅ Long/Short position mode aktif")
                else:
                    st.error("❌ Position mode aktif edilemedi")
        
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
            passphrase_input = st.text_input("Passphrase", type="password", key="settings_passphrase")
            
            if st.button("Kaydet ve Bağlan"):
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
                        st.success("✅ API anahtarları kaydedildi! Sayfa yenileniyor...")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Hata: {e}")
                    finally:
                        db.close()
    
    st.divider()
    
    st.subheader("🤖 Arka Plan İzleme (Background Scheduler)")
    
    st.info("⚙️ **Auto-Reopen Ayarları**")
    
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
        st.session_state.auto_reopen_delay_minutes = auto_reopen_delay
        st.success(f"✅ Auto-reopen süresi **{auto_reopen_delay} dakika** olarak güncellendi!")
        st.info("⚠️ Değişikliğin uygulanması için botu durdurup tekrar başlatın.")
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
            if st.button("⏸️ Botu Durdur", type="secondary", use_container_width=True):
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
            if st.button("▶️ Botu Başlat", type="primary", use_container_width=True):
                reopen_delay = st.session_state.get('auto_reopen_delay_minutes', 5)
                if start_monitor(reopen_delay):
                    st.success(f"✅ Background scheduler başlatıldı! (Auto-reopen: {reopen_delay} dakika)")
                    st.rerun()
                else:
                    st.error("❌ Başlatılamadı")
        
        with col2:
            st.caption("Scheduler durmuş")
    
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

if __name__ == "__main__":
    main()
