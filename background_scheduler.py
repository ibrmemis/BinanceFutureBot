import threading
import time
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from database import SessionLocal, Position
from trading_strategy import Try1Strategy

class PositionMonitor:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.strategy = None
        self.closed_positions_for_reopen = {}
    
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
            
            self.strategy.check_and_update_positions()
            
            db = SessionLocal()
            try:
                recently_closed = db.query(Position).filter(
                    Position.is_open == False,
                    Position.closed_at >= datetime.utcnow() - timedelta(minutes=10)
                ).all()
                
                for pos in recently_closed:
                    if pos.id not in self.closed_positions_for_reopen:
                        self.closed_positions_for_reopen[pos.id] = pos.closed_at
                
            finally:
                db.close()
                
        except Exception as e:
            print(f"Error checking positions: {e}")
    
    def cancel_orphaned_orders(self):
        try:
            self._ensure_strategy()
            if not self.strategy or not self.strategy.client.is_configured():
                return
            
            all_orders = self.strategy.client.get_algo_orders()
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
                
                if (inst_id, pos_side) not in position_keys:
                    algo_id = order.get('algoId')
                    if algo_id:
                        symbol = inst_id.replace('-USDT-SWAP', '').replace('-', '') + 'USDT'
                        result = self.strategy.client.cancel_algo_order(symbol, algo_id)
                        if result:
                            cancelled_count += 1
                            print(f"Cancelled orphaned order: {algo_id} ({inst_id} {pos_side})")
            
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
                current_time = datetime.utcnow()
                
                for pos_id, closed_time in list(self.closed_positions_for_reopen.items()):
                    if current_time >= closed_time + timedelta(minutes=5):
                        pos = db.query(Position).filter(Position.id == pos_id).first()
                        if pos and not pos.is_open:
                            positions_to_reopen.append(pos)
                        del self.closed_positions_for_reopen[pos_id]
                
                for pos in positions_to_reopen:
                    success, message, new_pos_id = self.strategy.open_position(
                        symbol=pos.symbol,
                        side=pos.side,
                        amount_usdt=pos.amount_usdt,
                        leverage=pos.leverage,
                        tp_usdt=pos.tp_usdt,
                        sl_usdt=pos.sl_usdt,
                        parent_position_id=pos.id,
                        reopen_count=pos.reopen_count + 1,
                        save_to_db=False
                    )
                    
                    if success:
                        pos.reopen_count += 1
                        pos.closed_at = datetime.utcnow() - timedelta(minutes=15)
                        db.commit()
                        print(f"Pozisyon yeniden açıldı: {message}")
                    else:
                        print(f"Pozisyon yeniden açılamadı: {message}")
                        
            finally:
                db.close()
                
        except Exception as e:
            print(f"Error reopening positions: {e}")
    
    def start(self):
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
        
        if not self.scheduler.running:
            self.scheduler.start()
    
    def stop(self):
        if self.scheduler.running:
            self.scheduler.shutdown()
    
    def is_running(self):
        return self.scheduler.running

monitor = None

def get_monitor():
    global monitor
    if monitor is None:
        monitor = PositionMonitor()
        monitor.start()
    return monitor

def stop_monitor():
    global monitor
    if monitor is not None and monitor.is_running():
        monitor.stop()
        return True
    return False

def start_monitor():
    global monitor
    if monitor is None:
        monitor = PositionMonitor()
        monitor.start()
        return True
    elif not monitor.is_running():
        monitor.start()
        return True
    return False
