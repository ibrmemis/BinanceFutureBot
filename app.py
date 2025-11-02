import streamlit as st
import pandas as pd
from datetime import datetime
from typing import cast
from database import init_db, SessionLocal, Position, APICredentials
from okx_client import OKXTestnetClient
from trading_strategy import Try1Strategy
from background_scheduler import get_monitor
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
    st.title("📈 OKX Futures Trading Bot (Demo Trading)")
    st.caption("OKX Demo Trading üzerinde çalışan otomatik futures trading botu")
    
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
        active_positions = db.query(Position).filter(Position.is_open == True).order_by(Position.opened_at.desc()).all()
        
        if not active_positions:
            st.info("Şu anda strateji ile oluşturulmuş aktif pozisyon bulunmuyor.")
        else:
            st.success(f"Toplam {len(active_positions)} aktif pozisyon")
            
            table_data = []
            for pos in active_positions:
                position_side = pos.position_side if pos.position_side else ("long" if pos.side == "LONG" else "short")
                okx_pos = client.get_position(str(pos.symbol), position_side)
                
                if pos.position_id and okx_pos and okx_pos.get('posId') != pos.position_id:
                    continue
                
                if okx_pos and float(okx_pos.get('positionAmt', 0)) != 0:
                    entry_price = float(okx_pos.get('entryPrice', pos.entry_price or 0))
                    unrealized_pnl = float(okx_pos.get('unrealizedProfit', 0))
                else:
                    entry_price = pos.entry_price or 0
                    unrealized_pnl = 0
                
                current_price = client.get_symbol_price(str(pos.symbol)) or 0
                
                direction = "🟢 LONG" if pos.side == "LONG" else "🔴 SHORT"
                pnl_display = f"{'🟢' if unrealized_pnl >= 0 else '🔴'} ${unrealized_pnl:.2f}"
                
                table_data.append({
                    "ID": pos.id,
                    "Coin": pos.symbol,
                    "Yön": direction,
                    "Kaldıraç": f"{pos.leverage}x",
                    "Miktar": f"${pos.amount_usdt:.2f}",
                    "Giriş": f"${entry_price:.4f}",
                    "Şu an": f"${current_price:.4f}",
                    "PnL": pnl_display,
                    "TP": f"${pos.tp_usdt:.2f}",
                    "SL": f"${pos.sl_usdt:.2f}",
                    "Açılış": pos.opened_at.strftime('%Y-%m-%d %H:%M')
                })
            
            df = pd.DataFrame(table_data)
            st.dataframe(
                df,
                width="stretch",
                hide_index=True,
                column_config={
                    "ID": st.column_config.NumberColumn("ID", width="small"),
                    "Coin": st.column_config.TextColumn("Coin", width="small"),
                    "Yön": st.column_config.TextColumn("Yön", width="small"),
                    "Kaldıraç": st.column_config.TextColumn("Kaldıraç", width="small"),
                    "Miktar": st.column_config.TextColumn("Miktar", width="small"),
                    "Giriş": st.column_config.TextColumn("Giriş", width="medium"),
                    "Şu an": st.column_config.TextColumn("Şu an", width="medium"),
                    "PnL": st.column_config.TextColumn("PnL", width="small"),
                    "TP": st.column_config.TextColumn("TP", width="small"),
                    "SL": st.column_config.TextColumn("SL", width="small"),
                    "Açılış": st.column_config.TextColumn("Açılış", width="medium")
                }
            )
            
            st.divider()
            st.subheader("⚙️ Pozisyon Yönetimi")
            
            position_ids = [pos.id for pos in active_positions]
            selected_position_id = st.selectbox(
                "Yönetmek istediğiniz pozisyonu seçin:",
                options=position_ids,
                format_func=lambda x: f"Pozisyon #{x} - {next((p.symbol for p in active_positions if p.id == x), 'N/A')}"
            )
            
            if selected_position_id:
                selected_pos = next((p for p in active_positions if p.id == selected_position_id), None)
                
                if selected_pos:
                    col1, col2 = st.columns(2)
                    
                    with col1:
                        st.write("**✏️ TP/SL Değerlerini Değiştir**")
                        new_tp = st.number_input(
                            "Yeni TP (USDT)",
                            min_value=0.1,
                            value=float(selected_pos.tp_usdt),
                            step=1.0,
                            key=f"manage_tp_{selected_position_id}"
                        )
                        new_sl = st.number_input(
                            "Yeni SL (USDT)",
                            min_value=0.1,
                            value=float(selected_pos.sl_usdt),
                            step=1.0,
                            key=f"manage_sl_{selected_position_id}"
                        )
                        if st.button("💾 TP/SL Güncelle", key=f"btn_update_{selected_position_id}", type="primary"):
                            selected_pos.tp_usdt = new_tp
                            selected_pos.sl_usdt = new_sl
                            db.commit()
                            st.success("✅ TP/SL güncellendi!")
                            st.info("💡 Mevcut TP/SL emirlerini 'Emirler' sayfasından iptal edip yenilerini oluşturabilirsiniz.")
                            st.rerun()
                    
                    with col2:
                        st.write("**⏹️ Pozisyon İşlemleri**")
                        st.warning(f"Pozisyon: {selected_pos.symbol} - {selected_pos.side}")
                        st.caption(f"Miktar: ${selected_pos.amount_usdt:.2f} | Kaldıraç: {selected_pos.leverage}x")
                        
                        col2_1, col2_2 = st.columns(2)
                        
                        with col2_1:
                            if st.button("⏹️ Kapat", key=f"btn_close_{selected_position_id}", type="secondary", width="stretch"):
                                with st.spinner("Pozisyon kapatılıyor..."):
                                    position_side = selected_pos.position_side if selected_pos.position_side else ("long" if selected_pos.side == "LONG" else "short")
                                    okx_pos = client.get_position(str(selected_pos.symbol), position_side)
                                    close_side = "sell" if selected_pos.side == "LONG" else "buy"
                                    
                                    if okx_pos:
                                        quantity = abs(int(float(okx_pos.get('positionAmt', 0))))
                                        if quantity > 0:
                                            success = client.close_position_market(
                                                str(selected_pos.symbol),
                                                close_side,
                                                quantity,
                                                position_side
                                            )
                                            if success:
                                                selected_pos.is_open = False
                                                selected_pos.closed_at = datetime.utcnow()
                                                selected_pos.close_reason = "Manuel kapatma"
                                                db.commit()
                                                st.success("✅ Pozisyon başarıyla kapatıldı!")
                                                st.rerun()
                                            else:
                                                st.error("❌ Pozisyon kapatılamadı")
                                        else:
                                            st.error("❌ Pozisyon miktarı 0 - zaten kapalı olabilir")
                                    else:
                                        st.error("❌ OKX'te pozisyon bulunamadı")
                        
                        with col2_2:
                            if st.button("🗑️ Sil", key=f"btn_delete_{selected_position_id}", type="secondary", width="stretch"):
                                if st.session_state.get(f'confirm_delete_{selected_position_id}', False):
                                    db.delete(selected_pos)
                                    db.commit()
                                    st.success("✅ Pozisyon database'den silindi!")
                                    st.rerun()
                                else:
                                    st.session_state[f'confirm_delete_{selected_position_id}'] = True
                                    st.warning("⚠️ Tekrar 'Sil' butonuna basarak onaylayın!")
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
    
    okx_positions = client.get_all_positions()
    
    if not okx_positions:
        st.info("Şu anda OKX'te aktif pozisyon bulunmuyor.")
    else:
        st.success(f"Toplam {len(okx_positions)} aktif pozisyon (OKX'ten)")
        
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
            
            with st.container():
                col1, col2, col3, col4 = st.columns([2, 1, 1, 2])
                
                with col1:
                    st.metric("Coin", symbol)
                
                with col2:
                    direction_color = "🟢" if side == "LONG" else "🔴"
                    st.metric("Yön", f"{direction_color} {side}")
                
                with col3:
                    st.metric("Kaldıraç", f"{leverage}x")
                
                with col4:
                    st.metric("Kontrat", f"{int(position_amt)}")
                
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.caption(f"Giriş: ${entry_price:.4f}")
                
                with col2:
                    if current_price:
                        st.caption(f"Şu an: ${current_price:.4f}")
                    else:
                        st.caption("Fiyat: N/A")
                
                with col3:
                    pnl_color = "🟢" if unrealized_pnl >= 0 else "🔴"
                    st.caption(f"PnL: {pnl_color} ${unrealized_pnl:.2f}")
                
                with col4:
                    st.caption(f"PosID: {pos_id}")
                
                st.divider()
    

