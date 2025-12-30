import threading
import time
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from database import SessionLocal, Position, Settings
from trading_strategy import Try1Strategy

class PositionMonitor:
    def __init__(self, auto_reopen_delay_minutes: int = None):
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': ThreadPoolExecutor(max_workers=3)
        }
        job_defaults = {
            'coalesce': True,
            'max_instances': 1,
            'misfire_grace_time': 30
        }
        self.scheduler = BackgroundScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults
        )
        self.strategy = None
        self.closed_positions_for_reopen = {}
        self.positions_in_recovery = set()
        
        # Load auto_reopen_delay from database or use provided value
        if auto_reopen_delay_minutes is None:
            self.auto_reopen_delay_minutes = self._load_auto_reopen_delay()
        else:
            self.auto_reopen_delay_minutes = auto_reopen_delay_minutes
            self._save_auto_reopen_delay(auto_reopen_delay_minutes)
    
    def _load_auto_reopen_delay(self) -> int:
        """Load auto-reopen delay from database, default to 1 minute if not set"""
        db = SessionLocal()
        try:
            setting = db.query(Settings).filter(Settings.key == "auto_reopen_delay_minutes").first()
            if setting:
                return int(setting.value)
            else:
                # Default to 1 minute and save it
                self._save_auto_reopen_delay(1)
                return 1
        finally:
            db.close()
    
    def _load_recovery_settings(self) -> dict:
        """Load recovery settings from database with multi-step support"""
        db = SessionLocal()
        try:
            settings = {}
            
            # Recovery enabled
            enabled = db.query(Settings).filter(Settings.key == "recovery_enabled").first()
            settings['enabled'] = enabled.value.lower() == 'true' if enabled else False
            
            # New TP (USDT) - same for all steps
            tp = db.query(Settings).filter(Settings.key == "recovery_tp_usdt").first()
            settings['tp_usdt'] = float(tp.value) if tp else 50.0
            
            # New SL (USDT) - same for all steps
            sl = db.query(Settings).filter(Settings.key == "recovery_sl_usdt").first()
            settings['sl_usdt'] = float(sl.value) if sl else 100.0
            
            # Load multi-step recovery settings (up to 5 steps)
            steps = []
            for i in range(1, 6):
                trigger_key = f"recovery_step_{i}_trigger"
                add_key = f"recovery_step_{i}_add"
                
                trigger = db.query(Settings).filter(Settings.key == trigger_key).first()
                add_amount = db.query(Settings).filter(Settings.key == add_key).first()
                
                if trigger and add_amount:
                    steps.append({
                        'trigger_pnl': float(trigger.value),
                        'add_amount': float(add_amount.value)
                    })
            
            # If no steps defined, use legacy single-step settings
            if not steps:
                trigger = db.query(Settings).filter(Settings.key == "recovery_trigger_pnl").first()
                add_amount = db.query(Settings).filter(Settings.key == "recovery_add_amount").first()
                steps.append({
                    'trigger_pnl': float(trigger.value) if trigger else -50.0,
                    'add_amount': float(add_amount.value) if add_amount else 100.0
                })
            
            settings['steps'] = steps
            
            return settings
        finally:
            db.close()
    
    def _save_auto_reopen_delay(self, minutes: int):
        """Save auto-reopen delay to database"""
        db = SessionLocal()
        try:
            setting = db.query(Settings).filter(Settings.key == "auto_reopen_delay_minutes").first()
            if setting:
                setting.value = str(minutes)
                setting.updated_at = datetime.now(timezone.utc)
            else:
                setting = Settings(key="auto_reopen_delay_minutes", value=str(minutes))
                db.add(setting)
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"Warning: Could not save auto_reopen_delay: {e}")
        finally:
            db.close()
    
    def _ensure_strategy(self):
        if self.strategy is None:
            self.strategy = Try1Strategy()
        elif not self.strategy.client.is_configured():
            self.strategy = Try1Strategy()
        
    def check_recovery(self):
        """Check positions for multi-step recovery trigger (PNL drops below threshold)"""
        try:
            recovery_settings = self._load_recovery_settings()
            
            if not recovery_settings.get('enabled', False):
                return
            
            self._ensure_strategy()
            if not self.strategy or not self.strategy.client.is_configured():
                return
            
            steps = recovery_settings.get('steps', [])
            tp_usdt = recovery_settings.get('tp_usdt', 50.0)
            sl_usdt = recovery_settings.get('sl_usdt', 100.0)
            
            if not steps:
                return
            
            # Collect positions that need recovery (don't hold DB session during API calls)
            positions_to_recover = []
            
            db = SessionLocal()
            try:
                open_positions = db.query(Position).filter(Position.is_open == True).all()
                
                for pos in open_positions:
                    pos_id = pos.id
                    
                    if pos_id in self.positions_in_recovery:
                        continue
                    
                    # Get current recovery count
                    current_recovery_count = pos.recovery_count if pos.recovery_count else 0
                    
                    # Check if all steps exhausted
                    if current_recovery_count >= len(steps):
                        continue  # All recovery steps used, skip this position
                    
                    # Get the next step's trigger and add amount
                    next_step = steps[current_recovery_count]
                    trigger_pnl = next_step['trigger_pnl']
                    add_amount = next_step['add_amount']
                    
                    position_side = pos.position_side if pos.position_side else ("long" if pos.side == "LONG" else "short")
                    okx_pos = self.strategy.client.get_position(pos.symbol, position_side)
                    
                    if not okx_pos:
                        continue
                    
                    pos_amt = abs(float(okx_pos.get('positionAmt', 0)))
                    if pos_amt == 0:
                        continue
                    
                    unrealized_pnl = float(okx_pos.get('unrealizedProfit', 0))
                    
                    if unrealized_pnl <= trigger_pnl:
                        positions_to_recover.append({
                            'pos_id': pos_id,
                            'symbol': str(pos.symbol),
                            'side': str(pos.side),
                            'unrealized_pnl': unrealized_pnl,
                            'trigger_pnl': trigger_pnl,
                            'add_amount': add_amount,
                            'step_num': current_recovery_count + 1
                        })
            finally:
                db.close()
            
            # Process each position for recovery (separate DB session per recovery)
            for pos_data in positions_to_recover:
                pos_id = pos_data['pos_id']
                
                if pos_id in self.positions_in_recovery:
                    continue
                
                print(f"🚨 RECOVERY BASAMAK {pos_data['step_num']} TETİKLENDİ: {pos_data['symbol']} {pos_data['side']} | PNL: ${pos_data['unrealized_pnl']:.2f} <= ${pos_data['trigger_pnl']:.2f} | Eklenecek: ${pos_data['add_amount']:.2f}")
                
                self.positions_in_recovery.add(pos_id)
                
                try:
                    success, message = self.strategy.execute_recovery(
                        position_db_id=pos_id,
                        add_amount_usdt=pos_data['add_amount'],
                        new_tp_usdt=tp_usdt,
                        new_sl_usdt=sl_usdt
                    )
                    
                    if success:
                        print(f"✅ {message}")
                    else:
                        print(f"❌ Recovery başarısız: {message}")
                        
                except Exception as e:
                    print(f"❌ Recovery exception: {pos_data['symbol']} {pos_data['side']} | Hata: {e}")
                finally:
                    self.positions_in_recovery.discard(pos_id)
                
        except Exception as e:
            print(f"Error checking recovery: {e}")
            self.positions_in_recovery.clear()
    
    def check_positions(self):
        try:
            print("LOG: Pozisyonlar kontrol ediliyor...")
            self._ensure_strategy()
            if not self.strategy or not self.strategy.client.is_configured():
                return
            
            # DO NOT call check_and_update_positions() - we don't want to auto-close positions
            # User controls position state manually via UI buttons
            
            db = SessionLocal()
            try:
                # Only check for positions that are OPEN in database but CLOSED on OKX
                # This detects manual closures on OKX platform
                all_open = db.query(Position).filter(
                    Position.is_open == True
                ).all()
                
                for pos in all_open:
                    # Skip if already in queue
                    if pos.id in self.closed_positions_for_reopen:
                        continue
                    
                    # Check if position is actually open on OKX
                    position_side = pos.position_side if pos.position_side else ("long" if pos.side == "LONG" else "short")
                    okx_pos = self.strategy.client.get_position(pos.symbol, position_side)
                    
                    is_open_on_okx = False
                    if okx_pos:
                        pos_amt = abs(float(okx_pos.get('positionAmt', 0)))
                        is_open_on_okx = pos_amt > 0
                    
                    # If position is marked OPEN in database but CLOSED on OKX, queue it for reopen
                    if not is_open_on_okx:
                        self.closed_positions_for_reopen[pos.id] = datetime.now(timezone.utc)
                        print(f"🔴 Pozisyon OKX'te manuel kapatılmış - queue'ya eklendi: {pos.symbol} {pos.side}")
                
            finally:
                db.close()
                
        except Exception as e:
            print(f"Error checking positions: {e}")
    
    def cancel_orphaned_orders(self):
        try:
            self._ensure_strategy()
            if not self.strategy or not self.strategy.client.is_configured():
                return
            
            # Database'den aktif pozisyonların TP/SL emir ID'lerini al
            db = SessionLocal()
            try:
                active_tp_sl_ids = set()
                active_positions = db.query(Position).filter(Position.is_open == True).all()
                for pos in active_positions:
                    if pos.tp_order_id:
                        active_tp_sl_ids.add(pos.tp_order_id)
                    if pos.sl_order_id:
                        active_tp_sl_ids.add(pos.sl_order_id)
            finally:
                db.close()
            
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
                algo_id = order.get('algoId')
                
                # KORUMA: Database'de kayıtlı TP/SL emirlerini ATLA
                if algo_id and algo_id in active_tp_sl_ids:
                    continue
                
                # Check if order is orphaned (no matching position)
                if (inst_id, pos_side) not in position_keys:
                    if algo_id:
                        symbol = inst_id.replace('-USDT-SWAP', '').replace('-', '') + 'USDT'
                        result = self.strategy.client.cancel_algo_order(symbol, algo_id)
                        if result:
                            cancelled_count += 1
                            print(f"✂️ Cancelled orphaned {ord_type} order: {algo_id} ({inst_id} {pos_side})")
                        else:
                            print(f"❌ Failed to cancel {ord_type} order: {algo_id}")
            
            if cancelled_count > 0:
                print(f"Total orphaned orders cancelled: {cancelled_count}")
                
        except Exception as e:
            print(f"Error cancelling orphaned orders: {e}")
    
    def reopen_closed_positions(self):
        try:
            if self.closed_positions_for_reopen:
                print(f"LOG: Yeniden açılmayı bekleyen {len(self.closed_positions_for_reopen)} pozisyon var.")
            self._ensure_strategy()
            if not self.strategy or not self.strategy.client.is_configured():
                return
            
            db = SessionLocal()
            try:
                positions_to_reopen = []
                positions_to_remove = []
                current_time = datetime.now(timezone.utc)
                
                for pos_id, closed_time in list(self.closed_positions_for_reopen.items()):
                    if current_time >= closed_time + timedelta(minutes=self.auto_reopen_delay_minutes):
                        pos = db.query(Position).filter(Position.id == pos_id).first()
                        if not pos:
                            # Pozisyon bulunamadı - queue'dan çıkar
                            positions_to_remove.append(pos_id)
                            continue
                        
                        # OKX'te pozisyon açık mı kontrol et
                        position_side = pos.position_side if pos.position_side else ("long" if pos.side == "LONG" else "short")
                        okx_pos = self.strategy.client.get_position(pos.symbol, position_side)
                        
                        is_open_on_okx = False
                        if okx_pos:
                            pos_amt = abs(float(okx_pos.get('positionAmt', 0)))
                            is_open_on_okx = pos_amt > 0
                        
                        if is_open_on_okx:
                            # Pozisyon zaten OKX'te açık - queue'dan çıkar
                            positions_to_remove.append(pos_id)
                            print(f"Pozisyon zaten OKX'te açık: {pos.symbol} {pos.side} - queue'dan çıkarıldı")
                        elif pos.is_open:
                            # Database'de açık ama OKX'te kapalı - yeniden aç
                            positions_to_reopen.append((pos_id, pos))
                        else:
                            # Database'de kapalı ve OKX'te de kapalı - yeniden aç
                            positions_to_reopen.append((pos_id, pos))
                
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
                        
                        # ESKİ TP/SL emirlerini iptal et (eğer varsa)
                        if pos.tp_order_id:
                            try:
                                self.strategy.client.cancel_algo_order(pos.symbol, pos.tp_order_id)
                                print(f"🗑️ Eski TP emri iptal edildi: {pos.tp_order_id}")
                            except Exception as e:
                                print(f"⚠️ Eski TP iptal edilemedi (muhtemelen zaten yok): {e}")
                        
                        if pos.sl_order_id:
                            try:
                                self.strategy.client.cancel_algo_order(pos.symbol, pos.sl_order_id)
                                print(f"🗑️ Eski SL emri iptal edildi: {pos.sl_order_id}")
                            except Exception as e:
                                print(f"⚠️ Eski SL iptal edilemedi (muhtemelen zaten yok): {e}")
                        
                        # YENİ TP/SL emirlerini yerleştir
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
                        pos.opened_at = datetime.now(timezone.utc)
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
                    seconds=30,
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
                
                self.scheduler.add_job(
                    self.check_recovery,
                    'interval',
                    seconds=15,
                    id='recovery_checker',
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
        
        # Auto-enable recovery when bot starts
        db = SessionLocal()
        try:
            recovery_setting = db.query(Settings).filter(Settings.key == "recovery_enabled").first()
            if recovery_setting:
                recovery_setting.value = "true"
            else:
                recovery_setting = Settings(key="recovery_enabled", value="true")
                db.add(recovery_setting)
            db.commit()
            print("🛡️ Kurtarma özelliği otomatik aktifleştirildi")
        finally:
            db.close()
        
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
