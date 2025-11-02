import os
import okx.Account as Account
import okx.Trade as Trade
import okx.MarketData as MarketData
import okx.PublicData as PublicData
from typing import Dict, Optional, List

class OKXTestnetClient:
    def __init__(self):
        self.api_key = None
        self.api_secret = None
        self.passphrase = None
        self.flag = "1"
        
        self.account_api = None
        self.trade_api = None
        self.market_api = None
        self.public_api = None
        
        self._load_credentials()
        
        if self.api_key and self.api_secret and self.passphrase:
            try:
                self.account_api = Account.AccountAPI(
                    self.api_key,
                    self.api_secret,
                    self.passphrase,
                    False,
                    self.flag
                )
                self.trade_api = Trade.TradeAPI(
                    self.api_key,
                    self.api_secret,
                    self.passphrase,
                    False,
                    self.flag
                )
                self.market_api = MarketData.MarketAPI(
                    self.api_key,
                    self.api_secret,
                    self.passphrase,
                    False,
                    self.flag
                )
                self.public_api = PublicData.PublicAPI(
                    self.api_key,
                    self.api_secret,
                    self.passphrase,
                    False,
                    self.flag
                )
            except Exception as e:
                print(f"Warning: Failed to initialize OKX client: {e}")
                self.account_api = None
    
    def _load_credentials(self):
        self.api_key = os.getenv("OKX_DEMO_API_KEY")
        self.api_secret = os.getenv("OKX_DEMO_API_SECRET")
        self.passphrase = os.getenv("OKX_DEMO_PASSPHRASE")
        
        if not self.api_key or not self.api_secret or not self.passphrase:
            try:
                from database import SessionLocal, APICredentials
                db = SessionLocal()
                try:
                    creds = db.query(APICredentials).first()
                    if creds:
                        self.api_key, self.api_secret, self.passphrase = creds.get_credentials()
                finally:
                    db.close()
            except Exception as e:
                pass
    
    def is_configured(self) -> bool:
        return (self.account_api is not None and 
                self.api_key is not None and 
                self.api_secret is not None and 
                self.passphrase is not None)
    
    def convert_symbol_to_okx(self, symbol: str) -> str:
        symbol = symbol.upper().replace("USDT", "")
        return f"{symbol}-USDT-SWAP"
    
    def set_position_mode(self, mode: str = "long_short_mode") -> bool:
        if not self.account_api:
            return False
        try:
            result = self.account_api.set_position_mode(posMode=mode)
            if result.get('code') == '0':
                return True
            if 'Position mode is already set' in str(result):
                return True
            return False
        except Exception as e:
            if 'Position mode is already set' in str(e):
                return True
            print(f"Error setting position mode: {e}")
            return False
    
    def set_leverage(self, symbol: str, leverage: int, position_side: str = "long") -> bool:
        if not self.account_api:
            return False
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            result = self.account_api.set_leverage(
                instId=inst_id,
                lever=str(leverage),
                mgnMode="cross",
                posSide=position_side
            )
            return result.get('code') == '0'
        except Exception as e:
            print(f"Error setting leverage: {e}")
            return False
    
    def get_symbol_price(self, symbol: str) -> Optional[float]:
        if not self.market_api:
            return None
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            result = self.market_api.get_ticker(instId=inst_id)
            if result.get('code') == '0' and result.get('data'):
                return float(result['data'][0]['last'])
            return None
        except Exception as e:
            print(f"Error getting price: {e}")
            return None
    
    def get_account_balance(self) -> Optional[Dict]:
        if not self.account_api:
            return None
        try:
            result = self.account_api.get_account_balance()
            if result.get('code') == '0':
                return result
            return None
        except Exception as e:
            print(f"Error getting balance: {e}")
            return None
    
    def place_market_order(self, symbol: str, side: str, quantity: float, position_side: str = "long") -> Optional[Dict]:
        if not self.trade_api:
            return None
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            
            okx_side = "buy" if side.upper() == "LONG" else "sell"
            okx_pos_side = "long" if side.upper() == "LONG" else "short"
            
            result = self.trade_api.place_order(
                instId=inst_id,
                tdMode="cross",
                side=okx_side,
                posSide=okx_pos_side,
                ordType="market",
                sz=str(int(quantity))
            )
            
            if result.get('code') == '0' and result.get('data'):
                return {
                    'orderId': result['data'][0]['ordId'],
                    'symbol': symbol,
                    'side': side,
                    'quantity': quantity
                }
            else:
                print(f"Order failed: {result}")
            return None
        except Exception as e:
            print(f"Error placing order: {e}")
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
                sz=str(int(quantity))
            )
            
            if result.get('code') == '0' and result.get('data'):
                return {
                    'orderId': result['data'][0]['ordId'],
                    'symbol': symbol
                }
            return None
        except Exception as e:
            print(f"Error placing limit order: {e}")
            return None
    
    def place_tp_sl_orders(self, symbol: str, side: str, quantity: float, entry_price: float, tp_price: float, sl_price: float, position_side: str = "long") -> tuple[Optional[str], Optional[str]]:
        if not self.trade_api:
            return None, None
        
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            close_side = "sell" if side.upper() == "LONG" else "buy"
            
            tp_order_id = None
            sl_order_id = None
            
            current_price = self.get_symbol_price(symbol)
            if not current_price:
                print("Cannot get current price for TP/SL validation")
                return None, None
            
            if tp_price:
                is_valid_tp = (side.upper() == "LONG" and tp_price > current_price) or \
                              (side.upper() == "SHORT" and tp_price < current_price)
                
                if is_valid_tp:
                    tp_result = self.trade_api.place_algo_order(
                        instId=inst_id,
                        tdMode="cross",
                        side=close_side,
                        posSide=position_side,
                        ordType="trigger",
                        sz=str(int(quantity)),
                        triggerPx=str(round(tp_price, 4)),
                        orderPx="-1"
                    )
                    if tp_result.get('code') == '0' and tp_result.get('data'):
                        tp_order_id = tp_result['data'][0]['algoId']
                        print(f"TP order placed: {tp_order_id} @ ${tp_price:.4f} (current: ${current_price:.4f})")
                    else:
                        print(f"TP order failed: {tp_result}")
                else:
                    print(f"Invalid TP price: ${tp_price:.4f} (current: ${current_price:.4f}, side: {side})")
            
            if sl_price:
                is_valid_sl = (side.upper() == "LONG" and sl_price < current_price) or \
                              (side.upper() == "SHORT" and sl_price > current_price)
                
                if is_valid_sl:
                    sl_result = self.trade_api.place_algo_order(
                        instId=inst_id,
                        tdMode="cross",
                        side=close_side,
                        posSide=position_side,
                        ordType="trigger",
                        sz=str(int(quantity)),
                        triggerPx=str(round(sl_price, 4)),
                        orderPx="-1"
                    )
                    if sl_result.get('code') == '0' and sl_result.get('data'):
                        sl_order_id = sl_result['data'][0]['algoId']
                        print(f"SL order placed: {sl_order_id} @ ${sl_price:.4f} (current: ${current_price:.4f})")
                    else:
                        print(f"SL order failed: {sl_result}")
                else:
                    print(f"Invalid SL price: ${sl_price:.4f} (current: ${current_price:.4f}, side: {side})")
            
            return tp_order_id, sl_order_id
            
        except Exception as e:
            print(f"Error placing TP/SL orders: {e}")
            return None, None
    
    def get_algo_orders(self, symbol: Optional[str] = None, order_type: str = "trigger") -> list:
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
            print(f"Error getting algo orders: {e}")
            return []
    
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
            print(f"Error canceling algo order: {e}")
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
            print(f"Error amending algo order: {e}")
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
                            'unrealizedProfit': pos.get('upl', '0'),
                            'leverage': pos.get('lever', '1')
                        }
            return {'positionAmt': '0'}
        except Exception as e:
            print(f"Error getting position: {e}")
            return None
    
    def get_all_positions(self) -> list:
        if not self.account_api:
            return []
        try:
            result = self.account_api.get_positions(instType="SWAP")
            if result.get('code') == '0' and result.get('data'):
                active_positions = [
                    pos for pos in result['data']
                    if float(pos.get('pos', 0)) != 0
                ]
                return active_positions
            return []
        except Exception as e:
            print(f"Error getting positions: {e}")
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
                print(f"Position closed: {result}")
                return True
            else:
                print(f"Failed to close position: {result}")
                return False
        except Exception as e:
            print(f"Error closing position: {e}")
            return False
    
    def cancel_order(self, symbol: str, order_id: str) -> bool:
        if not self.trade_api:
            return False
        try:
            inst_id = self.convert_symbol_to_okx(symbol)
            result = self.trade_api.cancel_order(instId=inst_id, ordId=order_id)
            return result.get('code') == '0'
        except Exception as e:
            print(f"Error canceling order: {e}")
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
            print(f"Error getting order: {e}")
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
            print(f"Error getting trades: {e}")
            return []
