#!/usr/bin/env python3
"""
Database migration script to add missing timestamp columns
"""
import os
from sqlalchemy import create_engine, text
from datetime import datetime, timezone

# Database URL'i al
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "postgresql://postgres:password@localhost:5432/trading_bot"
    print("⚠️  DATABASE_URL environment variable bulunamadı, default kullanılıyor:", DATABASE_URL)

def fix_database():
    """Add missing timestamp columns to existing tables"""
    engine = create_engine(DATABASE_URL)
    
    try:
        with engine.connect() as conn:
            print("🔧 Database güncelleniyor...")
            
            # Settings tablosuna timestamp sütunları ekle
            try:
                conn.execute(text("""
                    ALTER TABLE settings 
                    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                """))
                print("✅ Settings tablosu güncellendi")
            except Exception as e:
                print(f"⚠️  Settings tablosu zaten güncel: {e}")
            
            # API credentials tablosuna timestamp ve demo/real sütunları ekle
            try:
                conn.execute(text("""
                    ALTER TABLE api_credentials
                    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    ADD COLUMN IF NOT EXISTS demo_api_key_encrypted TEXT,
                    ADD COLUMN IF NOT EXISTS demo_api_secret_encrypted TEXT,
                    ADD COLUMN IF NOT EXISTS demo_passphrase_encrypted TEXT,
                    ADD COLUMN IF NOT EXISTS real_api_key_encrypted TEXT,
                    ADD COLUMN IF NOT EXISTS real_api_secret_encrypted TEXT,
                    ADD COLUMN IF NOT EXISTS real_passphrase_encrypted TEXT
                """))
                print("✅ API credentials tablosu güncellendi")
            except Exception as e:
                print(f"⚠️  API credentials tablosu zaten güncel: {e}")
            
            # Positions tablosuna timestamp sütunları ekle (eğer yoksa)
            try:
                conn.execute(text("""
                    ALTER TABLE positions
                    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                    ADD COLUMN IF NOT EXISTS original_tp_usdt FLOAT,
                    ADD COLUMN IF NOT EXISTS original_sl_usdt FLOAT
                """))
                print("✅ Positions tablosu güncellendi")
            except Exception as e:
                print(f"⚠️  Positions tablosu zaten güncel: {e}")
            
            # Değişiklikleri kaydet
            conn.commit()
            print("🎉 Database başarıyla güncellendi!")
            
    except Exception as e:
        print(f"❌ Database güncelleme hatası: {e}")
        print("💡 Yeni tablolar oluşturuluyor...")
        
        # Eğer tablolar yoksa, yeni oluştur
        from database import init_db
        init_db()
        print("✅ Yeni tablolar oluşturuldu!")

if __name__ == "__main__":
    fix_database()