import streamlit as st
from database import SessionLocal, APICredentials, Settings, Position
from services import get_cached_client
from background_scheduler import get_monitor, stop_monitor, start_monitor
import time

def show_settings_page():
    st.markdown("#### ⚙️ Ayarlar")
    
    db = SessionLocal()
    try:
        # Load existing credentials
        creds = db.query(APICredentials).first()
        
        # Demo credentials
        demo_api_key = ""
        demo_api_secret = ""
        demo_passphrase = ""
        
        # Real credentials
        real_api_key = ""
        real_api_secret = ""
        real_passphrase = ""
        
        existing_is_demo = True
        
        if creds:
            try:
                # Try to load demo credentials
                if creds.demo_api_key_encrypted:
                    demo_api_key, demo_api_secret, demo_passphrase = creds.get_credentials(is_demo=True)
                
                # Try to load real credentials
                if creds.real_api_key_encrypted:
                    real_api_key, real_api_secret, real_passphrase = creds.get_credentials(is_demo=False)
                
                existing_is_demo = getattr(creds, 'is_demo', True)
            except:
                pass
        
        st.markdown("##### 🔑 API")
        
        # Create tabs for Demo and Real accounts
        api_tab_demo, api_tab_real = st.tabs(["🧪 Demo Hesap API", "💰 Gerçek Hesap API"])
        
        with api_tab_demo:
            st.info("Demo hesap API anahtarlarınızı buraya girin (flag=1)")
            
            col_demo1, col_demo2, col_demo3 = st.columns(3)
            with col_demo1:
                demo_key_input = st.text_input("Demo API Key", value=demo_api_key, type="password", key="demo_api_key")
            with col_demo2:
                demo_secret_input = st.text_input("Demo API Secret", value=demo_api_secret, type="password", key="demo_api_secret")
            with col_demo3:
                demo_pass_input = st.text_input("Demo Passphrase", value=demo_passphrase, type="password", key="demo_passphrase")
            
            if st.button("💾 Demo API Kaydet", key="save_demo_api", type="primary"):
                if not demo_key_input or not demo_secret_input or not demo_pass_input:
                    st.error("Lütfen tüm alanları doldurun.")
                else:
                    if not creds:
                        creds = APICredentials(is_demo=True)
                        db.add(creds)
                    
                    creds.set_credentials(demo_key_input, demo_secret_input, demo_pass_input, is_demo=True)
                    db.commit()
                    st.success("✅ Demo API anahtarları kaydedildi!")
                    st.rerun()
        
        with api_tab_real:
            st.warning("⚠️ GERÇEK hesap API anahtarlarınızı buraya girin (flag=0)")
            st.caption("Gerçek hesap ile işlem yaparken çok dikkatli olun!")
            
            col_real1, col_real2, col_real3 = st.columns(3)
            with col_real1:
                real_key_input = st.text_input("Gerçek API Key", value=real_api_key, type="password", key="real_api_key")
            with col_real2:
                real_secret_input = st.text_input("Gerçek API Secret", value=real_api_secret, type="password", key="real_api_secret")
            with col_real3:
                real_pass_input = st.text_input("Gerçek Passphrase", value=real_passphrase, type="password", key="real_passphrase")
            
            if st.button("💾 Gerçek API Kaydet", key="save_real_api", type="primary"):
                if not real_key_input or not real_secret_input or not real_pass_input:
                    st.error("Lütfen tüm alanları doldurun.")
                else:
                    if not creds:
                        creds = APICredentials(is_demo=False)
                        db.add(creds)
                    
                    creds.set_credentials(real_key_input, real_secret_input, real_pass_input, is_demo=False)
                    db.commit()
                    st.success("✅ Gerçek API anahtarları kaydedildi!")
                    st.rerun()
        
        st.divider()
        
        st.markdown("##### 🔑 Durum")
        
        client = get_cached_client()
        if client.is_configured():
            st.success(f"✅ OKX API bağlantısı aktif ({'Demo' if getattr(creds, 'is_demo', True) else 'Gerçek'})")
            
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔄 Position Mode'u Kontrol Et ve Aktifleştir"):
                    success = client.set_position_mode("long_short_mode")
                    if success:
                        st.success("✅ Long/Short position mode aktif")
                    else:
                        st.error("❌ Position mode aktif edilemedi")
            
            with col2:
                if creds:
                    if st.button("🗑️ API Anahtarlarını Sil"):
                        db.delete(creds)
                        db.commit()
                        st.success("API anahtarları silindi. Sayfa yenileniyor...")
                        st.rerun()
        else:
            st.error("❌ API bağlantısı kurulamadı")
            
        st.divider()
        
        st.markdown("##### 🤖 Scheduler")
        
        st.info("⚙️ **Auto-Reopen Ayarları**")
    finally:
        db.close()
    
    auto_reopen_delay = st.number_input(
        "Pozisyon kapandıktan kaç dakika sonra yeniden açılsın?",
        min_value=1,
        max_value=60,
        value=st.session_state.auto_reopen_delay_minutes,
        step=1,
        help="Pozisyon kapandıktan sonra bu süre kadar beklenip otomatik olarak yeniden açılır",
        key="auto_reopen_delay_input"
    )
    
    if auto_reopen_delay != st.session_state.auto_reopen_delay_minutes:
        old_delay = st.session_state.auto_reopen_delay_minutes
        st.session_state.auto_reopen_delay_minutes = auto_reopen_delay
        
        # Save to database
        db = SessionLocal()
        try:
            setting = db.query(Settings).filter(Settings.key == "auto_reopen_delay_minutes").first()
            if setting:
                setting.value = str(auto_reopen_delay)
                # updated_at otomatik olarak TimestampMixin tarafından güncellenir
            else:
                setting = Settings(key="auto_reopen_delay_minutes", value=str(auto_reopen_delay))
                db.add(setting)
            db.commit()
        finally:
            db.close()
        
        # Otomatik restart: Bot çalışıyorsa restart et
        monitor = get_monitor()
        if monitor and monitor.is_running():
            st.info(f"⚙️ Ayar değişti: {old_delay} dk → {auto_reopen_delay} dk. Bot yeniden başlatılıyor...")
            stop_monitor()
            time.sleep(1)
            if start_monitor(auto_reopen_delay):
                st.success(f"✅ Bot yeni ayarla yeniden başlatıldı! (Auto-reopen: {auto_reopen_delay} dakika)")
            else:
                st.error("❌ Bot yeniden başlatılamadı. Lütfen manuel olarak başlatın.")
        else:
            st.success(f"✅ Auto-reopen süresi **{auto_reopen_delay} dakika** olarak güncellendi!")
            st.info("💡 Bot başlatıldığında bu ayar kullanılacak.")
    else:
        st.caption(f"📌 Mevcut ayar: **{st.session_state.auto_reopen_delay_minutes} dakika**")
    
    st.divider()
    
    monitor = get_monitor()
    is_running = monitor.is_running() if monitor else False
    
    if is_running:
        st.success(f"✅ Çalışıyor (Auto-reopen: {st.session_state.auto_reopen_delay_minutes} dk)")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("⏸️ Botu Durdur", type="secondary", width="stretch"):
                if stop_monitor():
                    st.success("✅ Background scheduler durduruldu!")
                    st.rerun()
                else:
                    st.error("❌ Durdurulamadı")
        
        with col2:
            st.caption("Scheduler çalışıyor")
    
    else:
        st.error("⚠️ Durmuş - Otomatik izleme kapalı")
        
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("▶️ Botu Başlat", type="primary", width="stretch"):
                reopen_delay = st.session_state.get('auto_reopen_delay_minutes', 5)
                if start_monitor(reopen_delay):
                    st.success(f"✅ Background scheduler başlatıldı! (Auto-reopen: {reopen_delay} dakika)")
                    st.rerun()
                else:
                    st.error("❌ Başlatılamadı")
        
        with col2:
            st.caption("Scheduler durmuş")
    
    st.divider()
    
    st.markdown("##### 🛡️ Recovery")
    
    st.caption("Pozisyon zarar seviyelerine göre basamaklı kurtarma (max 5 basamak)")
    
    # Load current recovery settings from database
    db_recovery = SessionLocal()
    try:
        enabled_setting = db_recovery.query(Settings).filter(Settings.key == "recovery_enabled").first()
        tp_setting = db_recovery.query(Settings).filter(Settings.key == "recovery_tp_usdt").first()
        sl_setting = db_recovery.query(Settings).filter(Settings.key == "recovery_sl_usdt").first()
        
        current_enabled = enabled_setting.value.lower() == 'true' if enabled_setting else True
        current_tp = float(tp_setting.value) if tp_setting else 50.0
        current_sl = float(sl_setting.value) if sl_setting else 100.0
        
        # Load multi-step settings with per-step TP/SL
        steps_data = []
        for i in range(1, 6):
            trigger = db_recovery.query(Settings).filter(Settings.key == f"recovery_step_{i}_trigger").first()
            add_amt = db_recovery.query(Settings).filter(Settings.key == f"recovery_step_{i}_add").first()
            tp_step = db_recovery.query(Settings).filter(Settings.key == f"recovery_step_{i}_tp").first()
            sl_step = db_recovery.query(Settings).filter(Settings.key == f"recovery_step_{i}_sl").first()
            if trigger and add_amt:
                steps_data.append({
                    'trigger': float(trigger.value),
                    'add': float(add_amt.value),
                    'tp': float(tp_step.value) if tp_step else 50.0,
                    'sl': float(sl_step.value) if sl_step else 100.0
                })
        
        # If no steps, use default values
        if not steps_data:
            steps_data = [
                {'trigger': -50.0, 'add': 3000.0, 'tp': 30.0, 'sl': 1200.0}
            ]
    finally:
        db_recovery.close()
    
    recovery_enabled = st.toggle("🔄 Kurtarma Özelliği Aktif", value=current_enabled, 
                                  help="Bot başladığında otomatik açılır, sadece manuel kapatılabilir")
    
    st.markdown("##### 📊 Basamak Ayarları")
    
    num_steps = st.number_input("Basamak Sayısı", min_value=1, max_value=5, value=len(steps_data), step=1)
    
    step_triggers = []
    step_adds = []
    step_tps = []
    step_sls = []
    
    for i in range(int(num_steps)):
        st.markdown(f"**Basamak {i+1}**")
        col1, col2, col3, col4 = st.columns(4)
        default_trigger = steps_data[i]['trigger'] if i < len(steps_data) else -50.0 * (i + 1)
        default_add = steps_data[i]['add'] if i < len(steps_data) else 100.0 * (i + 1)
        default_tp = steps_data[i]['tp'] if i < len(steps_data) else current_tp
        default_sl = steps_data[i]['sl'] if i < len(steps_data) else current_sl
        
        with col1:
            trigger = st.number_input(
                f"Tetikleme PNL",
                min_value=-10000.0,
                max_value=0.0,
                value=default_trigger,
                step=10.0,
                key=f"step_{i}_trigger",
                help=f"Basamak {i+1} için tetikleme değeri"
            )
            step_triggers.append(trigger)
        
        with col2:
            add = st.number_input(
                f"Ekleme (USDT)",
                min_value=10.0,
                max_value=50000.0,
                value=default_add,
                step=50.0,
                key=f"step_{i}_add",
                help=f"Basamak {i+1} tetiklendiğinde eklenecek miktar"
            )
            step_adds.append(add)
        
        with col3:
            tp = st.number_input(
                f"🎯 TP (USDT)",
                min_value=1.0,
                max_value=10000.0,
                value=default_tp,
                step=10.0,
                key=f"step_{i}_tp",
                help=f"Basamak {i+1} sonrası yeni kar hedefi"
            )
            step_tps.append(tp)
        
        with col4:
            sl = st.number_input(
                f"🛑 SL (USDT)",
                min_value=1.0,
                max_value=10000.0,
                value=default_sl,
                step=10.0,
                key=f"step_{i}_sl",
                help=f"Basamak {i+1} sonrası yeni zarar limiti"
            )
            step_sls.append(sl)
    
    if st.button("💾 Kurtarma Ayarlarını Kaydet", type="primary"):
        db_save = SessionLocal()
        try:
            settings_to_save = [
                ("recovery_enabled", str(recovery_enabled).lower())
            ]
            
            # Save step settings with per-step TP/SL
            for i in range(int(num_steps)):
                settings_to_save.append((f"recovery_step_{i+1}_trigger", str(step_triggers[i])))
                settings_to_save.append((f"recovery_step_{i+1}_add", str(step_adds[i])))
                settings_to_save.append((f"recovery_step_{i+1}_tp", str(step_tps[i])))
                settings_to_save.append((f"recovery_step_{i+1}_sl", str(step_sls[i])))
            
            # Clear unused steps
            for i in range(int(num_steps) + 1, 6):
                for suffix in ['trigger', 'add', 'tp', 'sl']:
                    existing = db_save.query(Settings).filter(Settings.key == f"recovery_step_{i}_{suffix}").first()
                    if existing:
                        db_save.delete(existing)
            
            for key, value in settings_to_save:
                existing = db_save.query(Settings).filter(Settings.key == key).first()
                if existing:
                    existing.value = value
                else:
                    new_setting = Settings(key=key, value=value)
                    db_save.add(new_setting)
            
            db_save.commit()
            st.success("✅ Basamaklı kurtarma ayarları kaydedildi!")
            
            if recovery_enabled:
                step_info = "\n".join([f"  - Basamak {i+1}: PNL ≤ {step_triggers[i]} → +{step_adds[i]} USDT | TP:{step_tps[i]} SL:{step_sls[i]}" for i in range(int(num_steps))])
                st.info(f"""
**Aktif Kurtarma Ayarları:**
{step_info}
                """)
        except Exception as e:
            db_save.rollback()
            st.error(f"❌ Hata: {str(e)}")
        finally:
            db_save.close()
    
    st.divider()
    
    with st.expander("🌐 OKX Info"):
        st.caption("Demo: https://www.okx.com/trade-demo")
        st.caption("API: https://www.okx.com/api/v5")
    
    st.divider()
    
    st.markdown("##### 📊 Database")
    
    db = SessionLocal()
    try:
        total_positions = db.query(Position).count()
        active_positions = db.query(Position).filter(Position.is_open == True).count()
        closed_positions = db.query(Position).filter(Position.is_open == False).count()
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("Toplam Kayıt", total_positions)
        
        with col2:
            st.metric("Aktif", active_positions)
        
        with col3:
            st.metric("Kapanmış", closed_positions)
    finally:
        db.close()
