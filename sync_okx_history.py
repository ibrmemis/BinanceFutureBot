from datetime import datetime
from database import SessionLocal, PositionHistory
from okx_client import OKXTestnetClient

def sync_okx_position_history():
    """
    Fetch position history from OKX and save to database
    Returns: (synced_count, error_message)
    """
    try:
        client = OKXTestnetClient()
        
        if not client.is_configured():
            return 0, "OKX client not configured"
        
        # Fetch positions history from OKX
        history_data = client.get_positions_history(inst_type="SWAP", limit=100)
        
        if not history_data:
            return 0, "No history data from OKX"
        
        db = SessionLocal()
        synced_count = 0
        
        try:
            for pos in history_data:
                pos_id = pos.get('posId')
                
                if not pos_id:
                    continue
                
                # Check if already exists
                existing = db.query(PositionHistory).filter(
                    PositionHistory.pos_id == pos_id
                ).first()
                
                if existing:
                    # Update existing record
                    existing.inst_id = pos.get('instId', '')
                    existing.mgn_mode = pos.get('mgnMode', '')
                    existing.pos_side = pos.get('direction', '')
                    existing.open_avg_px = float(pos.get('openAvgPx', 0))
                    existing.close_avg_px = float(pos.get('closeAvgPx', 0))
                    existing.open_max_pos = float(pos.get('openMaxPos', 0))
                    existing.close_total_pos = float(pos.get('closeTotalPos', 0))
                    existing.pnl = float(pos.get('pnl', 0))
                    existing.pnl_ratio = float(pos.get('pnlRatio', 0))
                    existing.leverage = int(pos.get('lever', 1))
                    existing.close_type = pos.get('type', '')
                    
                    # Convert timestamps (OKX uses milliseconds)
                    c_time_ms = int(pos.get('cTime', 0))
                    u_time_ms = int(pos.get('uTime', 0))
                    existing.c_time = datetime.fromtimestamp(c_time_ms / 1000) if c_time_ms else None
                    existing.u_time = datetime.fromtimestamp(u_time_ms / 1000) if u_time_ms else None
                else:
                    # Create new record
                    c_time_ms = int(pos.get('cTime', 0))
                    u_time_ms = int(pos.get('uTime', 0))
                    
                    new_history = PositionHistory(
                        inst_id=pos.get('instId', ''),
                        pos_id=pos_id,
                        mgn_mode=pos.get('mgnMode', ''),
                        pos_side=pos.get('direction', ''),
                        open_avg_px=float(pos.get('openAvgPx', 0)),
                        close_avg_px=float(pos.get('closeAvgPx', 0)),
                        open_max_pos=float(pos.get('openMaxPos', 0)),
                        close_total_pos=float(pos.get('closeTotalPos', 0)),
                        pnl=float(pos.get('pnl', 0)),
                        pnl_ratio=float(pos.get('pnlRatio', 0)),
                        leverage=int(pos.get('lever', 1)),
                        close_type=pos.get('type', ''),
                        c_time=datetime.fromtimestamp(c_time_ms / 1000) if c_time_ms else None,
                        u_time=datetime.fromtimestamp(u_time_ms / 1000) if u_time_ms else None
                    )
                    db.add(new_history)
                
                synced_count += 1
            
            db.commit()
            return synced_count, None
            
        except Exception as e:
            db.rollback()
            return 0, f"Database error: {str(e)}"
        finally:
            db.close()
            
    except Exception as e:
        return 0, f"Sync error: {str(e)}"

if __name__ == "__main__":
    count, error = sync_okx_position_history()
    if error:
        print(f"❌ Error: {error}")
    else:
        print(f"✅ Synced {count} positions from OKX history")
