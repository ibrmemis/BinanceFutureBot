from datetime import datetime
from binance_client import BinanceTestnetClient
from database import SessionLocal, Position

class Try1Strategy:
    def __init__(self):
        self.client = BinanceTestnetClient()
    
    def calculate_tp_sl_prices(
        self, 
        entry_price: float, 
        side: str, 
        tp_usdt: float, 
        sl_usdt: float, 
        quantity: float
    ) -> tuple:
        pnl_per_unit_tp = tp_usdt / quantity
        pnl_per_unit_sl = sl_usdt / quantity
        
        if side == "LONG":
            tp_price = entry_price + pnl_per_unit_tp
            sl_price = entry_price - pnl_per_unit_sl
        else:
            tp_price = entry_price - pnl_per_unit_tp
            sl_price = entry_price + pnl_per_unit_sl
        
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
            return False, "Binance API anahtarları yapılandırılmamış", None
        
        self.client.set_hedge_mode()
        self.client.set_leverage(symbol, leverage)
        self.client.set_margin_type(symbol, "CROSSED")
        
        current_price = self.client.get_symbol_price(symbol)
        if not current_price:
            return False, "Fiyat alınamadı", None
        
        quantity = self.client.calculate_quantity(symbol, amount_usdt, leverage, current_price)
        if quantity == 0:
            return False, "Geçersiz miktar", None
        
        position_side = "LONG" if side == "LONG" else "SHORT"
        order_side = "BUY" if side == "LONG" else "SELL"
        
        order = self.client.open_market_order(
            symbol=symbol,
            side=order_side,
            quantity=quantity,
            position_side=position_side
        )
        
        if not order:
            return False, "Emir açılamadı", None
        
        entry_price = float(order.get('avgPrice', current_price))
        
        tp_price, sl_price = self.calculate_tp_sl_prices(
            entry_price, side, tp_usdt, sl_usdt, quantity
        )
        
        tp_side = "SELL" if side == "LONG" else "BUY"
        sl_side = "SELL" if side == "LONG" else "BUY"
        
        tp_order = self.client.set_take_profit(
            symbol=symbol,
            side=tp_side,
            position_side=position_side,
            quantity=quantity,
            stop_price=tp_price
        )
        
        sl_order = self.client.set_stop_loss(
            symbol=symbol,
            side=sl_side,
            position_side=position_side,
            quantity=quantity,
            stop_price=sl_price
        )
        
        tp_order_id = str(tp_order['orderId']) if tp_order else None
        sl_order_id = str(sl_order['orderId']) if sl_order else None
        
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
                order_id=str(order['orderId']),
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
        finally:
            db.close()
        
        return True, f"Pozisyon açıldı: {symbol} {side} {quantity} @ {entry_price}", position_id
    
    def check_and_update_positions(self):
        db = SessionLocal()
        try:
            open_positions = db.query(Position).filter(Position.is_open == True).all()
            
            for pos in open_positions:
                if pos.position_side:
                    position_side = pos.position_side
                else:
                    position_side = "LONG" if pos.side == "LONG" else "SHORT"
                binance_pos = self.client.get_position(pos.symbol, position_side)
                
                if binance_pos and float(binance_pos['positionAmt']) == 0:
                    db.query(Position).filter(Position.id == pos.id).update({
                        'is_open': False,
                        'closed_at': datetime.utcnow()
                    })
                    db.flush()
                    
                    realized_pnl = 0.0
                    close_reason = "MANUAL"
                    found_close_trade = False
                    
                    tp_filled = False
                    sl_filled = False
                    
                    if pos.tp_order_id:
                        tp_order = self.client.get_order(pos.symbol, pos.tp_order_id)
                        if tp_order and tp_order.get('status') == 'FILLED':
                            tp_filled = True
                            close_reason = "TP"
                    
                    if pos.sl_order_id:
                        sl_order = self.client.get_order(pos.symbol, pos.sl_order_id)
                        if sl_order and sl_order.get('status') == 'FILLED':
                            sl_filled = True
                            close_reason = "SL"
                    
                    trades = self.client.get_account_trades(pos.symbol, limit=100)
                    
                    position_opened_ts = int(pos.opened_at.timestamp() * 1000)
                    
                    for trade in reversed(trades):
                        trade_time = int(trade.get('time', 0))
                        
                        if trade_time < position_opened_ts:
                            continue
                        
                        if trade['positionSide'] == position_side:
                            trade_order_id = str(trade.get('orderId'))
                            
                            if pos.tp_order_id and trade_order_id == pos.tp_order_id:
                                realized_pnl = float(trade.get('realizedPnl', 0))
                                close_reason = "TP"
                                found_close_trade = True
                                break
                            elif pos.sl_order_id and trade_order_id == pos.sl_order_id:
                                realized_pnl = float(trade.get('realizedPnl', 0))
                                close_reason = "SL"
                                found_close_trade = True
                                break
                    
                    if not found_close_trade and (tp_filled or sl_filled):
                        for trade in reversed(trades):
                            trade_time = int(trade.get('time', 0))
                            if trade_time >= position_opened_ts and trade['positionSide'] == position_side:
                                if float(trade.get('realizedPnl', 0)) != 0:
                                    realized_pnl += float(trade['realizedPnl'])
                    
                    if not found_close_trade and not tp_filled and not sl_filled:
                        for trade in reversed(trades):
                            trade_time = int(trade.get('time', 0))
                            if trade_time >= position_opened_ts and trade['positionSide'] == position_side:
                                if float(trade.get('realizedPnl', 0)) != 0:
                                    realized_pnl += float(trade['realizedPnl'])
                                    found_close_trade = True
                    
                    db.query(Position).filter(Position.id == pos.id).update({
                        'pnl': realized_pnl,
                        'close_reason': close_reason
                    })
                    
                    db.commit()
            
        finally:
            db.close()
