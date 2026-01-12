import threading
import time
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.pool import ThreadPoolExecutor
from database import SessionLocal, Position, Settings
from database_utils import get_db_session, DatabaseManager
from trading_strategy import TradingStrategy
from constants import (
    SchedulerConstants, DatabaseConstants, TradingConstants,
    ErrorMessages, SuccessMessages
)
from utils import setup_logger

logger = setup_logger("background_scheduler")

class PositionMonitor:
    def __init__(self, auto_reopen_delay_minutes: int = None):
        jobstores = {
            'default': MemoryJobStore()
        }
        executors = {
            'default': ThreadPoolExecutor(max_workers=SchedulerConstants.MAX_WORKERS)
        }
        job_defaults = {
            'coalesce': SchedulerConstants.COALESCE_JOBS,
            'max_instances': SchedulerConstants.MAX_INSTANCES,
            'misfire_grace_time': SchedulerConstants.MISFIRE_GRACE_TIME
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
        delay = DatabaseManager.get_setting(
            DatabaseConstants.SETTING_AUTO_REOPEN_DELAY,
            TradingConstants.DEFAULT_RECOVERY_DELAY
        )
        try:
            return int(delay)
        except (ValueError, TypeError):
            self._save_auto_reopen_delay(TradingConstants.DEFAULT_RECOVERY_DELAY)
            return TradingConstants.DEFAULT_RECOVERY_DELAY
    
    def _load_recovery_settings(self) -> dict:
        with get_db_session() as db:
            settings = {}
            
            # Recovery enabled (default True)
            enabled = db.query(Settings).filter(Settings.key == "recovery_enabled").first()
            settings['enabled'] = enabled.value.lower() == 'true' if enabled else True
            
            # New TP (USDT) - same for all steps
            tp = db.query(Settings).filter(Settings.key == "recovery_tp_usdt").first()
            settings['tp_usdt'] = float(tp.value) if tp else 8.0
            
            # New SL (USDT) - same for all steps
            sl = db.query(Settings).filter(Settings.key == "recovery_sl_usdt").first()
            settings['sl_usdt'] = float(sl.value) if sl else 500.0
            
            # Load multi-step recovery settings with per-step TP/SL (up to 5 steps)
            steps = []
            for i in range(1, 6):
                trigger_key = f"recovery_step_{i}_trigger"
                add_key = f"recovery_step_{i}_add"
                tp_key = f"recovery_step_{i}_tp"
                sl_key = f"recovery_step_{i}_sl"
                
                trigger = db.query(Settings).filter(Settings.key == trigger_key).first()
                add_amount = db.query(Settings).filter(Settings.key == add_key).first()
                tp_step = db.query(Settings).filter(Settings.key == tp_key).first()
                sl_step = db.query(Settings).filter(Settings.key == sl_key).first()
                
                if trigger and add_amount:
                    steps.append({
                        'trigger_pnl': float(trigger.value),
                        'add_amount': float(add_amount.value),
                        'tp_usdt': float(tp_step.value) if tp_step else settings.get('tp_usdt', 50.0),
                        'sl_usdt': float(sl_step.value) if sl_step else settings.get('sl_usdt', 100.0)
                    })
            
            # If no steps defined, use default values
            if not steps:
                steps = [
                    {'trigger_pnl': -50.0, 'add_amount': 3000.0, 'tp_usdt': 30.0, 'sl_usdt': 1200.0}
                ]
            
            settings['steps'] = steps
            
            return settings
    
    def _save_auto_reopen_delay(self, minutes: int):
        DatabaseManager.set_setting(DatabaseConstants.SETTING_AUTO_REOPEN_DELAY, str(minutes))
    
    def _ensure_strategy(self):
        if self.strategy is None:
            self.strategy = TradingStrategy()
        elif not self.strategy.client.is_configured():
            self.strategy = TradingStrategy()
        
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
            
            if not steps:
                return
            
            # Collect positions that need recovery (don't hold DB session during API calls)
            positions_to_recover = []
            
            with get_db_session() as db:
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
                    
                    # Get the next step's trigger, add amount, and per-step TP/SL
                    next_step = steps[current_recovery_count]
                    trigger_pnl = next_step['trigger_pnl']
                    add_amount = next_step['add_amount']
                    step_tp_usdt = next_step.get('tp_usdt', 50.0)
                    step_sl_usdt = next_step.get('sl_usdt', 100.0)
                    
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
                            'tp_usdt': step_tp_usdt,
                            'sl_usdt': step_sl_usdt,
                            'step_num': current_recovery_count + 1
                        })
            
            # Process each position for recovery (separate DB session per recovery)
            for pos_data in positions_to_recover:
                pos_id = pos_data['pos_id']
                
                if pos_id in self.positions_in_recovery:
                    continue
                
                logger.info(f"🚨 RECOVERY STEP {pos_data['step_num']} TRIGGERED: {pos_data['symbol']} {pos_data['side']} | PNL: ${pos_data['unrealized_pnl']:.2f} <= ${pos_data['trigger_pnl']:.2f} | Add: ${pos_data['add_amount']:.2f} | TP:{pos_data['tp_usdt']} SL:{pos_data['sl_usdt']}")
                
                self.positions_in_recovery.add(pos_id)
                
                try:
                    success, message = self.strategy.execute_recovery(
                        position_db_id=pos_id,
                        add_amount_usdt=pos_data['add_amount'],
                        new_tp_usdt=pos_data['tp_usdt'],
                        new_sl_usdt=pos_data['sl_usdt']
                    )
                    
                    if success:
                        logger.info(f"✅ {message}")
                    else:
                        logger.error(f"❌ Recovery failed: {message}")
                        
                except Exception as e:
                    logger.error(f"❌ Recovery exception: {pos_data['symbol']} {pos_data['side']} | Error: {e}")
                finally:
                    self.positions_in_recovery.discard(pos_id)
                
        except Exception as e:
            logger.error(f"Error checking recovery: {e}")
            self.positions_in_recovery.clear()
    
    def check_positions(self):
        try:
            logger.debug("Checking positions...")
            self._ensure_strategy()
            if not self.strategy or not self.strategy.client.is_configured():
                return
            
            # DO NOT call check_and_update_positions() - we don't want to auto-close positions
            # User controls position state manually via UI buttons
            
            with get_db_session() as db:
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
                        logger.info(f"🔴 Position manually closed on OKX - added to queue: {pos.symbol} {pos.side}")
                
        except Exception as e:
            logger.error(f"Error checking positions: {e}")
    
    def check_and_restore_tp_sl_orders(self):
        """Check if TP/SL orders exist for open positions and restore if missing"""
        try:
            self._ensure_strategy()
            if not self.strategy or not self.strategy.client.is_configured():
                return
            
            with get_db_session() as db:
                active_positions = db.query(Position).filter(Position.is_open == True).all()
                
                for pos in active_positions:
                    # Check if orders are disabled for this position
                    if getattr(pos, 'orders_disabled', False):
                        continue  # Skip restoring orders for this position

                    position_side = pos.position_side if pos.position_side else ("long" if pos.side == "LONG" else "short")

                    # Get current position from OKX
                    okx_pos = self.strategy.client.get_position(pos.symbol, position_side)
                    if not okx_pos or abs(float(okx_pos.get('positionAmt', 0))) == 0:
                        continue

                    # Get current PNL
                    unrealized_pnl = float(okx_pos.get('unrealizedProfit', 0))
                    entry_price = float(okx_pos.get('entryPrice', 0))
                    quantity = abs(float(okx_pos.get('positionAmt', 0)))

                    # Get all orders for this position
                    all_orders = self.strategy.client.get_all_open_orders(pos.symbol)
                    if all_orders is None:
                        logger.warning(f"Could not fetch orders for {pos.symbol}, skipping check")
                        continue

                    inst_id = self.strategy.client.convert_symbol_to_okx(pos.symbol)

                    # Check if TP/SL orders exist
                    has_tp = False
                    has_sl = False

                    for order in all_orders:
                        if order.get('instId') == inst_id and order.get('posSide') == position_side:
                            trigger_px = float(order.get('triggerPx', 0))
                            if pos.side == "LONG":
                                if trigger_px > entry_price:
                                    has_tp = True
                                elif trigger_px < entry_price:
                                    has_sl = True
                            else:  # SHORT
                                if trigger_px < entry_price:
                                    has_tp = True
                                elif trigger_px > entry_price:
                                    has_sl = True

                    # Use original TP/SL values if available
                    tp_usdt = pos.original_tp_usdt if pos.original_tp_usdt is not None else pos.tp_usdt
                    sl_usdt = pos.original_sl_usdt if pos.original_sl_usdt is not None else pos.sl_usdt

                    # Restore missing TP order
                    if not has_tp and tp_usdt:
                        # Check if TP target already reached
                        if unrealized_pnl >= tp_usdt:
                            logger.info(f"🎯 TP target already reached ({unrealized_pnl:.2f} >= {tp_usdt}), closing position: {pos.symbol} {pos.side}")
                            # Close position immediately
                            close_side = "sell" if pos.side == "LONG" else "buy"
                            self.strategy.client.close_position_market(pos.symbol, close_side, int(quantity), position_side)
                            pos.is_open = False
                            pos.closed_at = datetime.now(timezone.utc)
                            pos.pnl = unrealized_pnl
                            pos.close_reason = "TP"
                            db.commit()
                        else:
                            # Place TP order
                            tp_price, _ = self.strategy.calculate_tp_sl_prices(
                                entry_price, pos.side, tp_usdt, sl_usdt, quantity, pos.symbol
                            )
                            
                            close_side = "sell" if pos.side == "LONG" else "buy"
                            tick_size = self.strategy.client.get_tick_size(pos.symbol)
                            formatted_tp = self.strategy.client.format_price(tp_price, tick_size)
                            
                            result = self.strategy.client.trade_api.place_algo_order(
                                instId=inst_id,
                                tdMode="cross",
                                side=close_side,
                                posSide=position_side,
                                ordType="trigger",
                                sz=str(int(quantity)),
                                triggerPx=formatted_tp,
                                orderPx="-1"
                            )
                            
                            if result.get('code') == '0':
                                tp_order_id = result['data'][0]['algoId']
                                pos.tp_order_id = tp_order_id
                                db.commit()
                                logger.info(f"✅ TP order restored: {pos.symbol} {pos.side} @ {formatted_tp}")
                    
                    # Restore missing SL order
                    if not has_sl and sl_usdt:
                        # Check if SL target already reached
                        if unrealized_pnl <= -sl_usdt:
                            logger.info(f"🛡️ SL target already reached ({unrealized_pnl:.2f} <= -{sl_usdt}), closing position: {pos.symbol} {pos.side}")
                            # Close position immediately
                            close_side = "sell" if pos.side == "LONG" else "buy"
                            self.strategy.client.close_position_market(pos.symbol, close_side, int(quantity), position_side)
                            pos.is_open = False
                            pos.closed_at = datetime.now(timezone.utc)
                            pos.pnl = unrealized_pnl
                            pos.close_reason = "SL"
                            db.commit()
                        else:
                            # Place SL order
                            _, sl_price = self.strategy.calculate_tp_sl_prices(
                                entry_price, pos.side, tp_usdt, sl_usdt, quantity, pos.symbol
                            )
                            
                            close_side = "sell" if pos.side == "LONG" else "buy"
                            tick_size = self.strategy.client.get_tick_size(pos.symbol)
                            formatted_sl = self.strategy.client.format_price(sl_price, tick_size)
                            
                            result = self.strategy.client.trade_api.place_algo_order(
                                instId=inst_id,
                                tdMode="cross",
                                side=close_side,
                                posSide=position_side,
                                ordType="trigger",
                                sz=str(int(quantity)),
                                triggerPx=formatted_sl,
                                orderPx="-1"
                            )
                            
                            if result.get('code') == '0':
                                sl_order_id = result['data'][0]['algoId']
                                pos.sl_order_id = sl_order_id
                                db.commit()
                                logger.info(f"✅ SL order restored: {pos.symbol} {pos.side} @ {formatted_sl}")
                
        except Exception as e:
            logger.error(f"Error checking/restoring TP/SL orders: {e}")
    
    def cancel_orphaned_orders(self):
        try:
            self._ensure_strategy()
            if not self.strategy or not self.strategy.client.is_configured():
                return
            
            # Database'den aktif pozisyonların TP/SL emir ID'lerini al
            with get_db_session() as db:
                active_tp_sl_ids = set()
                active_positions = db.query(Position).filter(Position.is_open == True).all()
                for pos in active_positions:
                    if pos.tp_order_id:
                        active_tp_sl_ids.add(pos.tp_order_id)
                    if pos.sl_order_id:
                        active_tp_sl_ids.add(pos.sl_order_id)
            
            # TÜM emir türlerini çek (trigger, conditional, iceberg, twap)
            all_orders = self.strategy.client.get_all_open_orders()
            if all_orders is None:
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
                            logger.info(f"✂️ Cancelled orphaned {ord_type} order: {algo_id} ({inst_id} {pos_side})")
                        else:
                            logger.error(f"❌ Failed to cancel {ord_type} order: {algo_id}")
            
            if cancelled_count > 0:
                logger.info(f"Total orphaned orders cancelled: {cancelled_count}")
                
        except Exception as e:
            logger.error(f"Error cancelling orphaned orders: {e}")
    
    def reopen_closed_positions(self):
        try:
            if self.closed_positions_for_reopen:
                logger.info(f"Waiting to reopen {len(self.closed_positions_for_reopen)} positions.")
            self._ensure_strategy()
            if not self.strategy or not self.strategy.client.is_configured():
                return
            
            with get_db_session() as db:
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
                            logger.info(f"Position already open on OKX: {pos.symbol} {pos.side} - removed from queue")
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
                            logger.warning(f"Price not available: {pos.symbol}")
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
                            logger.error(f"Failed to reopen position: {pos.symbol} {pos.side}")
                            continue
                        
                        import time
                        time.sleep(2)
                        
                        # Yeni pozisyon bilgilerini OKX'ten al
                        okx_pos = self.strategy.client.get_position(pos.symbol, position_side)
                        
                        if not okx_pos:
                            logger.error(f"Failed to get position info: {pos.symbol} {pos.side}")
                            continue
                        
                        new_entry_price = float(okx_pos.get('entryPrice', 0))
                        new_quantity = abs(float(okx_pos.get('positionAmt', 0)))
                        new_pos_id = okx_pos.get('posId')
                        
                        if new_quantity == 0 or not new_pos_id:
                            logger.error(f"Invalid position info: {pos.symbol} {pos.side}")
                            continue
                        
                        # TP/SL fiyatlarını hesapla (orijinal değerleri kullan)
                        tp_usdt_for_reopen = pos.original_tp_usdt if pos.original_tp_usdt is not None else pos.tp_usdt
                        sl_usdt_for_reopen = pos.original_sl_usdt if pos.original_sl_usdt is not None else pos.sl_usdt

                        tp_price, sl_price = self.strategy.calculate_tp_sl_prices(
                            entry_price=new_entry_price,
                            side=pos.side,
                            tp_usdt=tp_usdt_for_reopen,
                            sl_usdt=sl_usdt_for_reopen,
                            quantity=new_quantity,
                            symbol=pos.symbol
                        )
                        
                        # ESKİ TP/SL emirlerini iptal et (eğer varsa)
                        if pos.tp_order_id:
                            try:
                                self.strategy.client.cancel_algo_order(pos.symbol, pos.tp_order_id)
                                logger.info(f"🗑️ Old TP order cancelled: {pos.tp_order_id}")
                            except Exception as e:
                                logger.warning(f"⚠️ Could not cancel old TP: {e}")
                        
                        if pos.sl_order_id:
                            try:
                                self.strategy.client.cancel_algo_order(pos.symbol, pos.sl_order_id)
                                logger.info(f"🗑️ Old SL order cancelled: {pos.sl_order_id}")
                            except Exception as e:
                                logger.warning(f"⚠️ Could not cancel old SL: {e}")
                        
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
                        pos.recovery_count = 0
                        pos.last_recovery_at = None
                        # Reset TP/SL to original values (not recovery values)
                        pos.tp_usdt = tp_usdt_for_reopen
                        pos.sl_usdt = sl_usdt_for_reopen
                        
                        db.commit()
                        
                        # Başarılı reopen - queue'dan çıkar
                        positions_to_remove.append(pos_id)
                        logger.info(f"✅ Position reopened (UPDATE): {pos.symbol} {pos.side} @ ${new_entry_price:.2f} | Qty: {new_quantity} | Delay: {self.auto_reopen_delay_minutes} min | DB ID: {pos.id}")
                        
                    except Exception as e:
                        db.rollback()  # Session'ı temizle
                        logger.error(f"⚠️ Failed to reopen position (will retry): {pos.symbol} {pos.side} | Error: {e}")
                        # Queue'da bırak, bir sonraki check'te tekrar denesin
                
                # Başarılı ve geçersiz pozisyonları queue'dan temizle
                for pos_id in positions_to_remove:
                    if pos_id in self.closed_positions_for_reopen:
                        del self.closed_positions_for_reopen[pos_id]
                
        except Exception as e:
            logger.error(f"Error reopening positions: {e}")
    
    def start(self):
        try:
            if not self.scheduler.running:
                self.scheduler.add_job(
                    self.check_positions,
                    'interval',
                    seconds=SchedulerConstants.POSITION_CHECK_INTERVAL,
                    id='position_checker',
                    replace_existing=True
                )
                
                self.scheduler.add_job(
                    self.cancel_orphaned_orders,
                    'interval',
                    seconds=SchedulerConstants.ORDER_CLEANUP_INTERVAL,
                    id='order_canceller',
                    replace_existing=True
                )
                
                self.scheduler.add_job(
                    self.check_and_restore_tp_sl_orders,
                    'interval',
                    seconds=SchedulerConstants.ORDER_CLEANUP_INTERVAL,
                    id='tp_sl_restorer',
                    replace_existing=True
                )
                
                self.scheduler.add_job(
                    self.reopen_closed_positions,
                    'interval',
                    seconds=SchedulerConstants.POSITION_REOPEN_INTERVAL,
                    id='position_reopener',
                    replace_existing=True
                )
                
                self.scheduler.add_job(
                    self.check_recovery,
                    'interval',
                    seconds=SchedulerConstants.RECOVERY_CHECK_INTERVAL,
                    id='recovery_checker',
                    replace_existing=True
                )
                
                self.scheduler.start()
        except Exception as e:
            logger.error(f"Error starting scheduler: {e}")
    
    def stop(self):
        try:
            if self.scheduler.running:
                self.scheduler.shutdown(wait=False)
        except Exception as e:
            logger.error(f"Error stopping scheduler: {e}")
    
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
        logger.error(f"Error getting monitor: {e}")
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
        logger.error(f"Error stopping monitor: {e}")
    return False

