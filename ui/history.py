import streamlit as st
import pandas as pd
from datetime import date, timedelta, datetime
from typing import cast
from database import SessionLocal, Position, PositionHistory
from services import get_cached_client

def show_history_page():
    st.markdown("#### 📈 Geçmiş")
    
    col1, col2, col3 = st.columns([2, 1, 1])
    
    with col2:
        if st.button("🔄 Yenile ", width="stretch", key="refresh_history"):
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
    
    tab1, tab2 = st.tabs(["📊 OKX Position History", "📋 Manuel Pozisyonlar (Database)"])
    
    with tab1:
        st.markdown("##### OKX History")
        
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
