#!/bin/bash

echo "🚀 OKX Trading Bot - Linux/macOS Başlatma Scripti"
echo "================================================"

# .env dosyasını kontrol et
if [ ! -f .env ]; then
    echo "❌ .env dosyası bulunamadı!"
    echo "Önce setup_local.py scriptini çalıştırın: python3 setup_local.py"
    exit 1
fi

# Virtual environment var mı kontrol et
if [ ! -d "venv" ]; then
    echo "📦 Virtual environment oluşturuluyor..."
    python3 -m venv venv
    if [ $? -ne 0 ]; then
        echo "❌ Virtual environment oluşturulamadı!"
        exit 1
    fi
fi

# Virtual environment'ı aktif et
echo "🔧 Virtual environment aktifleştiriliyor..."
source venv/bin/activate

# Paketleri yükle
echo "📦 Gerekli paketler yükleniyor..."
pip install -r requirements.txt
if [ $? -ne 0 ]; then
    echo "❌ Paket yükleme hatası!"
    exit 1
fi

# .env dosyasını yükle
echo "🔧 Environment variables yükleniyor..."
export $(cat .env | xargs)

# Streamlit'i başlat
echo "🌐 Streamlit başlatılıyor..."
echo "Tarayıcınızda http://localhost:8501 adresini açın"
streamlit run app.py --server.port 8501