def start_monitor(auto_reopen_delay_minutes: int = 5):
    global monitor, manually_stopped
    try:
        manually_stopped = False

        # Reset orders_disabled for all positions when bot starts
        with get_db_session() as db:
            disabled_positions = db.query(Position).filter(Position.orders_disabled == True).count()
            db.query(Position).update({"orders_disabled": False})
            db.commit()
            if disabled_positions > 0:
                logger.info(f"🔄 {disabled_positions} positions re-enabled for order restoration")
            else:
                logger.info("🔄 All positions already enabled for order restoration")

        # Auto-enable recovery when bot starts
        with get_db_session() as db:
            recovery_setting = db.query(Settings).filter(Settings.key == "recovery_enabled").first()
            if recovery_setting:
                recovery_setting.value = "true"
            else:
                recovery_setting = Settings(key="recovery_enabled", value="true")
                db.add(recovery_setting)
            db.commit()
            logger.info("🛡️ Recovery feature auto-enabled")
        
        if monitor is None:
            monitor = PositionMonitor(auto_reopen_delay_minutes)
            monitor.start()
            logger.info(f"🤖 Monitor started - Auto-reopen delay: {auto_reopen_delay_minutes} minutes")
            return True
        elif not monitor.is_running():
            try:
                monitor.stop()
            except:
                pass
            monitor = PositionMonitor(auto_reopen_delay_minutes)
            monitor.start()
            logger.info(f"🤖 Monitor started - Auto-reopen delay: {auto_reopen_delay_minutes} minutes")
            return True
    except Exception as e:
        logger.error(f"Error starting monitor: {e}")
        return False
    return False
