import os
from typing import Dict, Optional, List, Any, Tuple
from functools import wraps
import okx.Account as Account
import okx.Trade as Trade
import okx.MarketData as MarketData
import okx.PublicData as PublicData
from constants import (
    OrderSide, PositionSide, OrderType, TradingMode, 
    APIConstants, TradingConstants
)
from utils import setup_logger

logger = setup_logger("okx_client")

def handle_okx_response(func):
    """
    Decorator to handle OKX API responses consistently.
    Automatically checks for success code and handles errors.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            if isinstance(result, dict) and result.get('code') == '0':
                return result.get('data')
            elif isinstance(result, dict):
                logger.error(f"OKX API Error in {func.__name__}: {result.get('msg', 'Unknown error')}")
                return None
            return result
        except Exception as e:
            logger.exception(f"Exception in {func.__name__}: {e}")
            return None
    return wrapper

class OKXTestnetClient:
    """
    Modern OKX API client with improved error handling, type hints, and caching.
    """
    
    def __init__(self):
        self.api_key: Optional[str] = None
        self.api_secret: Optional[str] = None
        self.passphrase: Optional[str] = None
        self.flag: str = APIConstants.OKX_FLAG_DEMO
        
        # API instances
        self.account_api: Optional[Account.AccountAPI] = None
        self.trade_api: Optional[Trade.TradeAPI] = None
        self.market_api: Optional[MarketData.MarketAPI] = None
        self.public_api: Optional[PublicData.PublicAPI] = None
        
        self._load_credentials()
        self._initialize_apis()
    
    def _load_credentials(self) -> None:
        """Load API credentials from environment or database"""
        self.api_key = os.getenv("OKX_DEMO_API_KEY")
        self.api_secret = os.getenv("OKX_DEMO_API_SECRET")
        self.passphrase = os.getenv("OKX_DEMO_PASSPHRASE")
        
        # Default flag to demo unless specified otherwise in DB
        self.flag = APIConstants.OKX_FLAG_DEMO
        
        # Try to load from database if env vars not available
        if not all([self.api_key, self.api_secret, self.passphrase]):
            self._load_from_database()
    
    def _load_from_database(self) -> None:
        """Load credentials from database based on current mode"""
        try:
            from database import SessionLocal, APICredentials
            with SessionLocal() as db:
                creds = db.query(APICredentials).first()
                if creds:
                    # Determine which credentials to use
                    is_demo = creds.is_demo
                    
                    if not all([self.api_key, self.api_secret, self.passphrase]):
                        self.api_key, self.api_secret, self.passphrase = creds.get_credentials(is_demo=is_demo)
                    
                    # Update flag based on is_demo setting
                    self.flag = APIConstants.OKX_FLAG_DEMO if is_demo else APIConstants.OKX_FLAG_LIVE
        except Exception as e:
            logger.warning(f"Could not load credentials from database: {e}")
    
    def _initialize_apis(self) -> None:
        """Initialize OKX API instances if credentials are available"""
        if not all([self.api_key, self.api_secret, self.passphrase]):
            return
        
        try:
            common_args = (self.api_key, self.api_secret, self.passphrase, False, self.flag)
            
            self.account_api = Account.AccountAPI(*common_args)
            self.trade_api = Trade.TradeAPI(*common_args)
            self.market_api = MarketData.MarketAPI(*common_args)
            self.public_api = PublicData.PublicAPI(*common_args)
            
        except Exception as e:
            logger.warning(f"Failed to initialize OKX APIs: {e}")
            self._reset_apis()
    
    def _reset_apis(self) -> None:
        """Reset all API instances to None"""
        self.account_api = None
        self.trade_api = None
        self.market_api = None
        self.public_api = None
    
    def is_configured(self) -> bool:
        """Check if client is properly configured"""
        return (
            self.account_api is not None and 
            all([self.api_key, self.api_secret, self.passphrase])
        )
    
    @staticmethod
    def convert_symbol_to_okx(symbol: str) -> str:
        """Convert symbol format to OKX format (e.g., BTCUSDT -> BTC-USDT-SWAP)"""
        symbol = symbol.upper().replace("USDT", "")
        return f"{symbol}-USDT-SWAP"
    
    @handle_okx_response
    def set_position_mode(self, mode: str = TradingMode.CROSS) -> bool:
        """Set position mode (long_short_mode or net_mode)"""
        if not self.account_api:
            return False
        
        result = self.account_api.set_position_mode(posMode=mode)
        
        # Handle already set case
        if 'Position mode is already set' in str(result):
            return True
        
        return result.get('code') == '0'
    
    @handle_okx_response
    def set_leverage(self, symbol: str, leverage: int, position_side: str = PositionSide.LONG) -> bool:
        """Set leverage for a symbol"""
        if not self.account_api:
            return False
        
        inst_id = self.convert_symbol_to_okx(symbol)
        result = self.account_api.set_leverage(
            instId=inst_id,
            lever=str(leverage),
            mgnMode=TradingMode.CROSS,
            posSide=position_side
        )
        return result
    
    def get_account_balance(self, currency: str = "USDT") -> Optional[Dict[str, float]]:
        """Get account balance for a specific currency"""
        if not self.account_api:
            return None
        
        try:
            result = self.account_api.get_account_balance(ccy=currency)
            if result.get('code') == '0' and result.get('data'):
                data = result['data'][0]
                details = data.get('details', [])
                
                for detail in details:
                    if detail.get('ccy') == currency:
                        return {
                            'equity': float(detail.get('eq', 0)),
                            'available': float(detail.get('availEq', 0)),
                            'frozen': float(detail.get('frozenBal', 0)),
                            'unrealized_pnl': float(detail.get('upl', 0)),
                            'margin_used': float(detail.get('eq', 0)) - float(detail.get('availEq', 0))
                        }
            return None
        except Exception as e:
            logger.error(f"Error getting account balance: {e}")
            return None
    
    def get_all_swap_symbols(self) -> List[str]:
        """Get all available SWAP symbols from OKX API with caching"""
        if not self.public_api:
            return TradingConstants.POPULAR_SYMBOLS
        
        try:
            result = self.public_api.get_instruments(instType=APIConstants.INST_TYPE_SWAP)
            if result.get('code') == '0' and result.get('data'):
                symbols = []
                for instrument in result['data']:
                    inst_id = instrument.get('instId', '')
                    # Convert BTC-USDT-SWAP to BTCUSDT
                    if '-USDT-SWAP' in inst_id:
                        symbol = inst_id.replace('-USDT-SWAP', '').replace('-', '') + 'USDT'
                        symbols.append(symbol)
                return sorted(symbols)
            return TradingConstants.POPULAR_SYMBOLS
        except Exception as e:
            logger.error(f"Error getting SWAP symbols: {e}")
            return TradingConstants.POPULAR_SYMBOLS
    
    def get_contract_value(self, symbol: str) -> float:
        """Get contract value (ctVal) for a symbol from OKX API"""
        # Use cached values for popular symbols
        if symbol in TradingConstants.CONTRACT_VALUES:
            return TradingConstants.CONTRACT_VALUES[symbol]
        
        if not self.public_api:
            return TradingConstants.DEFAULT_LOT_SIZE
        
        inst_id = self.convert_symbol_to_okx(symbol)
        try:
            result = self.public_api.get_instruments(instType=APIConstants.INST_TYPE_SWAP, instId=inst_id)
            if result.get('code') == '0' and result.get('data'):
                return float(result['data'][0].get('ctVal', TradingConstants.DEFAULT_LOT_SIZE))
        except Exception as e:
            logger.error(f"Error getting contract value for {symbol}: {e}")
        
        # Fallback to known values
        if 'ETH' in symbol.upper():
            return 0.1
        elif 'BTC' in symbol.upper():
            return 0.01
        else:
            return 1.0
    
    def get_lot_size(self, symbol: str) -> float:
        """Get lot size (lotSz) for a symbol from OKX API"""
        if not self.public_api:
            return TradingConstants.DEFAULT_LOT_SIZE
        
        inst_id = self.convert_symbol_to_okx(symbol)
        try:
            result = self.public_api.get_instruments(instType=APIConstants.INST_TYPE_SWAP, instId=inst_id)
            if result.get('code') == '0' and result.get('data'):
                return float(result['data'][0].get('lotSz', TradingConstants.DEFAULT_LOT_SIZE))
        except Exception as e:
            logger.error(f"Error getting lot size for {symbol}: {e}")
        
        return TradingConstants.DEFAULT_LOT_SIZE
    
    def get_tick_size(self, symbol: str) -> str:
        """Get tick size (tickSz) for a symbol from OKX API"""
        if not self.public_api:
            return TradingConstants.DEFAULT_TICK_SIZE
        
        inst_id = self.convert_symbol_to_okx(symbol)
        try:
            result = self.public_api.get_instruments(instType=APIConstants.INST_TYPE_SWAP, instId=inst_id)
            if result.get('code') == '0' and result.get('data'):
                return result['data'][0].get('tickSz', TradingConstants.DEFAULT_TICK_SIZE)
        except Exception as e:
            logger.error(f"Error getting tick size for {symbol}: {e}")
        
        return TradingConstants.DEFAULT_TICK_SIZE
    
    def format_price(self, price: float, tick_size: str) -> str:
        """Format price according to tick size precision"""
        from decimal import Decimal, ROUND_DOWN
        try:
            tick_decimal = Decimal(tick_size)
            price_decimal = Decimal(str(price))
            # Round down to tick size
            rounded = (price_decimal / tick_decimal).quantize(Decimal('1'), rounding=ROUND_DOWN) * tick_decimal
            # Get decimal places from tick size
            decimal_places = len(tick_size.split('.')[1]) if '.' in tick_size else 0
            return f"{float(rounded):.{decimal_places}f}"
        except Exception:
            return str(price)
    
    def round_to_lot_size(self, quantity: float, lot_size: float) -> float:
        """Round quantity to 2 decimal places for OKX SWAP contracts"""
        return round(quantity, 2)
    
    def get_symbol_price(self, symbol: str) -> Optional[float]:
        """Get current symbol price"""
        if not self.market_api:
            return None
        
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            result = self.market_api.get_ticker(instId=inst_id)
            if result.get('code') == '0' and result.get('data'):
                return float(result['data'][0]['last'])
            return None
        except Exception as e:
            logger.error(f"Error getting price for {symbol}: {e}")
            return None
    
    def place_market_order(self, symbol: str, side: str, quantity: float, 
                          position_side: str = PositionSide.LONG) -> Optional[Dict[str, Any]]:
        """Place a market order"""
        if not self.trade_api:
            return None
        
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            lot_size = self.get_lot_size(symbol)
            rounded_quantity = self.round_to_lot_size(quantity, lot_size)
            
            logger.info(f"📦 Market order: {symbol} {side} | qty: {quantity} -> {rounded_quantity} (lot: {lot_size})")
            
            okx_side = OrderSide.BUY if side.upper() == OrderSide.LONG else OrderSide.SELL
            okx_pos_side = PositionSide.LONG if side.upper() == OrderSide.LONG else PositionSide.SHORT
            
            result = self.trade_api.place_order(
                instId=inst_id,
                tdMode=TradingMode.CROSS,
                side=okx_side,
                posSide=okx_pos_side,
                ordType=OrderType.MARKET,
                sz=str(rounded_quantity)
            )
            
            if result.get('code') == '0' and result.get('data'):
                return {
                    'orderId': result['data'][0]['ordId'],
                    'symbol': symbol,
                    'side': side,
                    'quantity': quantity
                }
            else:
                logger.error(f"Order failed: {result}")
            return None
        except Exception as e:
            logger.error(f"Error placing market order: {e}")
            return None
    
    def place_limit_order(self, symbol: str, side: str, quantity: float, price: float, position_side: str = "long") -> Optional[Dict]:
        if not self.trade_api:
            return None
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            okx_side = "buy" if side.upper() in ["LONG", "BUY"] else "sell"
            
            result = self.trade_api.place_order(
                instId=inst_id,
                tdMode="cross",
                side=okx_side,
                posSide=position_side,
                ordType="limit",
                px=str(price),
                sz=str(quantity)
            )
            
            if result.get('code') == '0' and result.get('data'):
                return {
                    'orderId': result['data'][0]['ordId'],
                    'symbol': symbol
                }
            return None
        except Exception as e:
            logger.error(f"Error placing limit order: {e}")
            return None
    
    def place_tp_sl_orders(self, symbol: str, side: str, quantity: float, entry_price: float, tp_price: float, sl_price: float, position_side: str = "long") -> tuple[Optional[str], Optional[str]]:
        if not self.trade_api:
            return None, None
        
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            close_side = "sell" if side.upper() == "LONG" else "buy"
            
            lot_size = self.get_lot_size(symbol)
            rounded_quantity = self.round_to_lot_size(quantity, lot_size)
            
            tp_order_id = None
            sl_order_id = None
            
            validation_price = entry_price
            
            # Get tick size for proper price formatting
            tick_size = self.get_tick_size(symbol)
            
            if tp_price and tp_price > 0:
                is_valid_tp = (side.upper() == "LONG" and tp_price > validation_price) or \
                              (side.upper() == "SHORT" and tp_price < validation_price)
                
                if is_valid_tp:
                    formatted_tp = self.format_price(tp_price, tick_size)
                    tp_result = self.trade_api.place_algo_order(
                        instId=inst_id,
                        tdMode="cross",
                        side=close_side,
                        posSide=position_side,
                        ordType="trigger",
                        sz=str(rounded_quantity),
                        triggerPx=formatted_tp,
                        orderPx="-1"
                    )
                    if tp_result.get('code') == '0' and tp_result.get('data'):
                        tp_order_id = tp_result['data'][0]['algoId']
                        logger.info(f"TP order placed: {tp_order_id} @ {formatted_tp}")
                    else:
                        logger.error(f"TP order failed: {tp_result}")
                else:
                    logger.warning(f"Invalid TP price: {tp_price} (entry: {entry_price}, side: {side})")
            
            if sl_price and sl_price > 0:
                is_valid_sl = (side.upper() == "LONG" and sl_price < validation_price) or \
                              (side.upper() == "SHORT" and sl_price > validation_price)
                
                if is_valid_sl:
                    formatted_sl = self.format_price(sl_price, tick_size)
                    sl_result = self.trade_api.place_algo_order(
                        instId=inst_id,
                        tdMode="cross",
                        side=close_side,
                        posSide=position_side,
                        ordType="trigger",
                        sz=str(rounded_quantity),
                        triggerPx=formatted_sl,
                        orderPx="-1"
                    )
                    if sl_result.get('code') == '0' and sl_result.get('data'):
                        sl_order_id = sl_result['data'][0]['algoId']
                        logger.info(f"SL order placed: {sl_order_id} @ {formatted_sl}")
                    else:
                        logger.error(f"SL order failed: {sl_result}")
                else:
                    logger.warning(f"Invalid SL price: {sl_price} (entry: {entry_price}, side: {side})")
            
            return tp_order_id, sl_order_id
            
        except Exception as e:
            logger.error(f"Error placing TP/SL orders: {e}")
            return None, None
    
    def get_algo_orders(self, symbol: Optional[str] = None, order_type: str = "trigger") -> list:
        """Get algo orders (trigger, conditional, etc.)"""
        if not self.trade_api:
            return []
        try:
            inst_id = self.convert_symbol_to_okx(symbol) if symbol else ''
            
            result = self.trade_api.order_algos_list(
                ordType=order_type,
                instType='SWAP',
                instId=inst_id
            )
            
            if result.get('code') == '0' and result.get('data'):
                return result['data']
            return []
        except Exception as e:
            logger.error(f"Error getting algo orders: {e}")
            return []
    
    def get_all_open_orders(self, symbol: Optional[str] = None) -> Optional[list]:
        """Get ALL open orders including algo orders, conditional orders, iceberg, etc."""
        if not self.trade_api:
            return None
        
        all_orders = []
        
        try:
            # 1. Get trigger orders
            trigger_orders = self.get_algo_orders(symbol, order_type="trigger")
            all_orders.extend(trigger_orders)
            
            # 2. Get conditional orders
            try:
                conditional_orders = self.get_algo_orders(symbol, order_type="conditional")
                all_orders.extend(conditional_orders)
            except:
                pass
            
            # 3. Get iceberg orders
            try:
                iceberg_orders = self.get_algo_orders(symbol, order_type="iceberg")
                all_orders.extend(iceberg_orders)
            except:
                pass
            
            # 4. Get TWAP orders
            try:
                twap_orders = self.get_algo_orders(symbol, order_type="twap")
                all_orders.extend(twap_orders)
            except:
                pass
                
        except Exception as e:
            logger.error(f"Error getting all open orders: {e}")
            return None
        
        return all_orders
    
    def cancel_algo_order(self, symbol: str, algo_id: str) -> bool:
        if not self.trade_api:
            return False
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            result = self.trade_api.cancel_algo_order([{
                'instId': inst_id,
                'algoId': algo_id
            }])
            return result.get('code') == '0'
        except Exception as e:
            logger.error(f"Error canceling algo order: {e}")
            return False
    
    def amend_algo_order(self, symbol: str, algo_id: str, new_trigger_price: float, quantity: int) -> bool:
        if not self.trade_api:
            return False
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            params = {
                'instId': inst_id,
                'algoId': algo_id,
                'newSz': str(quantity)
            }
            
            if new_trigger_price:
                params['newTpTriggerPx'] = str(round(new_trigger_price, 4))
                params['newTpOrdPx'] = '-1'
            
            result = self.trade_api.amend_algo_order(**params)
            return result.get('code') == '0'
        except Exception as e:
            logger.error(f"Error amending algo order: {e}")
            return False
    
    def get_position(self, symbol: str, position_side: str = "long") -> Optional[Dict]:
        if not self.account_api:
            return None
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            result = self.account_api.get_positions(instType="SWAP", instId=inst_id)
            
            if result.get('code') == '0' and result.get('data'):
                for pos in result['data']:
                    if pos.get('posSide') == position_side:
                        return {
                            'positionAmt': pos.get('pos', '0'),
                            'entryPrice': pos.get('avgPx', '0'),
                            'breakevenPrice': pos.get('bePx', pos.get('avgPx', '0')),
                            'unrealizedProfit': pos.get('upl', '0'),
                            'leverage': pos.get('lever', '1'),
                            'posId': pos.get('posId', None)
                        }
            return {'positionAmt': '0', 'posId': None}
        except Exception as e:
            logger.error(f"Error getting position: {e}")
            return None
    
    def get_all_positions(self) -> list:
        if not self.account_api:
            return []
        try:
            result = self.account_api.get_positions(instType="SWAP")
            if result.get('code') == '0' and result.get('data'):
                active_positions = []
                for pos in result['data']:
                    if float(pos.get('pos', 0)) != 0:
                        active_positions.append({
                            'instId': pos.get('instId'),
                            'posSide': pos.get('posSide'),
                            'positionAmt': pos.get('pos', '0'),
                            'entryPrice': pos.get('avgPx', '0'),
                            'markPrice': pos.get('markPx', '0'),
                            'notionalUsd': pos.get('notionalUsd', '0'),
                            'unrealizedProfit': pos.get('upl', '0'),
                            'leverage': pos.get('lever', '1'),
                            'posId': pos.get('posId', None)
                        })
                return active_positions
            return []
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []
    
    def close_position_market(self, symbol: str, side: str, quantity: int, position_side: str = "long") -> bool:
        if not self.trade_api:
            return False
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            result = self.trade_api.place_order(
                instId=inst_id,
                tdMode="cross",
                side=side,
                ordType="market",
                sz=str(quantity),
                posSide=position_side
            )
            
            if result.get('code') == '0':
                logger.info(f"Position closed: {result}")
                return True
            else:
                logger.error(f"Failed to close position: {result}")
                return False
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False
    
    def cancel_order(self, symbol: str, order_id: str) -> bool:
        if not self.trade_api:
            return False
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            result = self.trade_api.cancel_order(instId=inst_id, ordId=order_id)
            return result.get('code') == '0'
        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            return False
    
    def get_order(self, symbol: str, order_id: str) -> Optional[Dict]:
        if not self.trade_api:
            return None
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            result = self.trade_api.get_order(instId=inst_id, ordId=order_id)
            
            if result.get('code') == '0' and result.get('data'):
                order = result['data'][0]
                return {
                    'orderId': order.get('ordId'),
                    'status': order.get('state'),
                    'executedQty': order.get('accFillSz', '0'),
                    'avgPrice': order.get('avgPx', '0')
                }
            return None
        except Exception as e:
            logger.error(f"Error getting order: {e}")
            return None
    
    def get_account_trades(self, symbol: str, limit: int = 50) -> list:
        if not self.trade_api:
            return []
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            result = self.trade_api.get_fills(instType="SWAP", instId=inst_id, limit=str(limit))
            
            if result.get('code') == '0' and result.get('data'):
                return list(result['data'])
            return []
        except Exception as e:
            logger.error(f"Error getting trades: {e}")
            return []
    
    def cancel_all_position_orders(self, symbol: str, position_side: str) -> int:
        """Cancel all algo orders for a specific position (TP/SL orders)"""
        if not self.trade_api:
            return 0
        
        cancelled_count = 0
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            
            # Get all algo orders for this symbol
            all_orders = self.get_all_open_orders(symbol)
            
            if all_orders is None:
                return 0

            for order in all_orders:
                if order.get('state') != 'live':
                    continue
                
                order_inst_id = order.get('instId', '')
                order_pos_side = order.get('posSide', '')
                algo_id = order.get('algoId')
                
                # Match by instId and posSide
                if order_inst_id == inst_id and order_pos_side == position_side and algo_id:
                    result = self.cancel_algo_order(symbol, algo_id)
                    if result:
                        cancelled_count += 1
                        logger.info(f"✂️ Cancelled order: {algo_id} ({order_inst_id} {order_pos_side})")
            
            return cancelled_count
        except Exception as e:
            logger.error(f"Error cancelling position orders: {e}")
            return cancelled_count
    
    def add_to_position(self, symbol: str, side: str, quantity: float, position_side: str = "long") -> Optional[Dict]:
        """Add to existing position (same as place_market_order but named for clarity)"""
        return self.place_market_order(symbol, side, quantity, position_side)
    
    def get_positions_history(self, inst_type: str = "SWAP", limit: int = 100, before: str = None, after: str = None) -> list:
        """
        Get positions history from OKX with pagination support
        """
        if not self.account_api:
            return []
        try:
            params = {
                'instType': inst_type,
                'limit': str(limit)
            }
            
            if before:
                params['before'] = str(before)
            if after:
                params['after'] = str(after)
            
            result = self.account_api.get_positions_history(**params)
            
            if result.get('code') == '0' and result.get('data'):
                return list(result['data'])
            return []
        except Exception as e:
            logger.error(f"Error getting positions history: {e}")
            return []