def show_history_page():
    st.header("📈 Geçmiş İşlemler")
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        if st.button("🔄 Yenile ", width="stretch"):
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
    
    with st.spinner("OKX'ten emirler alınıyor..."):
        algo_orders = client.get_algo_orders()
    
    if not algo_orders:
        st.info("Şu anda aktif emir bulunmuyor.")
    else:
        st.success(f"Toplam {len(algo_orders)} aktif emir")
        
        for order in algo_orders:
            inst_id = order.get('instId', 'N/A')
            algo_id = order.get('algoId', 'N/A')
            order_type = order.get('ordType', 'N/A')
            side = order.get('side', 'N/A')
            pos_side = order.get('posSide', 'N/A')
            trigger_px = order.get('triggerPx', '0')
            size = order.get('sz', '0')
            state = order.get('state', 'N/A')
            
            trigger_type = "🎯 TP" if side == "sell" and pos_side == "long" else "🎯 TP" if side == "buy" and pos_side == "short" else "🛡️ SL"
            
            with st.container():
                col1, col2, col3, col4, col5, col6 = st.columns([2, 1, 1, 1, 1, 1])
                
                with col1:
                    st.metric("Coin", inst_id)
                
                with col2:
                    direction_color = "🟢" if pos_side == "long" else "🔴"
                    st.metric("Pozisyon", f"{direction_color} {pos_side.upper()}")
                
                with col3:
                    st.metric("Tür", trigger_type)
                
                with col4:
                    st.metric("Trigger Fiyat", f"${float(trigger_px):.4f}")
                
                with col5:
                    st.metric("Miktar", size)
                
                with col6:
                    state_emoji = "✅" if state == "live" else "⏸️"
                    st.metric("Durum", f"{state_emoji} {state}")
                
                col1, col2, col3 = st.columns([2, 1, 1])
                
                with col1:
                    st.caption(f"Emir ID: {algo_id}")
                
                with col2:
                    if st.button(f"🗑️ İptal", key=f"cancel_{algo_id}"):
                        with st.spinner("İptal ediliyor..."):
                            symbol_base = inst_id.replace('-USDT-SWAP', 'USDT')
                            success = client.cancel_algo_order(symbol_base, algo_id)
                            if success:
                                st.success("✅ Emir iptal edildi!")
                                st.rerun()
                            else:
                                st.error("❌ İptal edilemedi")
                
                with col3:
                    with st.popover("✏️ Düzenle"):
                        st.caption("Trigger fiyatını değiştir")
                        new_trigger_px = st.number_input(
                            "Yeni Trigger Fiyat",
                            min_value=0.0001,
                            value=float(trigger_px),
                            step=0.0001,
                            key=f"edit_trigger_{algo_id}"
                        )
                        new_size = st.number_input(
                            "Yeni Miktar",
                            min_value=1,
                            value=int(float(size)),
                            step=1,
                            key=f"edit_size_{algo_id}"
                        )
                        if st.button("💾 Kaydet", key=f"save_{algo_id}"):
                            with st.spinner("Güncelleniyor..."):
                                symbol_base = inst_id.replace('-USDT-SWAP', 'USDT')
                                success = client.amend_algo_order(
                                    symbol_base,
                                    algo_id,
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
    
    st.subheader("🤖 Arka Plan İzleme")
    
    st.info("""
    **Otomatik İzleme Sistemi Aktif:**
    
    - ✅ Pozisyonlar her **1 dakikada** kontrol ediliyor
    - ✅ Kapanan pozisyonlar **5 dakika** sonra otomatik yeniden açılıyor
    - ✅ Tüm işlemler veritabanına kaydediliyor
    """)
    
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
