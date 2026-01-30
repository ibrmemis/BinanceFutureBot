import streamlit as st
import pandas as pd
from sqlalchemy import text
from database import SessionLocal, Position, APICredentials, Settings

def show_database_page():
    st.markdown("#### 💾 Database Editor")
    
    db = SessionLocal()
    try:
        # Tables to display
        tables = {
            "Positions (Pozisyonlar)": Position,
            "Settings (Ayarlar)": Settings,
            "API Credentials (API Bilgileri)": APICredentials
        }
        
        selected_table_name = st.selectbox("Düzenlemek istediğiniz tabloyu seçin:", list(tables.keys()))
        model_class = tables[selected_table_name]
        
        # Query all records
        records = db.query(model_class).all()
        
        if not records:
            st.info(f"{selected_table_name} tablosunda henüz veri bulunmuyor.")
        else:
            # Prepare data for editor
            data = []
            for record in records:
                row = {}
                for column in record.__table__.columns:
                    val = getattr(record, column.name)
                    # Handle encrypted fields for display
                    if model_class == APICredentials and column.name in ['api_key_encrypted', 'api_secret_encrypted', 'passphrase_encrypted', 
                                                                       'demo_api_key_encrypted', 'demo_api_secret_encrypted', 'demo_passphrase_encrypted',
                                                                       'real_api_key_encrypted', 'real_api_secret_encrypted', 'real_passphrase_encrypted']:
                        row[column.name] = "********"
                    else:
                        row[column.name] = val
                data.append(row)
            
            df = pd.DataFrame(data)
            
            # Define columns customization
            column_config = {
                "id": st.column_config.NumberColumn(disabled=True),
                "created_at": st.column_config.DatetimeColumn(disabled=True, format="D MMM YYYY, h:mm a"),
                "updated_at": st.column_config.DatetimeColumn(disabled=True, format="D MMM YYYY, h:mm a"),
            }

            # Disable editing for encrypted fields
            if model_class == APICredentials:
                for col in ['api_key_encrypted', 'api_secret_encrypted', 'passphrase_encrypted', 
                           'demo_api_key_encrypted', 'demo_api_secret_encrypted', 'demo_passphrase_encrypted',
                           'real_api_key_encrypted', 'real_api_secret_encrypted', 'real_passphrase_encrypted']:
                    column_config[col] = st.column_config.TextColumn(disabled=True)

            st.info("📝 Tablo üzerinde değişiklik yapıp 'Save Changes' butonuna basabilirsiniz. (ID ve Tarih alanları değiştirilemez)")
            
            # Editor
            edited_df = st.data_editor(
                df,
                disabled=["id", "created_at", "updated_at"],
                column_config=column_config,
                num_rows="dynamic",
                key=f"editor_{selected_table_name}",
                use_container_width=True
            )
            
            if st.button("💾 Değişiklikleri Kaydet", type="primary"):
                try:
                    # Detect changes
                    # Simple approach: Iterate through edited_df and update records
                    # For a robust solution, we should diff, but re-writing for small tables is okay for now.
                    # However, we must be careful not to overwrite encrypted fields with asterisks if they weren't changed.
                    # Since we disabled editing them, they should come back as asterisks in edited_df? 
                    # Actually, data_editor returns the current state.
                    
                    rows_updated = 0
                    for index, row in edited_df.iterrows():
                        record_id = row.get("id")
                        if record_id:
                            # Update existing
                            obj = db.query(model_class).filter(model_class.id == record_id).first()
                            if obj:
                                changed = False
                                for col in df.columns:
                                    # Skip protected/encrypted columns from update logic to prevent overwriting with masks
                                    if col in ["id", "created_at", "updated_at"]:
                                        continue
                                    if model_class == APICredentials and "encrypted" in col:
                                        continue
                                        
                                    new_val = row[col]
                                    old_val = getattr(obj, col)
                                    
                                    # Handle different types comparison if needed
                                    # Pandas might convert None to NaN, handle that
                                    if pd.isna(new_val) and old_val is None:
                                        continue
                                        
                                    if new_val != old_val:
                                        setattr(obj, col, new_val)
                                        changed = True
                                
                                if changed:
                                    rows_updated += 1
                        else:
                            # Insert new record (handle carefully)
                            # For now, maybe just skip new rows or handle them if needed. 
                            # The user mainly needs update.
                            pass
                            
                    db.commit()
                    if rows_updated > 0:
                        st.success(f"✅ {rows_updated} kayıt güncellendi!")
                        st.balloons()
                    else:
                        st.info("ℹ️ Değişiklik algılanmadı.")
                        
                except Exception as e:
                    db.rollback()
                    st.error(f"❌ Kaydetme hatası: {e}")
                    
    except Exception as e:
        st.error(f"Veritabanı okuma hatası: {e}")
    finally:
        db.close()

    st.divider()
    st.markdown("##### 🛠️ SQL")
    st.warning("⚠️ **DİKKAT:** Bu bölüm doğrudan veritabanı sorguları çalıştırmanızı sağlar. Sadece ne yaptığınızdan eminseniz kullanın.")
    
    with st.expander("📝 SQL Komutu Çalıştır"):
        sql_input = st.text_area("SQL Sorgusu", placeholder="ALTER TABLE api_credentials ADD COLUMN ...", height=100)
        col1, col2 = st.columns([1, 4])
        with col1:
            run_sql = st.button("🚀 Çalıştır", type="primary")
        
        if run_sql and sql_input:
            db = SessionLocal()
            try:
                # DML/DDL işlemleri için execute kullanıyoruz
                result = db.execute(text(sql_input))
                
                # Eğer bir SELECT sorgusuysa sonuçları göster
                if sql_input.strip().upper().startswith("SELECT"):
                    df = pd.DataFrame(result.fetchall(), columns=result.keys())
                    if not df.empty:
                        st.dataframe(df)
                        st.success(f"✅ Sorgu başarılı! {len(df)} kayıt bulundu.")
                    else:
                        st.info("ℹ️ Sorgu başarılı ancak sonuç dönmedi.")
                else:
                    db.commit()
                    st.success("✅ SQL komutu başarıyla çalıştırıldı!")
                    if result.rowcount > 0:
                        st.info(f"ℹ️ Etkilenen satır sayısı: {result.rowcount}")
            except Exception as e:
                db.rollback()
                st.error(f"❌ SQL Hatası: {str(e)}")
            finally:
                db.close()
