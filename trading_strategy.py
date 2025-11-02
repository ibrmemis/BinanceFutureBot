from datetime import datetime
from okx_client import OKXTestnetClient
from database import SessionLocal, Position

class Try1Strategy:
    def __init__(self):
        self.client = OKXTestnetClient()
    
    def calculate_quantity_for_usdt(
        self,
        amount_usdt: float,
        leverage: int,
        current_price: float
    ) -> int:
        total_value = amount_usdt * leverage
        contracts = int(total_value / current_price)
        return max(1, contracts)
    
    def calculate_tp_sl_prices(
        self,
        entry_price: float,
        side: str,
        tp_usdt: float,
        sl_usdt: float,
        quantity: int
    ) -> tuple[float, float]:
        pnl_per_contract_tp = tp_usdt / quantity
        pnl_per_contract_sl = sl_usdt / quantity
        
        if side == "LONG":
            tp_price = entry_price + pnl_per_contract_tp
            sl_price = entry_price - pnl_per_contract_sl
        else:
            tp_price = entry_price - pnl_per_contract_tp
            sl_price = entry_price + pnl_per_contract_sl
        
        return tp_price, sl_price
    
    def open_position(
        self,
        symbol: str,
        side: str,
        amount_usdt: float,
        leverage: int,
        tp_usdt: float,
        sl_usdt: float,
        parent_position_id: int | None = None,
        reopen_count: int = 0
    ) -> tuple[bool, str, int | None]:
        if not self.client.is_configured():
            return False, "OKX API anahtarları yapılandırılmamış", None
        
        self.client.set_position_mode("long_short_mode")
        
        position_side = "long" if side == "LONG" else "short"
        self.client.set_leverage(symbol, leverage, position_side)
        
        current_price = self.client.get_symbol_price(symbol)
        if not current_price:
            return False, "Fiyat alınamadı", None
        
        quantity = self.calculate_quantity_for_usdt(amount_usdt, leverage, current_price)
        if quantity == 0:
            return False, "Geçersiz miktar", None
        
        order = self.client.place_market_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            position_side=position_side
        )
        
        if not order:
            return False, "Emir açılamadı", None
        
        entry_price = current_price
        
        import time
        time.sleep(2)
        
        okx_position = self.client.get_position(symbol, position_side)
        pos_id = okx_position.get('posId') if okx_position else None
        
        tp_price, sl_price = self.calculate_tp_sl_prices(
            entry_price=entry_price,
            side=side,
            tp_usdt=tp_usdt,
            sl_usdt=sl_usdt,
            quantity=quantity
        )
        
        tp_order_id, sl_order_id = self.client.place_tp_sl_orders(
            symbol=symbol,
            side=side,
            quantity=quantity,
            entry_price=entry_price,
            tp_price=tp_price,
            sl_price=sl_price,
            position_side=position_side
        )
        
        db = SessionLocal()
        try:
            position = Position(
                symbol=symbol,
                side=side,
                amount_usdt=amount_usdt,
                leverage=leverage,
                tp_usdt=tp_usdt,
                sl_usdt=sl_usdt,
                entry_price=entry_price,
                quantity=quantity,
                order_id=str(order.get('orderId')),
                position_id=pos_id,
                position_side=position_side,
                tp_order_id=tp_order_id,
                sl_order_id=sl_order_id,
                is_open=True,
                reopen_count=reopen_count,
                parent_position_id=parent_position_id
            )
            db.add(position)
            db.commit()
            db.refresh(position)
            
            position_id = position.id
            
            tp_sl_msg = ""
            if tp_order_id and sl_order_id:
                tp_sl_msg = f" (TP: ${tp_price:.4f}, SL: ${sl_price:.4f})"
            elif tp_order_id:
                tp_sl_msg = f" (TP: ${tp_price:.4f})"
            elif sl_order_id:
                tp_sl_msg = f" (SL: ${sl_price:.4f})"
            
            return True, f"Pozisyon açıldı: {symbol} {side} {quantity} kontrat @ ${entry_price:.4f}{tp_sl_msg}", position_id
        except Exception as e:
            db.rollback()
            return False, f"Veritabanı hatası: {e}", None
        finally:
            db.close()
    
    def check_and_update_positions(self):
        if not self.client.is_configured():
            print("OKX client not configured")
            return
        
        db = SessionLocal()
        try:
            open_positions = db.query(Position).filter(Position.is_open == True).all()
            
            for pos in open_positions:
                if pos.position_side is not None:
                    position_side = pos.position_side
                else:
                    position_side = "long" if pos.side == "LONG" else "short"
                
                okx_pos = self.client.get_position(pos.symbol, position_side)
                
                if not okx_pos:
                    print(f"Could not fetch position from OKX: {pos.symbol} {position_side}")
                    continue
                
                okx_pos_id = okx_pos.get('posId')
                okx_pos_amt = float(okx_pos.get('positionAmt', 0))
                
                if pos.position_id:
                    if okx_pos_id and okx_pos_id != pos.position_id and okx_pos_amt != 0:
                        print(f"Position ID mismatch: DB={pos.position_id}, OKX={okx_pos_id}")
                        continue
                
                if okx_pos_amt == 0:
                    db.query(Position).filter(Position.id == pos.id).update({
                        'is_open': False,
                        'closed_at': datetime.utcnow()
                    })
                    db.flush()
                    
                    realized_pnl = 0.0
                    close_reason = "MANUAL"
                    
                    trades = self.client.get_account_trades(pos.symbol, limit=100)
                    
                    if trades and len(trades) > 0:
                        position_opened_ts = int(pos.opened_at.timestamp() * 1000)
                        
                        for trade in trades:
                            trade_time = int(trade.get('ts', 0))
                            
                            if trade_time < position_opened_ts:
                                continue
                            
                            trade_side = trade.get('side', '')
                            trade_pos_side = trade.get('posSide', '')
                            
                            if trade_pos_side == position_side:
                                pnl = float(trade.get('fillPnl', 0))
                                realized_pnl += pnl
                        
                        if pos.tp_usdt is not None and realized_pnl >= float(pos.tp_usdt):
                            close_reason = "TP"
                        elif pos.sl_usdt is not None and realized_pnl <= -float(pos.sl_usdt):
                            close_reason = "SL"
                    
                    db.query(Position).filter(Position.id == pos.id).update({
                        'pnl': realized_pnl,
                        'close_reason': close_reason
                    })
                    
                    db.commit()
                    print(f"Position closed: {pos.symbol} {pos.side} - PnL: ${realized_pnl:.2f} ({close_reason})")
                
                elif okx_pos:
                    unrealized_pnl = float(okx_pos.get('unrealizedProfit', 0))
                    current_entry = float(okx_pos.get('entryPrice', 0))
                    
                    if current_entry > 0 and pos.entry_price is not None and abs(current_entry - float(pos.entry_price)) > 0.01:
                        db.query(Position).filter(Position.id == pos.id).update({
                            'entry_price': current_entry
                        })
                        db.commit()
                    
                    if pos.tp_usdt is not None and unrealized_pnl >= float(pos.tp_usdt):
                        print(f"TP target reached for {pos.symbol} {pos.side}: ${unrealized_pnl:.2f}")
                    
                    if pos.sl_usdt is not None and unrealized_pnl <= -float(pos.sl_usdt):
                        print(f"SL target reached for {pos.symbol} {pos.side}: ${unrealized_pnl:.2f}")
            
        except Exception as e:
            print(f"Error checking positions: {e}")
            db.rollback()
        finally:
            db.close()
