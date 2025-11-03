import threading
import time
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from database import SessionLocal, Position
from trading_strategy import Try1Strategy

class PositionMonitor:
    def __init__(self, auto_reopen_delay_minutes: int = 5):
        self.scheduler = BackgroundScheduler()
        self.strategy = None
        self.closed_positions_for_reopen = {}
        self.auto_reopen_delay_minutes = auto_reopen_delay_minutes
    
    def _ensure_strategy(self):
        if self.strategy is None:
            self.strategy = Try1Strategy()
        elif not self.strategy.client.is_configured():
            self.strategy = Try1Strategy()
        
    def check_positions(self):
        try:
            self._ensure_strategy()
            if not self.strategy or not self.strategy.client.is_configured():
                return
            
            # DO NOT call check_and_update_positions() - we don't want to auto-close positions
            # User controls position state manually via UI buttons
            
            db = SessionLocal()
            try:
                # Find positions marked as closed (is_open = FALSE)
                # These were manually closed by user via UI
                recently_closed = db.query(Position).filter(
                    Position.is_open == False,
                    Position.closed_at >= datetime.utcnow() - timedelta(minutes=10)
                ).all()
                
                for pos in recently_closed:
                    # Add to reopen queue only if not already there
                    if pos.id not in self.closed_positions_for_reopen:
                        self.closed_positions_for_reopen[pos.id] = pos.closed_at
                        print(f"Pozisyon auto-reopen queue'ya eklendi: {pos.symbol} {pos.side}")
                
            finally:
                db.close()
                
        except Exception as e:
            print(f"Error checking positions: {e}")
    
    def cancel_orphaned_orders(self):
        try:
            self._ensure_strategy()
            if not self.strategy or not self.strategy.client.is_configured():
                return
            
            # TÜM emir türlerini çek (trigger, conditional, iceberg, twap)
            all_orders = self.strategy.client.get_all_open_orders()
            if not all_orders:
                return
            
            all_positions = self.strategy.client.get_all_positions()
            position_keys = set()
            for pos in all_positions:
                inst_id = pos.get('instId', '')
                pos_side = pos.get('posSide', '')
                pos_amt = abs(float(pos.get('positionAmt', 0)))
                if pos_amt > 0:
                    position_keys.add((inst_id, pos_side))
            
            cancelled_count = 0
            for order in all_orders:
                if order.get('state') != 'live':
                    continue
                
                inst_id = order.get('instId', '')
                pos_side = order.get('posSide', '')
                ord_type = order.get('ordType', 'unknown')
                
                if (inst_id, pos_side) not in position_keys:
                    algo_id = order.get('algoId')
                    if algo_id:
                        symbol = inst_id.replace('-USDT-SWAP', '').replace('-', '') + 'USDT'
                        result = self.strategy.client.cancel_algo_order(symbol, algo_id)
                        if result:
                            cancelled_count += 1
                            print(f"Cancelled orphaned {ord_type} order: {algo_id} ({inst_id} {pos_side})")
            
            if cancelled_count > 0:
                print(f"Total orphaned orders cancelled: {cancelled_count}")
                
        except Exception as e:
            print(f"Error cancelling orphaned orders: {e}")
    
    def reopen_closed_positions(self):
        try:
            self._ensure_strategy()
            if not self.strategy or not self.strategy.client.is_configured():
                return
            
            db = SessionLocal()
            try:
                positions_to_reopen = []
                positions_to_remove = []
                current_time = datetime.utcnow()
                
                for pos_id, closed_time in list(self.closed_positions_for_reopen.items()):
                    if current_time >= closed_time + timedelta(minutes=self.auto_reopen_delay_minutes):
                        pos = db.query(Position).filter(Position.id == pos_id).first()
                        if pos and not pos.is_open:
                            positions_to_reopen.append((pos_id, pos))
                        else:
                            # Pozisyon bulunamadı veya zaten açık - queue'dan çıkar
                            positions_to_remove.append(pos_id)
                
                for pos_id, pos in positions_to_reopen:
                    try:
                        # Yeni pozisyon bilgilerini al
                        position_side = pos.position_side if pos.position_side else ("long" if pos.side == "LONG" else "short")
                        
                        # Kontrat miktarını hesapla
                        current_price = self.strategy.client.get_symbol_price(pos.symbol)
                        if not current_price:
                            print(f"Fiyat alınamadı: {pos.symbol}")
                            continue
                        
                        quantity = self.strategy.calculate_quantity_for_usdt(
                            amount_usdt=pos.amount_usdt,
                            leverage=pos.leverage,
                            current_price=current_price,
                            symbol=pos.symbol
                        )
                        
                        # Market order ile pozisyon aç
                        order_result = self.strategy.client.place_market_order(
                            symbol=pos.symbol,
                            side=pos.side,
                            quantity=quantity,
                            position_side=position_side
                        )
                        
                        if not order_result:
                            print(f"Pozisyon yeniden açılamadı: {pos.symbol} {pos.side}")
                            continue
                        
                        import time
                        time.sleep(2)
                        
                        # Yeni pozisyon bilgilerini OKX'ten al
                        okx_pos = self.strategy.client.get_position(pos.symbol, position_side)
                        
                        if not okx_pos:
                            print(f"Pozisyon bilgisi alınamadı: {pos.symbol} {pos.side}")
                            continue
                        
                        new_entry_price = float(okx_pos.get('entryPrice', 0))
                        new_quantity = abs(float(okx_pos.get('positionAmt', 0)))
                        new_pos_id = okx_pos.get('posId')
                        
                        if new_quantity == 0 or not new_pos_id:
                            print(f"Geçersiz pozisyon bilgisi: {pos.symbol} {pos.side}")
                            continue
                        
                        # TP/SL fiyatlarını hesapla
                        tp_price, sl_price = self.strategy.calculate_tp_sl_prices(
                            entry_price=new_entry_price,
                            side=pos.side,
                            tp_usdt=pos.tp_usdt,
                            sl_usdt=pos.sl_usdt,
                            quantity=new_quantity,
                            symbol=pos.symbol
                        )
                        
                        # TP/SL emirlerini yerleştir
                        tp_order_id, sl_order_id = self.strategy.client.place_tp_sl_orders(
                            symbol=pos.symbol,
                            side=pos.side,
                            quantity=new_quantity,
                            entry_price=new_entry_price,
                            tp_price=tp_price,
                            sl_price=sl_price,
                            position_side=position_side
                        )
                        
                        # MEVCUT database kaydını güncelle (yeni kayıt oluşturma!)
                        pos.entry_price = new_entry_price
                        pos.quantity = new_quantity
                        pos.position_id = new_pos_id
                        pos.tp_order_id = tp_order_id
                        pos.sl_order_id = sl_order_id
                        pos.is_open = True
                        pos.opened_at = datetime.utcnow()
                        pos.closed_at = None
                        pos.pnl = None
                        pos.close_reason = None
                        
                        db.commit()
                        
                        # Başarılı reopen - queue'dan çıkar
                        positions_to_remove.append(pos_id)
                        print(f"✅ Pozisyon yeniden açıldı (UPDATE): {pos.symbol} {pos.side} @ ${new_entry_price:.2f} | Qty: {new_quantity} | Bekleme: {self.auto_reopen_delay_minutes} dk | DB ID: {pos.id}")
                        
                    except Exception as e:
                        db.rollback()  # Session'ı temizle
                        print(f"⚠️ Pozisyon yeniden açılamadı (tekrar denenecek): {pos.symbol} {pos.side} | Hata: {e}")
                        # Queue'da bırak, bir sonraki check'te tekrar denesin
                
                # Başarılı ve geçersiz pozisyonları queue'dan temizle
                for pos_id in positions_to_remove:
                    if pos_id in self.closed_positions_for_reopen:
                        del self.closed_positions_for_reopen[pos_id]
                        
            finally:
                db.close()
                
        except Exception as e:
            print(f"Error reopening positions: {e}")
    
    def start(self):
        try:
            if not self.scheduler.running:
                self.scheduler.add_job(
                    self.check_positions,
                    'interval',
                    minutes=1,
                    id='position_checker',
                    replace_existing=True
                )
                
                self.scheduler.add_job(
                    self.cancel_orphaned_orders,
                    'interval',
                    minutes=1,
                    id='order_canceller',
                    replace_existing=True
                )
                
                self.scheduler.add_job(
                    self.reopen_closed_positions,
                    'interval',
                    seconds=30,
                    id='position_reopener',
                    replace_existing=True
                )
                
                self.scheduler.start()
        except Exception as e:
            print(f"Error starting scheduler: {e}")
    
    def stop(self):
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
        except Exception as e:
            print(f"Error stopping scheduler: {e}")
    
    def is_running(self):
        return self.scheduler.running

