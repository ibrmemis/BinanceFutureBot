import streamlit as st
import pandas as pd
from database import SessionLocal, Position
from services import get_cached_client, get_cached_symbols, get_cached_price
from trading_strategy import TradingStrategy
from constants import APIConstants

def show_new_trade_page():
    # st.markdown("#### 🎯 Yeni İşlem") # Removed header to save space
    
    client = get_cached_client()
    all_symbols = get_cached_symbols()
    
    popular_coins = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    other_coins = [s for s in all_symbols if s not in popular_coins]
    ordered_symbols = popular_coins + other_coins
    
    with st.container(border=True):
        # Row 1: Symbol, Side, Leverage, Amount
        col1, col2, col3, col4 = st.columns([2, 1.5, 1.5, 2])
        
        with col1:
            symbol = st.selectbox("Coin", ordered_symbols, help=f"{len(all_symbols)} çift", key="trade_symbol_select")
            current_price = get_cached_price(symbol)
            if current_price:
                st.caption(f"Fiyat: **${current_price:,.2f}**")
        
        with col2:
            side = st.selectbox("Yön", ["LONG", "SHORT"])
            # side_emoji = "🟢" if side == "LONG" else "🔴"
            # st.caption(f"{side_emoji} {side}")
        
        with col3:
            leverage = st.number_input(
                "Kaldıraç", 
                min_value=APIConstants.MIN_LEVERAGE, 
                max_value=APIConstants.MAX_LEVERAGE, 
                value=APIConstants.DEFAULT_LEVERAGE, 
                step=1
            )
        
        with col4:
            amount_usdt = st.number_input(
                "Tutar ($)", 
                min_value=APIConstants.MIN_POSITION_SIZE, 
                value=APIConstants.DEFAULT_POSITION_SIZE, 
                step=10.0
            )

        # Row 2: TP, SL, Info
        col5, col6, col7 = st.columns([1.5, 1.5, 3])
        
        with col5:
            tp_usdt = st.number_input(
                "TP ($)", 
                min_value=0.1, 
                value=APIConstants.DEFAULT_TP_USDT, 
                step=1.0, 
                help="Kar hedefi"
            )
        
        with col6:
            sl_usdt = st.number_input(
                "SL ($)", 
                min_value=0.1, 
                value=APIConstants.DEFAULT_SL_USDT, 
                step=1.0, 
                help="Zarar limiti"
            )
            
        with col7:
            if current_price:
                contract_value = client.get_contract_value(symbol)
                contract_usdt_value = contract_value * current_price
                exact_contracts = amount_usdt / contract_usdt_value
                actual_contracts = max(0.01, round(exact_contracts, 2))
                actual_position_value = actual_contracts * contract_usdt_value
                margin_used = actual_position_value / leverage
                
                st.info(f"Marjin: **${margin_used:.2f}** | Kontrat: **{actual_contracts}**")
            else:
                st.warning("Fiyat bekleniyor...")
        
        # Row 3: Buttons
        btn_col1, btn_col2 = st.columns([3, 1])
        
        with btn_col1:
            if st.button("🚀 Pozisyon Aç", type="primary", use_container_width=True):
                with st.spinner("Açılıyor..."):
                    strategy = TradingStrategy()
                    result = strategy.open_position(
                        symbol=symbol, side=side, amount_usdt=amount_usdt,
                        leverage=leverage, tp_usdt=tp_usdt, sl_usdt=sl_usdt
                    )
                    if result.success:
                        st.success(f"✅ {result.message}")
                        st.balloons()
                    else:
                        st.error(f"❌ {result.message}")
        
        with btn_col2:
            if st.button("💾 Kaydet", use_container_width=True, help="OKX'de açmadan kaydet"):
                db = SessionLocal()
                try:
                    if not current_price:
                        st.error("Fiyat yok")
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
                        st.success(f"✅ ID: {position.id}")
                except Exception as e:
                    db.rollback()
                    st.error(f"❌ {e}")
                finally:
                    db.close()

    st.divider()
    st.markdown("##### 📋 Kayıtlı Pozisyonlar")
    
    db = SessionLocal()
    try:
        # Fetch all positions (open and closed)
        positions = db.query(Position).order_by(Position.is_open.desc(), Position.opened_at.desc()).all()
        
        if not positions:
            st.info("Kayıtlı pozisyon bulunmuyor.")
        else:
            # Prepare data for editor
            data = []
            for p in positions:
                data.append({
                    "id": p.id,
                    "symbol": p.symbol,
                    "side": p.side,
                    "leverage": p.leverage,
                    "amount_usdt": float(p.amount_usdt),
                    "tp_usdt": float(p.tp_usdt),
                    "sl_usdt": float(p.sl_usdt),
                    "is_open": p.is_open,
                    "delete": False
                })
            
            df = pd.DataFrame(data)
            
            edited_df = st.data_editor(
                df,
                width="stretch",
                hide_index=True,
                key="positions_editor",
                column_config={
                    "id": st.column_config.NumberColumn("ID", disabled=True, width="small"),
                    "symbol": st.column_config.TextColumn("Coin", disabled=True, width="small"),
                    "side": st.column_config.TextColumn("Yön", disabled=True, width="small"),
                    "leverage": st.column_config.NumberColumn("Lev", disabled=True, width="small"),
                    "amount_usdt": st.column_config.NumberColumn("Tutar ($)", min_value=0.0, step=10.0, width="small"),
                    "tp_usdt": st.column_config.NumberColumn("TP ($)", min_value=0.0, step=1.0, width="small"),
                    "sl_usdt": st.column_config.NumberColumn("SL ($)", min_value=0.0, step=1.0, width="small"),
                    "is_open": st.column_config.CheckboxColumn("Aktif?", help="İşaretliyse bot çalıştırır", width="small"),
                    "delete": st.column_config.CheckboxColumn("Sil?", width="small"),
                }
            )
            
            if st.button("💾 Değişiklikleri Kaydet", type="primary", use_container_width=True):
                changes_count = 0
                deleted_count = 0
                
                # Detect changes
                for index, row in edited_df.iterrows():
                    pos_id = row['id']
                    original_row = df[df['id'] == pos_id].iloc[0]
                    
                    # Check for deletion
                    if row['delete']:
                        db.query(Position).filter(Position.id == pos_id).delete()
                        deleted_count += 1
                        continue
                    
                    # Check for updates
                    updates = {}
                    if row['amount_usdt'] != original_row['amount_usdt']:
                        updates['amount_usdt'] = row['amount_usdt']
                    if row['tp_usdt'] != original_row['tp_usdt']:
                        updates['tp_usdt'] = row['tp_usdt']
                    if row['sl_usdt'] != original_row['sl_usdt']:
                        updates['sl_usdt'] = row['sl_usdt']
                    if row['is_open'] != original_row['is_open']:
                        updates['is_open'] = row['is_open']
                        # If closing, set closed_at
                        if not row['is_open'] and original_row['is_open']:
                            from datetime import datetime, timezone
                            updates['closed_at'] = datetime.now(timezone.utc)
                        # If opening, clear closed_at
                        elif row['is_open'] and not original_row['is_open']:
                            updates['closed_at'] = None
                    
                    if updates:
                        db.query(Position).filter(Position.id == pos_id).update(updates)
                        changes_count += 1
                
                if changes_count > 0 or deleted_count > 0:
                    db.commit()
                    st.success(f"✅ {changes_count} güncellendi, {deleted_count} silindi!")
                    st.rerun()
                else:
                    st.info("Değişiklik yok.")
                    
    except Exception as e:
        st.error(f"Hata: {e}")
    finally:
        db.close()
