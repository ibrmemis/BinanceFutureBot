#!/usr/bin/env python3
"""
Local kurulum için setup scripti
PostgreSQL database'i kontrol eder ve gerekli tabloları oluşturur
"""

import os
import sys
import subprocess
from pathlib import Path

def check_python_version():
    """Python 3.11+ kontrolü"""
    if sys.version_info < (3, 11):
        print("❌ Python 3.11 veya üzeri gerekli!")
        print(f"Mevcut versiyon: {sys.version}")
        return False
    print(f"✅ Python {sys.version_info.major}.{sys.version_info.minor} - OK")
    return True

def check_postgresql():
    """PostgreSQL kurulu mu kontrol et"""
    try:
        result = subprocess.run(['psql', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ PostgreSQL kurulu: {result.stdout.strip()}")
            return True
        else:
            print("❌ PostgreSQL bulunamadı!")
            return False
    except FileNotFoundError:
        print("❌ PostgreSQL kurulu değil!")
        print("Windows için: https://www.postgresql.org/download/windows/")
        print("macOS için: brew install postgresql")
        print("Ubuntu için: sudo apt install postgresql postgresql-contrib")
        return False

def create_env_file():
    """Eğer .env yoksa .env.example'dan oluştur"""
    env_file = Path('.env')
    env_example = Path('.env.example')
    
    if not env_file.exists() and env_example.exists():
        print("📝 .env dosyası oluşturuluyor...")
        env_content = env_example.read_text()
        
        # Kullanıcıdan database bilgilerini al
        print("\n🔧 PostgreSQL Database Ayarları:")
        db_host = input("Database Host (localhost): ").strip() or "localhost"
        db_port = input("Database Port (5432): ").strip() or "5432"
        db_name = input("Database Name (trading_bot): ").strip() or "trading_bot"
        db_user = input("Database Username: ").strip()
        db_password = input("Database Password: ").strip()
        
        if not db_user or not db_password:
            print("❌ Username ve password gerekli!")
            return False
        
        # SESSION_SECRET oluştur
        import secrets
        session_secret = secrets.token_urlsafe(32)
        
        # .env içeriğini güncelle
        env_content = env_content.replace("postgresql://username:password@localhost:5432/trading_bot", 
                                        f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}")
        env_content = env_content.replace("your_32_character_random_secret_key", session_secret)
        env_content = env_content.replace("your_username", db_user)
        env_content = env_content.replace("your_password", db_password)
        
        env_file.write_text(env_content)
        print("✅ .env dosyası oluşturuldu!")
        print("⚠️  OKX API keys'lerini .env dosyasına manuel olarak ekleyin!")
        return True
    elif env_file.exists():
        print("✅ .env dosyası mevcut")
        return True
    else:
        print("❌ .env.example bulunamadı!")
        return False

def install_requirements():
    """Python paketlerini yükle"""
    requirements_file = Path('requirements.txt')
    if not requirements_file.exists():
        print("❌ requirements.txt bulunamadı!")
        return False
    
    print("📦 Python paketleri yükleniyor...")
    try:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', 'requirements.txt'], 
                      check=True)
        print("✅ Python paketleri yüklendi!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Paket yükleme hatası: {e}")
        return False

def test_database_connection():
    """Database bağlantısını test et"""
    try:
        # .env dosyasını yükle
        from dotenv import load_dotenv
        load_dotenv()
        
        from database import init_db, SessionLocal
        
        print("🔗 Database bağlantısı test ediliyor...")
        
        # Database'i initialize et
        init_db()
        
        # Test bağlantısı
        db = SessionLocal()
        db.execute("SELECT 1")
        db.close()
        
        print("✅ Database bağlantısı başarılı!")
        return True
        
    except ImportError as e:
        print(f"❌ Modül import hatası: {e}")
        print("Önce 'pip install python-dotenv' çalıştırın")
        return False
    except Exception as e:
        print(f"❌ Database bağlantı hatası: {e}")
        print("PostgreSQL çalışıyor mu? Database mevcut mu? Kullanıcı izinleri doğru mu?")
        return False

def main():
    """Ana kurulum fonksiyonu"""
    print("🚀 OKX Trading Bot - Local Kurulum")
    print("=" * 50)
    
    # 1. Python version kontrolü
    if not check_python_version():
        return False
    
    # 2. PostgreSQL kontrolü
    if not check_postgresql():
        return False
    
    # 3. .env dosyası oluştur
    if not create_env_file():
        return False
    
    # 4. Python paketlerini yükle
    if not install_requirements():
        return False
    
    # 5. Database bağlantısını test et
    if not test_database_connection():
        return False
    
    print("\n🎉 Kurulum tamamlandı!")
    print("\n📋 Sonraki adımlar:")
    print("1. .env dosyasındaki OKX API keys'lerini doldurun")
    print("2. streamlit run app.py komutu ile uygulamayı başlatın")
    print("3. Tarayıcıda http://localhost:8501 adresini açın")
    
    return True

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)