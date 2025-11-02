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
        current_price: float,
        symbol: str | None = None
    ) -> float:
        # Get contract value from OKX API (e.g., ETH: 0.1, BTC: 0.01, SOL: 1)
        if symbol:
            contract_value = self.client.get_contract_value(symbol)
        else:
            contract_value = 1.0
        
        # Calculate exact contracts needed for desired position value
        # Contract USDT value = contract_value * current_price
        contract_usdt_value = contract_value * current_price
        exact_contracts = amount_usdt / contract_usdt_value
        
        # Round to 2 decimal places (OKX supports fractional contracts with 0.01 precision)
        contracts = round(exact_contracts, 2)
        
        # Ensure minimum 0.01 contracts (OKX requirement)
        return max(0.01, contracts)
    
    def calculate_tp_sl_prices(
        self,
        entry_price: float,
        side: str,
        tp_usdt: float,
        sl_usdt: float,
        quantity: float
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
        reopen_count: int = 0,
        save_to_db: bool = True
    ) -> tuple[bool, str, int | None]:
        if not self.client.is_configured():
            return False, "OKX API anahtarları yapılandırılmamış", None
        
        self.client.set_position_mode("long_short_mode")
        
        position_side = "long" if side == "LONG" else "short"
        self.client.set_leverage(symbol, leverage, position_side)
        
        current_price = self.client.get_symbol_price(symbol)
        if not current_price:
            return False, "Fiyat alınamadı", None
        
        quantity = self.calculate_quantity_for_usdt(amount_usdt, leverage, current_price, symbol)
        if quantity < 0.01:
            return False, "Geçersiz miktar (minimum 0.01 kontrat)", None
        
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
        
        # Use entry_price instead of breakeven for TP/SL calculation
        # User's TP/SL USDT values represent net profit/loss expectations
        tp_price, sl_price = self.calculate_tp_sl_prices(
            entry_price=entry_price,
            side=side,
            tp_usdt=tp_usdt,
            sl_usdt=sl_usdt,
            quantity=quantity
        )
        
        sl_order_id = None
        current_price_check = self.client.get_symbol_price(symbol)
        if current_price_check and sl_price and self.client.trade_api:
            is_valid_sl = (side == "LONG" and sl_price < current_price_check) or \
                          (side == "SHORT" and sl_price > current_price_check)
            if is_valid_sl:
                inst_id = self.client.convert_symbol_to_okx(symbol)
                close_side = "sell" if side == "LONG" else "buy"
                sl_result = self.client.trade_api.place_algo_order(
                    instId=inst_id,
                    tdMode="cross",
                    side=close_side,
                    posSide=position_side,
                    ordType="trigger",
                    sz=str(quantity),
                    triggerPx=str(round(sl_price, 4)),
                    orderPx="-1"
                )
                if sl_result.get('code') == '0' and sl_result.get('data'):
                    sl_order_id = sl_result['data'][0]['algoId']
                    print(f"SL order placed immediately: {sl_order_id} @ ${sl_price:.4f}")
        
        time.sleep(5)
        
        tp_order_id = None
        current_price_check = self.client.get_symbol_price(symbol)
        if current_price_check and tp_price and self.client.trade_api:
            is_valid_tp = (side == "LONG" and tp_price > current_price_check) or \
                          (side == "SHORT" and tp_price < current_price_check)
            if is_valid_tp:
                inst_id = self.client.convert_symbol_to_okx(symbol)
                close_side = "sell" if side == "LONG" else "buy"
                # Use conditional order for TP (correct behavior)
                tp_result = self.client.trade_api.place_algo_order(
                    instId=inst_id,
                    tdMode="cross",
                    side=close_side,
                    posSide=position_side,
                    ordType="conditional",
                    sz=str(quantity),
                    tpTriggerPx=str(round(tp_price, 4)),
                    tpOrdPx="-1",
                    reduceOnly=True
                )
                if tp_result.get('code') == '0' and tp_result.get('data'):
                    tp_order_id = tp_result['data'][0]['algoId']
                    print(f"TP order placed after 5 seconds: {tp_order_id} @ ${tp_price:.4f} (entry: ${entry_price:.4f})")
        
        tp_sl_msg = ""
        if tp_order_id and sl_order_id:
            tp_sl_msg = f" (TP: ${tp_price:.4f}, SL: ${sl_price:.4f})"
        elif tp_order_id:
            tp_sl_msg = f" (TP: ${tp_price:.4f})"
        elif sl_order_id:
            tp_sl_msg = f" (SL: ${sl_price:.4f})"
        
        if not save_to_db:
            return True, f"Pozisyon açıldı (DB'ye kaydedilmedi): {symbol} {side} {quantity} kontrat @ ${entry_price:.4f}{tp_sl_msg}", None
        
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
            
            # Extract id value using getattr to satisfy type checker
            position_db_id = int(getattr(position, 'id')) if getattr(position, 'id', None) is not None else None
            
            return True, f"Pozisyon açıldı: {symbol} {side} {quantity} kontrat @ ${entry_price:.4f}{tp_sl_msg}", position_db_id
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
            from datetime import timedelta
            grace_period_cutoff = datetime.utcnow() - timedelta(seconds=60)
            
            # Only check positions older than 60 seconds (grace period for new positions)
            open_positions = db.query(Position).filter(
                Position.is_open == True,
                Position.opened_at < grace_period_cutoff
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
                        'closed_at': datetime.utcnow()
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