monitor = None
manually_stopped = True  # Bot otomatik başlamasın, sadece manuel Start ile

def get_monitor():
    global monitor, manually_stopped
    try:
        if monitor is None and not manually_stopped:
            monitor = PositionMonitor()
            monitor.start()
        elif monitor is not None and not monitor.is_running() and not manually_stopped:
            try:
                monitor.stop()
            except:
                pass
            monitor = PositionMonitor()
            monitor.start()
    except Exception as e:
        print(f"Error getting monitor: {e}")
        if not manually_stopped:
            monitor = PositionMonitor()
            try:
                monitor.start()
            except:
                pass
    return monitor

def stop_monitor():
    global monitor, manually_stopped
    try:
        if monitor is not None and monitor.is_running():
            monitor.stop()
            manually_stopped = True
            return True
    except Exception as e:
        print(f"Error stopping monitor: {e}")
    return False

def start_monitor(auto_reopen_delay_minutes: int = 5):
    global monitor, manually_stopped
    try:
        manually_stopped = False
        if monitor is None:
            monitor = PositionMonitor(auto_reopen_delay_minutes)
            monitor.start()
            print(f"🤖 Monitor başlatıldı - Auto-reopen süresi: {auto_reopen_delay_minutes} dakika")
            return True
        elif not monitor.is_running():
            try:
                monitor.stop()
            except:
                pass
            monitor = PositionMonitor(auto_reopen_delay_minutes)
            monitor.start()
            print(f"🤖 Monitor başlatıldı - Auto-reopen süresi: {auto_reopen_delay_minutes} dakika")
            return True
    except Exception as e:
        print(f"Error starting monitor: {e}")
        return False
    return False
