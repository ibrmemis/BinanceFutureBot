from datetime import datetime
from database import SessionLocal, PositionHistory
from okx_client import OKXTestnetClient

def sync_okx_position_history():
    """
    Fetch position history from OKX and save to database with pagination
    Returns: (synced_count, error_message)
    """
    try:
        client = OKXTestnetClient()
        
        if not client.is_configured():
            return 0, "OKX client not configured"
        
        db = SessionLocal()
        synced_count = 0
        total_pages = 0
        before_cursor = None
        last_cursor = None
        
        try:
            # Pagination loop - fetch all historical positions
            while True:
                # Fetch positions history from OKX with pagination
                history_data = client.get_positions_history(
                    inst_type="SWAP", 
                    limit=100,
                    before=before_cursor
                )
                
                if not history_data:
                    if total_pages == 0:
                        return 0, "No history data from OKX"
                    else:
                        break
                
                total_pages += 1
                print(f"📄 Page {total_pages}: Fetched {len(history_data)} positions (cursor: {before_cursor})")
                
                for pos in history_data:
                    pos_id = pos.get('posId')
                    
                    if not pos_id:
                        continue
                    
                    # Check if already exists (using pos_id + c_time for uniqueness)
                    c_time_ms = int(pos.get('cTime', 0))
                    c_time_dt = datetime.fromtimestamp(c_time_ms / 1000) if c_time_ms else None
                    
                    existing = db.query(PositionHistory).filter(
                        PositionHistory.pos_id == pos_id,
                        PositionHistory.c_time == c_time_dt
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
                        existing.leverage = int(float(pos.get('lever', 1)))
                        existing.close_type = pos.get('type', '')
                        
                        # Convert timestamps (OKX uses milliseconds)
                        u_time_ms = int(pos.get('uTime', 0))
                        existing.u_time = datetime.fromtimestamp(u_time_ms / 1000) if u_time_ms else None
                    else:
                        # Create new record
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
                            leverage=int(float(pos.get('lever', 1))),
                            close_type=pos.get('type', ''),
                            c_time=c_time_dt,
                            u_time=datetime.fromtimestamp(u_time_ms / 1000) if u_time_ms else None
                        )
                        db.add(new_history)
                    
                    synced_count += 1
                
                # Check if we should continue pagination
                if len(history_data) < 100:
                    print(f"✅ Reached end of history (last page had {len(history_data)} items)")
                    break
                
                # Update cursor for next page - use posId of oldest record
                # OKX API returns records from newest to oldest, so last record is oldest
                before_cursor = history_data[-1].get('posId')
                
                if not before_cursor:
                    print("⚠️ No posId found for pagination, stopping")
                    break
                
                # Prevent infinite loop only if we got exactly 100 records AND cursor hasn't changed
                # This indicates API is returning same page repeatedly
                if before_cursor == last_cursor and len(history_data) == 100:
                    print("⚠️ API returned same cursor with 100 records, stopping to prevent infinite loop")
                    break
                
                last_cursor = before_cursor
            
            db.commit()
            print(f"✅ Synced {synced_count} total positions across {total_pages} pages")
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
