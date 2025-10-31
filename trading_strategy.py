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
        parent_position_id: int = None,
        reopen_count: int = 0
    ) -> tuple[bool, str, int]:
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
        
        self.client.set_take_profit(
            symbol=symbol,
            side=tp_side,
            position_side=position_side,
            quantity=quantity,
            stop_price=tp_price
        )
        
        self.client.set_stop_loss(
            symbol=symbol,
            side=sl_side,
            position_side=position_side,
            quantity=quantity,
            stop_price=sl_price
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
                order_id=order['orderId'],
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
                position_side = "LONG" if pos.side == "LONG" else "SHORT"
                binance_pos = self.client.get_position(pos.symbol, position_side)
                
                if binance_pos and float(binance_pos['positionAmt']) == 0:
                    pos.is_open = False
                    pos.closed_at = datetime.utcnow()
                    
                    unrealized_pnl = float(binance_pos.get('unRealizedProfit', 0))
                    pos.pnl = unrealized_pnl
                    
                    if unrealized_pnl > 0:
                        pos.close_reason = "TP"
                    elif unrealized_pnl < 0:
                        pos.close_reason = "SL"
                    else:
                        pos.close_reason = "MANUAL"
                    
                    db.commit()
            
        finally:
            db.close()
