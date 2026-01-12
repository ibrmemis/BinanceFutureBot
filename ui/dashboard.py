import streamlit as st
import pandas as pd
from database import SessionLocal, Position
from services import get_cached_client
from constants import PositionSide

def show_active_positions_page():
    # st.markdown("#### 📊 Aktif Pozisyonlar")
    
    client = get_cached_client()
    
    if not client.is_configured():
        st.error("OKX API yapılandırılmamış.")
        return
    
    usdt_balance = client.get_account_balance("USDT")
    
    col_bal, col_refresh = st.columns([4, 1])
    
    with col_bal:
        if usdt_balance:
            c1, c2, c3 = st.columns(3)
            c1.metric("Equity", f"${usdt_balance['equity']:.0f}")
            c2.metric("Avail", f"${usdt_balance['available']:.0f}")
            pnl_color = "normal" if usdt_balance['unrealized_pnl'] >= 0 else "inverse"
            c3.metric("PnL", f"${usdt_balance['unrealized_pnl']:.2f}", delta_color=pnl_color)
        else:
            st.warning("Bakiye alınamadı")

    with col_refresh:
        if st.button("🔄", help="Yenile", use_container_width=True, key="refresh_dashboard"):
            st.rerun()
    
    st.divider()
    
    okx_positions = client.get_all_positions()
    
    if not okx_positions:
        st.info("Aktif pozisyon yok.")
    else:
        # st.success(f"Toplam {len(okx_positions)} pozisyon")
        
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
                try:
                    notional_usd = float(okx_pos.get('notionalUsd', 0))
                except (ValueError, TypeError):
                    notional_usd = 0.0
                
                if notional_usd == 0 and position_amt > 0:
                    try:
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
                    "Lev": f"{leverage}x",
                    "Size": f"${notional_usd:.0f}",
                    "Giriş": f"${entry_price:.4f}",
                    "PnL": f"{pnl_icon} ${unrealized_pnl:.2f}",
                    "TP": f"${tp_price:.4f}" if tp_price else "-",
                    "SL": f"${sl_price:.4f}" if sl_price else "-"
                })
            
            df = pd.DataFrame(table_data)
            st.dataframe(
                df, 
                width="stretch", 
                hide_index=True,
                column_config={
                    "Coin": st.column_config.TextColumn("Coin", width="small"),
                    "Yön": st.column_config.TextColumn("Yön", width="small"),
                    "Lev": st.column_config.TextColumn("Lev", width="small"),
                    "Size": st.column_config.TextColumn("Size", width="small"),
                    "Giriş": st.column_config.TextColumn("Giriş", width="small"),
                    "PnL": st.column_config.TextColumn("PnL", width="small"),
                    "TP": st.column_config.TextColumn("TP", width="small"),
                    "SL": st.column_config.TextColumn("SL", width="small"),
                }
            )
        finally:
            db.close()
