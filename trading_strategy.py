from datetime import datetime, timezone
from typing import Tuple, Optional, Union
from dataclasses import dataclass
from okx_client import OKXTestnetClient
from database_utils import get_db_session
from database import Position, SessionLocal
from constants import (
    OrderSide, PositionSide, TradingConstants, 
    ErrorMessages, SuccessMessages, TradingMode, OrderType
)


@dataclass
class PositionParams:
    """Data class for position parameters"""
    symbol: str
    side: str
    amount_usdt: float
    leverage: int
    tp_usdt: float
    sl_usdt: float
    parent_position_id: Optional[int] = None


@dataclass
class PositionResult:
    """Data class for position operation results"""
    success: bool
    message: str
    position_id: Optional[int] = None
    order_id: Optional[str] = None


class TradingCalculator:
    """Separate class for trading calculations"""
    
    @staticmethod
    def calculate_quantity_for_usdt(
        amount_usdt: float,
        leverage: int,
        current_price: float,
        contract_value: float,
        lot_size: float
    ) -> float:
        """Calculate contract quantity for given USDT amount"""
        contract_usdt_value = contract_value * current_price
        exact_contracts = amount_usdt / contract_usdt_value

        # Round to 2 decimal places for OKX precision
        return round(exact_contracts, 2)
    
    @staticmethod
    def calculate_tp_sl_prices(
        entry_price: float,
        side: str,
        tp_usdt: float,
        sl_usdt: float,
        quantity: float,
        contract_value: float
    ) -> Tuple[float, float]:
        """Calculate TP/SL prices based on USDT amounts"""
        crypto_amount = quantity * contract_value
        
        price_change_tp = tp_usdt / crypto_amount
        price_change_sl = sl_usdt / crypto_amount
        
        if side == OrderSide.LONG:
            tp_price = entry_price + price_change_tp
            sl_price = entry_price - price_change_sl
        else:
            tp_price = entry_price - price_change_tp
            sl_price = entry_price + price_change_sl
        
        return tp_price, sl_price


