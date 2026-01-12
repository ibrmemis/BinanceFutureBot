import streamlit as st
import pandas as pd
from database import SessionLocal, Position
from services import get_cached_client

def show_orders_page():
    # Auto-refresh logic
    try:
        from streamlit_autorefresh import st_autorefresh
        # Refresh every 30 seconds
        st_autorefresh(interval=30000, key="orders_autorefresh")
    except ImportError:
        pass

    col_header, col_refresh = st.columns([6, 1])
    with col_header:
        st.caption("Açık emirleri yönetin. 'Botu Durdur' işaretlenirse o pozisyon için TP/SL yenilenmez.")
    with col_refresh:
        if st.button("🔄", help="Yenile", use_container_width=True, key="refresh_orders"):
            st.rerun()

    client = get_cached_client()
    
    if not client.is_configured():
        st.error("API yapılandırılmamış.")
        return
    
    with st.spinner("Yükleniyor..."):
        algo_orders = client.get_all_open_orders()
        positions = client.get_all_positions()
    
    if algo_orders is None:
        st.error("Emirler alınamadı.")
        return

    # Map positions for price info
    position_map = {}
    for pos in positions:
        inst_id = pos.get('instId', '')
        pos_side = pos.get('posSide', '')
        entry_px = pos.get('entryPrice', '0')
        try:
            position_map[f"{inst_id}_{pos_side}"] = float(entry_px)
        except:
            pass
    
    if not algo_orders:
        st.info("Aktif emir yok.")
    else:
        # Prepare data for editor
        data = []
        db = SessionLocal()
        try:
            for order in algo_orders:
                inst_id = order.get('instId', '')
                algo_id = order.get('algoId', '')
                pos_side = order.get('posSide', '')
                trigger_px = order.get('triggerPx', '0')
                
                # Determine Type (TP/SL)
                entry_price = position_map.get(f"{inst_id}_{pos_side}", 0)
                trigger_type = "?"
                if entry_price > 0:
                    try:
                        t_px = float(trigger_px)
                        if pos_side == "long":
                            trigger_type = "TP" if t_px > entry_price else "SL"
                        elif pos_side == "short":
                            trigger_type = "TP" if t_px < entry_price else "SL"
                    except:
                        pass
                
                # Determine DB Status
                symbol_clean = inst_id.replace('-USDT-SWAP', '').replace('-', '') + 'USDT'
                position_side_db = "long" if pos_side == "long" else "short"
                
                pos_db = db.query(Position).filter(
                    Position.symbol == symbol_clean,
                    Position.position_side == position_side_db,
                    Position.is_open == True
                ).first()
                
                orders_disabled = False
                if pos_db:
                    orders_disabled = getattr(pos_db, 'orders_disabled', False)
                
                data.append({
                    "algo_id": algo_id,
                    "inst_id": inst_id,
                    "symbol": inst_id.replace("-USDT-SWAP", ""),
                    "side": pos_side.upper(),
                    "type": trigger_type,
                    "price": float(trigger_px) if trigger_px else 0,
                    "orders_disabled": orders_disabled, # Checkbox value
                    "delete": False # Checkbox value
                })
        finally:
            db.close()
        
        df = pd.DataFrame(data)
        
        edited_df = st.data_editor(
            df,
            width="stretch",
            hide_index=True,
            key="orders_editor",
            column_config={
                "algo_id": None,
                "inst_id": None,
                "symbol": st.column_config.TextColumn("Coin", disabled=True, width="small"),
                "side": st.column_config.TextColumn("Yön", disabled=True, width="small"),
                "type": st.column_config.TextColumn("Tür", disabled=True, width="small"),
                "price": st.column_config.NumberColumn("Fiyat", disabled=True, format="$%.4f", width="small"),
                "orders_disabled": st.column_config.CheckboxColumn("Botu Durdur?", help="İşaretliyse bot bu pozisyonu yönetmez", width="small"),
                "delete": st.column_config.CheckboxColumn("İptal Et?", help="Emri sil", width="small"),
            }
        )
        
        if st.button("💾 Değişiklikleri Uygula", type="primary", use_container_width=True):
            cancelled_count = 0
            disabled_count = 0
            db = SessionLocal()
            try:
                for index, row in edited_df.iterrows():
                    algo_id = row['algo_id']
                    original_row = df[df['algo_id'] == algo_id].iloc[0]
                    
                    # 1. Handle Deletion
                    if row['delete']:
                        symbol_base = row['inst_id'].replace('-USDT-SWAP', 'USDT')
                        if client.cancel_algo_order(symbol_base, algo_id):
                            cancelled_count += 1
                    
                    # 2. Handle Status Change (only if not deleted)
                    if not row['delete'] and row['orders_disabled'] != original_row['orders_disabled']:
                        # Find position in DB
                        symbol_clean = row['inst_id'].replace('-USDT-SWAP', '').replace('-', '') + 'USDT'
                        position_side_db = "long" if row['side'].lower() == "long" else "short"
                        
                        pos_db = db.query(Position).filter(
                            Position.symbol == symbol_clean,
                            Position.position_side == position_side_db,
                            Position.is_open == True
                        ).first()
                        
                        if pos_db:
                            pos_db.orders_disabled = row['orders_disabled']
                            disabled_count += 1
                
                db.commit()
                
                if cancelled_count > 0 or disabled_count > 0:
                    st.success(f"✅ {cancelled_count} emir iptal edildi, {disabled_count} durum güncellendi.")
                    st.rerun()
                else:
                    st.info("Değişiklik yok.")
                    
            except Exception as e:
                db.rollback()
                st.error(f"Hata: {e}")
            finally:
                db.close()

    st.divider()
    with st.expander("➕ Manuel Emir Ekle"):
        c1, c2, c3, c4 = st.columns([2, 1.5, 1.5, 1.5])
        with c1:
            ms = st.selectbox("Coin", ["SOLUSDT", "BTCUSDT", "ETHUSDT"], key="ms")
        with c2:
            mps = st.selectbox("Yön", ["long", "short"], key="mps")
        with c3:
            mot = st.selectbox("Tür", ["TP", "SL"], key="mot")
        with c4:
            msz = st.number_input("Adet", 1, 1000, 1, key="msz")
            
        c5, c6 = st.columns([2, 1])
        with c5:
            mtp = st.number_input("Fiyat", 0.0001, value=100.0, step=0.1, key="mtp")
        with c6:
            if st.button("Ekle", use_container_width=True):
                with st.spinner("..."):
                    close_side = "sell" if mps == "long" else "buy"
                    inst_id = client.convert_symbol_to_okx(ms)
                    try:
                        res = client.trade_api.place_algo_order(
                            instId=inst_id, tdMode="cross", side=close_side, posSide=mps,
                            ordType="trigger", sz=str(msz), triggerPx=str(round(mtp, 4)), orderPx="-1"
                        )
                        if res.get('code') == '0':
                            st.success("✅")
                            st.rerun()
                        else:
                            st.error(res.get('msg'))
                    except Exception as e:
                        st.error(e)
