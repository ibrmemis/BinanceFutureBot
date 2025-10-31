import os
from binance.client import Client
from binance.exceptions import BinanceAPIException
from typing import Dict, Optional

class BinanceTestnetClient:
    def __init__(self):
        self.api_key = None
        self.api_secret = None
        self.client = None
        
        self._load_credentials()
        
        if self.api_key and self.api_secret:
            try:
                self.client = Client(
                    self.api_key, 
                    self.api_secret,
                    testnet=True
                )
                self.client.API_URL = 'https://demo.binance.com'
            except Exception as e:
                print(f"Warning: Failed to initialize Binance client: {e}")
                self.client = None
    
    def _load_credentials(self):
        self.api_key = os.getenv("BINANCE_TESTNET_API_KEY")
        self.api_secret = os.getenv("BINANCE_TESTNET_API_SECRET")
        
        if not self.api_key or not self.api_secret:
            try:
                from database import SessionLocal, APICredentials
                db = SessionLocal()
                try:
                    creds = db.query(APICredentials).first()
                    if creds:
                        self.api_key, self.api_secret = creds.get_credentials()
                finally:
                    db.close()
            except Exception as e:
                pass
    
    def is_configured(self) -> bool:
        return self.client is not None and self.api_key is not None and self.api_secret is not None
    
    def set_hedge_mode(self) -> bool:
        if not self.client:
            return False
        try:
            self.client.futures_change_position_mode(dualSidePosition=True)
            return True
        except BinanceAPIException as e:
            if "No need to change position side" in str(e):
                return True
            return False
    
    def set_leverage(self, symbol: str, leverage: int) -> bool:
        if not self.client:
            return False
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            return True
        except Exception as e:
            print(f"Error setting leverage: {e}")
            return False
    
    def set_margin_type(self, symbol: str, margin_type: str = "CROSSED") -> bool:
        if not self.client:
            return False
        try:
            self.client.futures_change_margin_type(symbol=symbol, marginType=margin_type)
            return True
        except BinanceAPIException as e:
            if "No need to change margin type" in str(e):
                return True
            return False
    
    def get_symbol_price(self, symbol: str) -> Optional[float]:
        if not self.client:
            return None
        try:
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            print(f"Error getting price: {e}")
            return None
    
    def get_symbol_info(self, symbol: str) -> Optional[Dict]:
        if not self.client:
            return None
        try:
            exchange_info = self.client.futures_exchange_info()
            for s in exchange_info['symbols']:
                if s['symbol'] == symbol:
                    return s
            return None
        except Exception as e:
            print(f"Error getting symbol info: {e}")
            return None
    
    def calculate_quantity(self, symbol: str, amount_usdt: float, leverage: int, price: float) -> float:
        symbol_info = self.get_symbol_info(symbol)
        if not symbol_info:
            return 0
        
        quantity = (amount_usdt * leverage) / price
        
        step_size = None
        for f in symbol_info['filters']:
            if f['filterType'] == 'LOT_SIZE':
                step_size = float(f['stepSize'])
                break
        
        if step_size:
            precision = len(str(step_size).rstrip('0').split('.')[-1])
            quantity = round(quantity, precision)
        
        return quantity
    
    def open_market_order(
        self, 
        symbol: str, 
        side: str,
        quantity: float,
        position_side: str,
        reduce_only: bool = False
    ) -> Optional[Dict]:
        if not self.client:
            return None
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                positionSide=position_side,
                type='MARKET',
                quantity=quantity,
                reduceOnly=reduce_only
            )
            return order
        except Exception as e:
            print(f"Error creating order: {e}")
            return None
    
    def set_take_profit(
        self,
        symbol: str,
        side: str,
        position_side: str,
        quantity: float,
        stop_price: float
    ) -> Optional[Dict]:
        if not self.client:
            return None
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                positionSide=position_side,
                type='TAKE_PROFIT_MARKET',
                stopPrice=stop_price,
                closePosition=True,
                workingType='MARK_PRICE'
            )
            return order
        except Exception as e:
            print(f"Error setting TP: {e}")
            return None
    
    def set_stop_loss(
        self,
        symbol: str,
        side: str,
        position_side: str,
        quantity: float,
        stop_price: float
    ) -> Optional[Dict]:
        if not self.client:
            return None
        try:
            order = self.client.futures_create_order(
                symbol=symbol,
                side=side,
                positionSide=position_side,
                type='STOP_MARKET',
                stopPrice=stop_price,
                closePosition=True,
                workingType='MARK_PRICE'
            )
            return order
        except Exception as e:
            print(f"Error setting SL: {e}")
            return None
    
    def get_position(self, symbol: str, position_side: str) -> Optional[Dict]:
        if not self.client:
            return None
        try:
            positions = self.client.futures_position_information(symbol=symbol)
            for pos in positions:
                if pos['positionSide'] == position_side:
                    return pos
            return None
        except Exception as e:
            print(f"Error getting position: {e}")
            return None
    
    def get_all_positions(self) -> list:
        if not self.client:
            return []
        try:
            positions = self.client.futures_position_information()
            active_positions = [
                pos for pos in positions 
                if float(pos['positionAmt']) != 0
            ]
            return active_positions
        except Exception as e:
            print(f"Error getting positions: {e}")
            return []
    
    def cancel_all_orders(self, symbol: str) -> bool:
        if not self.client:
            return False
        try:
            self.client.futures_cancel_all_open_orders(symbol=symbol)
            return True
        except Exception as e:
            print(f"Error canceling orders: {e}")
            return False
    
    def get_account_trades(self, symbol: str, limit: int = 50) -> list:
        if not self.client:
            return []
        try:
            trades = self.client.futures_account_trades(symbol=symbol, limit=limit)
            return list(trades) if trades else []
        except Exception as e:
            print(f"Error getting trades: {e}")
            return []
    
    def get_order(self, symbol: str, order_id: str) -> Optional[Dict]:
        if not self.client:
            return None
        try:
            order = self.client.futures_get_order(symbol=symbol, orderId=order_id)
            return order
        except Exception as e:
            print(f"Error getting order: {e}")
            return None
