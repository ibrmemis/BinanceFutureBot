@echo off
echo 🚀 OKX Trading Bot - Windows Başlatma Scripti
echo ================================================

REM .env dosyasını kontrol et
if not exist .env (
    echo ❌ .env dosyası bulunamadı!
    echo Önce setup_local.py scriptini çalıştırın: python setup_local.py
    pause
    exit /b 1
)

REM Virtual environment var mı kontrol et
if not exist venv (
    echo 📦 Virtual environment oluşturuluyor...
    python -m venv venv
    if errorlevel 1 (
        echo ❌ Virtual environment oluşturulamadı!
        pause
        exit /b 1
    )
)

REM Virtual environment'ı aktif et
echo 🔧 Virtual environment aktifleştiriliyor...
call venv\Scripts\activate.bat

REM Paketleri yükle
echo 📦 Gerekli paketler yükleniyor...
pip install -r requirements.txt
if errorlevel 1 (
    echo ❌ Paket yükleme hatası!
    pause
    exit /b 1
)

REM .env dosyasını yükle (Windows için)
for /f "delims=" %%x in (.env) do (set "%%x")

REM Streamlit'i başlat
echo 🌐 Streamlit başlatılıyor...
echo Tarayıcınızda http://localhost:8501 adresini açın
streamlit run app.py --server.port 8501

pause