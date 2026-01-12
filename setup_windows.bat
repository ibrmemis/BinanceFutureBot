@echo off
chcp 65001 >nul
echo 🚀 OKX Trading Bot - Windows Kurulum Scripti
echo ================================================

REM Python version kontrolü
echo 📋 Python version kontrol ediliyor...
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python bulunamadı!
    echo Python 3.11+ indirin: https://www.python.org/downloads/
    pause
    exit /b 1
)

python -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)" >nul 2>&1
if errorlevel 1 (
    echo ❌ Python 3.11+ gerekli!
    python --version
    pause
    exit /b 1
)

echo ✅ Python version OK
python --version

REM PostgreSQL kontrolü
echo.
echo 📋 PostgreSQL kontrol ediliyor...
psql --version >nul 2>&1
if errorlevel 1 (
    echo ❌ PostgreSQL bulunamadı!
    echo PostgreSQL indirin: https://www.postgresql.org/download/windows/
    echo Kurulum sonrası PATH'e eklemeyi unutmayın!
    pause
    exit /b 1
)

echo ✅ PostgreSQL bulundu
psql --version

REM Virtual environment oluştur
echo.
echo 📦 Virtual environment oluşturuluyor...
if exist venv (
    echo Virtual environment zaten mevcut
) else (
    python -m venv venv
    if errorlevel 1 (
        echo ❌ Virtual environment oluşturulamadı!
        pause
        exit /b 1
    )
    echo ✅ Virtual environment oluşturuldu
)

REM Virtual environment aktif et
echo.
echo 🔧 Virtual environment aktifleştiriliyor...
call venv\Scripts\activate.bat
if errorlevel 1 (
    echo ❌ Virtual environment aktifleştirilemedi!
    pause
    exit /b 1
)

REM pip güncelle
echo.
echo 📦 pip güncelleniyor...
python -m pip install --upgrade pip

REM Requirements yükle
echo.
echo 📦 Python paketleri yükleniyor...
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ Paket yükleme hatası!
    pause
    exit /b 1
)

echo ✅ Python paketleri yüklendi

REM .env dosyası kontrolü
echo.
echo 📄 .env dosyası kontrol ediliyor...
if not exist .env (
    if exist .env.example (
        echo .env.example'dan .env oluşturuluyor...
        copy .env.example .env >nul
        echo ⚠️  .env dosyası oluşturuldu, lütfen düzenleyin!
        echo.
        echo Düzenlemeniz gereken alanlar:
        echo - DATABASE_URL: PostgreSQL bağlantı bilgileri
        echo - OKX_DEMO_API_KEY: OKX Demo API Key
        echo - OKX_DEMO_API_SECRET: OKX Demo API Secret  
        echo - OKX_DEMO_PASSPHRASE: OKX Demo Passphrase
        echo - SESSION_SECRET: 32 karakter rastgele string
        echo.
        echo SESSION_SECRET oluşturmak için:
        python -c "import secrets; print('SESSION_SECRET=' + secrets.token_urlsafe(32))"
        echo.
        echo .env dosyasını düzenledikten sonra tekrar çalıştırın.
        pause
        exit /b 0
    ) else (
        echo ❌ .env.example dosyası bulunamadı!
        pause
        exit /b 1
    )
) else (
    echo ✅ .env dosyası mevcut
)

REM Database bağlantı testi
echo.
echo 🔗 Database bağlantısı test ediliyor...
python check_system.py >nul 2>&1
if errorlevel 1 (
    echo ⚠️  Sistem kontrolünde sorunlar tespit edildi
    echo Detaylı kontrol için: python check_system.py
    echo.
    echo Yaygın sorunlar:
    echo - PostgreSQL çalışmıyor
    echo - trading_bot database'i yok
    echo - .env dosyasındaki bilgiler yanlış
    echo - OKX API keys eksik
    echo.
    pause
    exit /b 1
)

echo ✅ Sistem kontrolleri başarılı

REM Kurulum tamamlandı
echo.
echo 🎉 Kurulum tamamlandı!
echo.
echo 📋 Sonraki adımlar:
echo 1. .env dosyasındaki OKX API keys'lerini doldurun
echo 2. run_local.bat ile uygulamayı başlatın
echo 3. Tarayıcıda http://localhost:8501 adresini açın
echo.
echo 🔧 Faydalı komutlar:
echo - Sistem kontrolü: python check_system.py
echo - Uygulama başlat: run_local.bat
echo - Manuel başlat: streamlit run app.py
echo.
pause