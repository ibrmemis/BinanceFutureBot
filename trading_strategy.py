from datetime import datetime, timezone
from typing import Tuple, Optional, Union
from dataclasses import dataclass
import time

from okx_client import OKXTestnetClient
from database_utils import get_db_session
from database import Position, SessionLocal
from constants import (
    OrderSide, PositionSide, TradingConstants, 
    ErrorMessages, SuccessMessages, TradingMode, OrderType
)
from utils import setup_logger

logger = setup_logger("trading_strategy")

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


class TradingStrategy:
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
        
        logger.info(f"Opening {side} position for {symbol}... Size: {amount_usdt} USDT, Leverage: {leverage}x")
        
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
            return PositionResult(False, "Invalid quantity (minimum 1 contract)")
        
        # Place market order
        order = self.client.place_market_order(symbol, side, quantity, position_side)
        if not order:
            return PositionResult(False, ErrorMessages.ORDER_FAILED)
        
        logger.info(f"Order placed for {symbol}. Entry Price: ${current_price:.4f}")
        
        # Get position ID from OKX
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
        message = f"Position opened: {symbol} {side} {quantity} contracts @ ${current_price:.4f}{tp_sl_msg}"
        
        return PositionResult(True, message, order_id=order.get('orderId'))
    
    def _place_tp_sl_orders(
        self, symbol: str, side: str, quantity: float, 
        current_price: float, tp_price: float, sl_price: float, 
        position_side: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Place TP and SL orders with proper validation"""
        
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
                logger.info(f"{order_type} order placed: {order_id} @ ${formatted_price}")
                return order_id
            else:
                logger.error(f"{order_type} order FAILED: {result.get('msg', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"{order_type} order exception: {e}")
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
                message = f"{SuccessMessages.POSITION_OPENED}: {params.symbol} {params.side} {quantity} contracts @ ${entry_price:.4f}{tp_sl_msg}"
                
                return PositionResult(True, message, position.id)
                
        except Exception as e:
            logger.error(f"Database error: {e}")
            return PositionResult(False, f"Database error: {e}")
    
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
        
        try:
            with get_db_session() as db:
                pos = db.query(Position).filter(Position.id == position_db_id).first()
                if not pos:
                    return False, "Position not found"
                
                if not pos.is_open:
                    return False, "Position is not open"
                
                symbol = str(pos.symbol)
                side = str(pos.side)
                leverage = int(pos.leverage)
                position_side = str(pos.position_side) if pos.position_side else ("long" if side == "LONG" else "short")
                
                # Verify position exists on OKX before proceeding
                okx_pos_check = self.client.get_position(symbol, position_side)
                if not okx_pos_check or abs(float(okx_pos_check.get('positionAmt', 0))) == 0:
                    return False, "Position not found on OKX or closed"
                
                logger.info(f"🔄 RECOVERY starting: {symbol} {side} | DB ID: {position_db_id}")
                
                # Step 1: Cancel all TP/SL orders for this position
                cancelled_count = self.client.cancel_all_position_orders(symbol, position_side)
                logger.info(f"✂️ {cancelled_count} orders cancelled")
                
                # Step 2: Get current price and calculate add quantity
                current_price = self.client.get_symbol_price(symbol)
                if not current_price:
                    return False, "Price not available"
                
                add_quantity = self.calculate_quantity_for_usdt(add_amount_usdt, leverage, current_price, symbol)
                if add_quantity < 0.01:
                    return False, "Add amount too low (min 0.01 contracts)"
                
                # Step 3: Add to position
                order_result = self.client.add_to_position(symbol, side, add_quantity, position_side)
                if not order_result:
                    return False, "Failed to add to position"
                
                logger.info(f"➕ {add_quantity} contracts added ({add_amount_usdt} USDT)")
                
                time.sleep(2)
                
                # Step 4: Get updated position info from OKX
                okx_pos = self.client.get_position(symbol, position_side)
                if not okx_pos:
                    return False, "Failed to get updated position info"
                
                new_entry_price = float(okx_pos.get('entryPrice', 0))
                new_quantity = abs(float(okx_pos.get('positionAmt', 0)))
                new_pos_id = okx_pos.get('posId')
                
                if new_quantity == 0:
                    return False, "Position quantity is 0"
                
                # Step 5: Calculate new TP/SL prices based on updated position
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
                
                # Step 7: Update database record
                original_amount = float(pos.amount_usdt)
                
                # Update position fields
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
                
                msg = f"✅ RECOVERY #{current_recovery_count + 1} completed: {symbol} {side} | Start: ${original_amount:.2f} | Added: ${add_amount_usdt:.2f} | Entry: ${new_entry_price:.4f} | Qty: {new_quantity}"
                logger.info(msg)
                
                return True, msg
                
        except Exception as e:
            error_msg = f"Recovery error: {e}"
            logger.error(f"❌ {error_msg}")
            return False, error_msg