class ModernTradingStrategy:
    """
    Modern trading strategy with improved error handling and type safety
    """
    
    def __init__(self):
        self.client = OKXTestnetClient()
        self.calculator = TradingCalculator()
    
    def _validate_position_params(self, params: PositionParams) -> Optional[str]:
        """Validate position parameters"""
        if not self.client.is_configured():
            return ErrorMessages.API_NOT_CONFIGURED
        
        if params.amount_usdt < TradingConstants.MIN_POSITION_SIZE:
            return ErrorMessages.INVALID_POSITION_SIZE
        
        if params.leverage < 1 or params.leverage > TradingConstants.MAX_LEVERAGE:
            return f"Leverage must be between 1 and {TradingConstants.MAX_LEVERAGE}"
        
        return None
    
    def open_position(
        self,
        symbol: str,
        side: str,
        amount_usdt: float,
        leverage: int,
        tp_usdt: float,
        sl_usdt: float,
        parent_position_id: Optional[int] = None,
        save_to_db: bool = True
    ) -> PositionResult:
        """
        Open a new position with modern error handling
        """
        params = PositionParams(
            symbol=symbol,
            side=side,
            amount_usdt=amount_usdt,
            leverage=leverage,
            tp_usdt=tp_usdt,
            sl_usdt=sl_usdt,
            parent_position_id=parent_position_id
        )
        
        # Validate parameters
        validation_error = self._validate_position_params(params)
        if validation_error:
            return PositionResult(False, validation_error)
        
        print(f"LOG: {symbol} için {side} pozisyonu açılıyor... Büyüklük: {amount_usdt} USDT, Kaldıraç: {leverage}x")
        
        # Set position mode and leverage
        self.client.set_position_mode("long_short_mode")
        position_side = PositionSide.LONG if side == OrderSide.LONG else PositionSide.SHORT
        self.client.set_leverage(symbol, leverage, position_side)
        
        # Get current price
        current_price = self.client.get_symbol_price(symbol)
        if not current_price:
            return PositionResult(False, ErrorMessages.PRICE_NOT_AVAILABLE)
        
        # Calculate quantity
        contract_value = self.client.get_contract_value(symbol)
        lot_size = self.client.get_lot_size(symbol)
        
        quantity = self.calculator.calculate_quantity_for_usdt(
            amount_usdt, leverage, current_price, contract_value, lot_size
        )
        
        if quantity < 1:
            return PositionResult(False, "Geçersiz miktar (minimum 1 kontrat)")
        
        # Place market order
        order = self.client.place_market_order(symbol, side, quantity, position_side)
        if not order:
            return PositionResult(False, ErrorMessages.ORDER_FAILED)
        
        print(f"LOG: {symbol} emri başarıyla açıldı. Giriş Fiyatı: ${current_price:.4f}")
        
        # Get position ID from OKX
        import time
        time.sleep(TradingConstants.ORDER_DELAY_SECONDS)
        
        okx_position = self.client.get_position(symbol, position_side)
        pos_id = okx_position.get('posId') if okx_position else None
        
        # Calculate TP/SL prices
        tp_price, sl_price = self.calculator.calculate_tp_sl_prices(
            current_price, side, tp_usdt, sl_usdt, quantity, contract_value
        )
        
        # Place TP/SL orders
        tp_order_id, sl_order_id = self._place_tp_sl_orders(
            symbol, side, quantity, current_price, tp_price, sl_price, position_side
        )
        
        # Save to database if requested
        if save_to_db:
            return self._save_position_to_db(
                params, current_price, quantity, order.get('orderId'), 
                pos_id, position_side, tp_order_id, sl_order_id
            )
        
        tp_sl_msg = self._format_tp_sl_message(tp_price, sl_price, tp_order_id, sl_order_id)
        message = f"Pozisyon açıldı: {symbol} {side} {quantity} kontrat @ ${current_price:.4f}{tp_sl_msg}"
        
        return PositionResult(True, message, order_id=order.get('orderId'))
    
    def _place_tp_sl_orders(
        self, symbol: str, side: str, quantity: float, 
        current_price: float, tp_price: float, sl_price: float, 
        position_side: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Place TP and SL orders with proper validation"""
        import time
        
        tp_order_id = None
        sl_order_id = None
        
        # Place SL order first
        if sl_price and sl_price > 0:
            is_valid_sl = (
                (side == OrderSide.LONG and sl_price < current_price) or 
                (side == OrderSide.SHORT and sl_price > current_price)
            )
            
            if is_valid_sl:
                sl_order_id = self._place_algo_order(
                    symbol, side, quantity, sl_price, position_side, "SL"
                )
        
        # Wait before placing TP order
        time.sleep(TradingConstants.TP_ORDER_DELAY_SECONDS)
        
        # Place TP order
        if tp_price and tp_price > 0:
            is_valid_tp = (
                (side == OrderSide.LONG and tp_price > current_price) or 
                (side == OrderSide.SHORT and tp_price < current_price)
            )
            
            if is_valid_tp:
                tp_order_id = self._place_algo_order(
                    symbol, side, quantity, tp_price, position_side, "TP"
                )
        
        return tp_order_id, sl_order_id
    
    def _place_algo_order(
        self, symbol: str, side: str, quantity: float, 
        trigger_price: float, position_side: str, order_type: str
    ) -> Optional[str]:
        """Place a single algo order (TP or SL)"""
        if not self.client.trade_api:
            return None
        
        try:
            inst_id = self.client.convert_symbol_to_okx(symbol)
            close_side = OrderSide.SELL if side == OrderSide.LONG else OrderSide.BUY
            tick_size = self.client.get_tick_size(symbol)
            formatted_price = self.client.format_price(trigger_price, tick_size)
            
            result = self.client.trade_api.place_algo_order(
                instId=inst_id,
                tdMode=TradingMode.CROSS,
                side=close_side,
                posSide=position_side,
                ordType=OrderType.TRIGGER,
                sz=str(quantity),
                triggerPx=formatted_price,
                orderPx="-1"
            )
            
            if result.get('code') == '0' and result.get('data'):
                order_id = result['data'][0]['algoId']
                print(f"{order_type} order placed: {order_id} @ ${formatted_price}")
                return order_id
            else:
                print(f"❌ {order_type} order FAILED: {result.get('msg', 'Unknown error')}")
                return None
                
        except Exception as e:
            print(f"❌ {order_type} order exception: {e}")
            return None
    
    def _save_position_to_db(
        self, params: PositionParams, entry_price: float, quantity: float,
        order_id: Optional[str], pos_id: Optional[str], position_side: str,
        tp_order_id: Optional[str], sl_order_id: Optional[str]
    ) -> PositionResult:
        """Save position to database"""
        try:
            with get_db_session() as db:
                position = Position(
                    symbol=params.symbol,
                    side=params.side,
                    amount_usdt=params.amount_usdt,
                    leverage=params.leverage,
                    tp_usdt=params.tp_usdt,
                    sl_usdt=params.sl_usdt,
                    original_tp_usdt=params.tp_usdt,
                    original_sl_usdt=params.sl_usdt,
                    entry_price=entry_price,
                    quantity=quantity,
                    order_id=order_id,
                    position_id=pos_id,
                    position_side=position_side,
                    tp_order_id=tp_order_id,
                    sl_order_id=sl_order_id,
                    is_open=True,
                    parent_position_id=params.parent_position_id
                )
                db.add(position)
                db.commit()
                db.refresh(position)
                
                tp_sl_msg = self._format_tp_sl_message(
                    None, None, tp_order_id, sl_order_id
                )
                message = f"{SuccessMessages.POSITION_OPENED}: {params.symbol} {params.side} {quantity} kontrat @ ${entry_price:.4f}{tp_sl_msg}"
                
                return PositionResult(True, message, position.id)
                
        except Exception as e:
            return PositionResult(False, f"Veritabanı hatası: {e}")
    
    @staticmethod
    def _format_tp_sl_message(
        tp_price: Optional[float], sl_price: Optional[float],
        tp_order_id: Optional[str], sl_order_id: Optional[str]
    ) -> str:
        """Format TP/SL message for display"""
        parts = []
        if tp_order_id and tp_price:
            parts.append(f"TP: ${tp_price:.4f}")
        elif tp_order_id:
            parts.append("TP: Placed")
        
        if sl_order_id and sl_price:
            parts.append(f"SL: ${sl_price:.4f}")
        elif sl_order_id:
            parts.append("SL: Placed")
        
        return f" ({', '.join(parts)})" if parts else ""


# Backward compatibility alias
Try1Strategy = ModernTradingStrategy


class Try1Strategy(ModernTradingStrategy):
    """Legacy class name for backward compatibility"""
    
    def calculate_quantity_for_usdt(
        self,
        amount_usdt: float,
        leverage: int,
        current_price: float,
        symbol: str
    ) -> float:
        """Calculate contract quantity for given USDT amount - wrapper method"""
        contract_value = self.client.get_contract_value(symbol)
        lot_size = self.client.get_lot_size(symbol)
        
        return self.calculator.calculate_quantity_for_usdt(
            amount_usdt, leverage, current_price, contract_value, lot_size
        )
    
    def calculate_tp_sl_prices(
        self,
        entry_price: float,
        side: str,
        tp_usdt: float,
        sl_usdt: float,
        quantity: float,
        symbol: str
    ) -> Tuple[float, float]:
        """Calculate TP/SL prices - wrapper method"""
        contract_value = self.client.get_contract_value(symbol)
        
        return self.calculator.calculate_tp_sl_prices(
            entry_price, side, tp_usdt, sl_usdt, quantity, contract_value
        )
    
    def execute_recovery(
        self,
        position_db_id: int,
        add_amount_usdt: float,
        new_tp_usdt: float,
        new_sl_usdt: float
    ) -> tuple[bool, str]:
        """
        Execute recovery for a position:
        1. Cancel all TP/SL orders for this position
        2. Add to the position with add_amount_usdt
        3. Set new TP/SL based on the total new position size
        
        Returns: (success, message)
        """
        from datetime import timezone
        
        db = SessionLocal()
        try:
            pos = db.query(Position).filter(Position.id == position_db_id).first()
            if not pos:
                return False, "Pozisyon bulunamadı"
            
            if not pos.is_open:
                return False, "Pozisyon açık değil"
            
            symbol = str(pos.symbol)
            side = str(pos.side)
            leverage = int(pos.leverage)
            position_side = str(pos.position_side) if pos.position_side else ("long" if side == "LONG" else "short")
            
            # Use recovery step TP/SL values (passed from background_scheduler based on current step)
            
            # Verify position exists on OKX before proceeding
            okx_pos_check = self.client.get_position(symbol, position_side)
            if not okx_pos_check or abs(float(okx_pos_check.get('positionAmt', 0))) == 0:
                return False, "Pozisyon OKX'te bulunamadı veya kapalı"
            
            # Verify position side matches
            okx_pos_side = okx_pos_check.get('posSide', position_side) if 'posSide' in str(okx_pos_check) else position_side
            
            print(f"🔄 RECOVERY başlatılıyor: {symbol} {side} | DB ID: {position_db_id}")
            
            # Step 1: Cancel all TP/SL orders for this position
            cancelled_count = self.client.cancel_all_position_orders(symbol, position_side)
            print(f"✂️ {cancelled_count} emir iptal edildi")
            
            # Step 2: Get current price and calculate add quantity
            current_price = self.client.get_symbol_price(symbol)
            if not current_price:
                return False, "Fiyat alınamadı"
            
            add_quantity = self.calculate_quantity_for_usdt(add_amount_usdt, leverage, current_price, symbol)
            if add_quantity < 0.01:
                return False, "Ekleme miktarı çok düşük (minimum 0.01 kontrat)"
            
            # Step 3: Add to position
            order_result = self.client.add_to_position(symbol, side, add_quantity, position_side)
            if not order_result:
                return False, "Pozisyona ekleme yapılamadı"
            
            print(f"➕ {add_quantity} kontrat eklendi ({add_amount_usdt} USDT)")
            
            import time
            time.sleep(2)
            
            # Step 4: Get updated position info from OKX
            okx_pos = self.client.get_position(symbol, position_side)
            if not okx_pos:
                return False, "Güncel pozisyon bilgisi alınamadı"
            
            new_entry_price = float(okx_pos.get('entryPrice', 0))
            new_quantity = abs(float(okx_pos.get('positionAmt', 0)))
            new_pos_id = okx_pos.get('posId')
            
            if new_quantity == 0:
                return False, "Pozisyon miktarı 0"
            
            # Step 5: Calculate new TP/SL prices based on updated position (using recovery step TP/SL values)
            tp_price, sl_price = self.calculate_tp_sl_prices(
                entry_price=new_entry_price,
                side=side,
                tp_usdt=new_tp_usdt,
                sl_usdt=new_sl_usdt,
                quantity=new_quantity,
                symbol=symbol
            )
            
            time.sleep(1)
            
            # Step 6: Place new TP/SL orders
            tp_order_id, sl_order_id = self.client.place_tp_sl_orders(
                symbol=symbol,
                side=side,
                quantity=new_quantity,
                entry_price=new_entry_price,
                tp_price=tp_price,
                sl_price=sl_price,
                position_side=position_side
            )
            
            # Step 7: Update database record with recovery step TP/SL values
            original_amount = float(pos.amount_usdt)
            
            # Update position fields (TP/SL updated to recovery step values)
            pos.entry_price = new_entry_price
            pos.quantity = new_quantity
            pos.position_id = new_pos_id
            pos.tp_usdt = new_tp_usdt
            pos.sl_usdt = new_sl_usdt
            pos.tp_order_id = tp_order_id
            pos.sl_order_id = sl_order_id
            
            # Update recovery tracking
            current_recovery_count = pos.recovery_count or 0
            pos.recovery_count = current_recovery_count + 1
            pos.last_recovery_at = datetime.now(timezone.utc)
            
            db.commit()
            
            msg = f"✅ RECOVERY #{current_recovery_count + 1} tamamlandı: {symbol} {side} | Başlangıç miktar: ${original_amount:.2f} (değişmedi) | Eklenen: ${add_amount_usdt:.2f} | Giriş: ${new_entry_price:.4f} | Kontrat: {new_quantity}"
            print(msg)
            
            return True, msg
            
        except Exception as e:
            db.rollback()
            error_msg = f"Recovery hatası: {e}"
            print(f"❌ {error_msg}")
            return False, error_msg
        finally:
            db.close()
    
    def check_and_update_positions(self):
        if not self.client.is_configured():
            print("OKX client not configured")
            return
        
        db = SessionLocal()
        try:
            from datetime import timedelta
            grace_period_cutoff = datetime.now(timezone.utc) - timedelta(seconds=120)
            
            # Only check positions older than 120 seconds (grace period for new positions - OKX needs time to update)
            # AND only positions that have a position_id (meaning they were actually opened on OKX)
            open_positions = db.query(Position).filter(
                Position.is_open == True,
                Position.opened_at < grace_period_cutoff,
                Position.position_id != None
            ).all()
            
            for pos in open_positions:
                # Extract all values from SQLAlchemy columns for type safety
                pos_side_value = str(pos.position_side) if pos.position_side is not None else None
                pos_symbol = str(pos.symbol)
                pos_tp_usdt = float(getattr(pos, 'tp_usdt')) if getattr(pos, 'tp_usdt', None) is not None else None
                pos_sl_usdt = float(getattr(pos, 'sl_usdt')) if getattr(pos, 'sl_usdt', None) is not None else None
                pos_entry_price_val = float(getattr(pos, 'entry_price')) if getattr(pos, 'entry_price', None) is not None else None
                
                if pos_side_value is not None:
                    position_side = pos_side_value
                else:
                    position_side = "long" if str(pos.side) == "LONG" else "short"
                
                okx_pos = self.client.get_position(pos_symbol, position_side)
                
                if not okx_pos:
                    print(f"Could not fetch position from OKX: {pos_symbol} {position_side}")
                    continue
                
                okx_pos_id = okx_pos.get('posId')
                okx_pos_amt = float(okx_pos.get('positionAmt', 0))
                
                # Extract position_id value for comparison
                pos_position_id = str(pos.position_id) if pos.position_id is not None else None
                
                if pos_position_id is not None:
                    if okx_pos_id and okx_pos_id != pos_position_id and okx_pos_amt != 0:
                        print(f"Position ID mismatch: DB={pos_position_id}, OKX={okx_pos_id}")
                        continue
                
                if okx_pos_amt == 0:
                    db.query(Position).filter(Position.id == pos.id).update({
                        'is_open': False,
                        'closed_at': datetime.now(timezone.utc)
                    })
                    db.flush()
                    
                    realized_pnl = 0.0
                    close_reason = "MANUAL"
                    
                    trades = self.client.get_account_trades(pos_symbol, limit=100)
                    
                    if trades and len(trades) > 0:
                        position_opened_ts = int(pos.opened_at.timestamp() * 1000)
                        
                        for trade in trades:
                            trade_time = int(trade.get('ts', 0))
                            
                            if trade_time < position_opened_ts:
                                continue
                            
                            trade_side = trade.get('side', '')
                            trade_pos_side = trade.get('posSide', '')
                            exec_type = trade.get('execType', '')
                            
                            if trade_pos_side == position_side:
                                pnl = float(trade.get('fillPnl', 0))
                                realized_pnl += pnl
                                
                                # Check if algo order (TP/SL) triggered
                                if exec_type == 'T' and trade_side in ['sell', 'buy']:
                                    # Determine TP or SL based on PnL
                                    if pnl > 0:
                                        close_reason = "TP"
                                    elif pnl < 0:
                                        close_reason = "SL"
                        
                        # Fallback to PnL-based detection if execType didn't determine it
                        if close_reason == "MANUAL":
                            if pos_tp_usdt is not None and realized_pnl >= pos_tp_usdt:
                                close_reason = "TP"
                            elif pos_sl_usdt is not None and realized_pnl <= -pos_sl_usdt:
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
                    
                    # Use pre-extracted entry_price value
                    if current_entry > 0 and pos_entry_price_val is not None and abs(current_entry - pos_entry_price_val) > 0.01:
                        db.query(Position).filter(Position.id == pos.id).update({
                            'entry_price': current_entry
                        })
                        db.commit()
                    
                    # Use pre-extracted TP/SL values for monitoring unrealized PnL
                    if pos_tp_usdt is not None and unrealized_pnl >= pos_tp_usdt:
                        print(f"TP target reached for {pos_symbol} {str(pos.side)}: ${unrealized_pnl:.2f}")
                    
                    if pos_sl_usdt is not None and unrealized_pnl <= -pos_sl_usdt:
                        print(f"SL target reached for {pos_symbol} {str(pos.side)}: ${unrealized_pnl:.2f}")
            
        except Exception as e:
            print(f"Error checking positions: {e}")
            db.rollback()
        finally:
            db.close()
