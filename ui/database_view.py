import streamlit as st
import pandas as pd
from sqlalchemy import text
from database import SessionLocal, Position, APICredentials, Settings

def show_database_page():
    st.markdown("#### 💾 Database")
    
    db = SessionLocal()
    try:
        # Tables to display
        tables = {
            "Positions (Pozisyonlar)": Position,
            "API Credentials (API Bilgileri)": APICredentials,
            "Settings (Ayarlar)": Settings
        }
        
        selected_table_name = st.selectbox("Görüntülemek istediğiniz tabloyu seçin:", list(tables.keys()))
        model_class = tables[selected_table_name]
        
        # Query all records from the selected table
        records = db.query(model_class).all()
        
        if not records:
            st.info(f"{selected_table_name} tablosunda henüz veri bulunmuyor.")
        else:
            # Convert to list of dictionaries for DataFrame
            data = []
            for record in records:
                row = {}
                for column in record.__table__.columns:
                    val = getattr(record, column.name)
                    # Mask sensitive fields if it's the credentials table
                    if model_class == APICredentials and column.name in ['api_key_encrypted', 'api_secret_encrypted', 'passphrase_encrypted']:
                        row[column.name] = "******** (Şifreli)"
                    else:
                        row[column.name] = val
                data.append(row)
            
            df = pd.DataFrame(data)
            st.dataframe(df, width="stretch")
            
            st.write(f"Toplam Kayıt: **{len(records)}**")
            
            # Refresh button
            if st.button("🔄 Verileri Yenile"):
                st.rerun()
                
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
