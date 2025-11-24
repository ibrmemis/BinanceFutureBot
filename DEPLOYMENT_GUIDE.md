# 🚀 OKX Trading Bot - Kendi Sunucunuzda Kurulum Rehberi

## 📋 Gereksinimler

### Minimum Sunucu Özellikleri
- **İşletim Sistemi**: Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- **RAM**: 2 GB minimum (4 GB önerilen)
- **CPU**: 1 vCPU minimum (2 vCPU önerilen)
- **Disk**: 10 GB boş alan
- **Network**: İnternet bağlantısı (OKX API erişimi için)

### Yazılım Gereksinimleri
- Python 3.11+
- PostgreSQL 14+
- Nginx (reverse proxy için)
- systemd (Ubuntu/Debian'da varsayılan)

---

## 1️⃣ Sunucu Hazırlığı

### Ubuntu/Debian Sistemler

```bash
# Sistem güncellemeleri
sudo apt update && sudo apt upgrade -y

# Gerekli paketleri yükle
sudo apt install -y python3 python3-pip python3-venv \
                    postgresql postgresql-contrib \
                    nginx git curl

# Firewall kurulumu (UFW)
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS (SSL için)
sudo ufw enable
```

### CentOS/RHEL Sistemler

```bash
# Sistem güncellemeleri
sudo yum update -y

# Gerekli paketleri yükle
sudo yum install -y python3 python3-pip python3-virtualenv \
                    postgresql postgresql-server postgresql-contrib \
                    nginx git curl

# PostgreSQL başlat
sudo postgresql-setup --initdb
sudo systemctl start postgresql
sudo systemctl enable postgresql

# Firewall kurulumu (firewalld)
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

---

## 2️⃣ PostgreSQL Kurulumu ve Yapılandırma

### Database Oluştur

```bash
# PostgreSQL kullanıcısına geç
sudo -u postgres psql

# SQL komutları (PostgreSQL shell içinde)
CREATE DATABASE okx_trading_bot;
CREATE USER bot_user WITH ENCRYPTED PASSWORD 'GüçlüŞifre123!';
GRANT ALL PRIVILEGES ON DATABASE okx_trading_bot TO bot_user;
\q
```

### PostgreSQL Uzaktan Erişim (Opsiyonel)

Eğer database farklı sunucudaysa:

```bash
# /etc/postgresql/14/main/postgresql.conf düzenle
sudo nano /etc/postgresql/14/main/postgresql.conf

# Şu satırı bul ve değiştir:
# listen_addresses = 'localhost'  →  listen_addresses = '*'

# /etc/postgresql/14/main/pg_hba.conf düzenle
sudo nano /etc/postgresql/14/main/pg_hba.conf

# Şu satırı ekle (IP aralığını kendi networküne göre ayarla):
host    all             all             0.0.0.0/0               md5

# PostgreSQL'i yeniden başlat
sudo systemctl restart postgresql
```

---

## 3️⃣ Uygulama Kurulumu

### Kullanıcı Oluştur (Güvenlik için)

```bash
# Bot için özel kullanıcı oluştur
sudo adduser botuser --disabled-password --gecos ""
sudo su - botuser
```

### Proje Dosyalarını Kopyala

**Seçenek 1: Git ile (önerilen)**

```bash
# Git repository'den klonla
cd ~
git clone https://github.com/YOUR_USERNAME/okx-trading-bot.git
cd okx-trading-bot
```

**Seçenek 2: Manuel Kopyalama**

```bash
# Yerel bilgisayardan sunucuya dosya aktar (kendi bilgisayarında çalıştır)
scp -r /path/to/local/project botuser@YOUR_SERVER_IP:/home/botuser/okx-trading-bot

# Sunucuda
cd /home/botuser/okx-trading-bot
```

### Python Virtual Environment Oluştur

```bash
# Virtual environment oluştur
python3 -m venv venv

# Aktif et
source venv/bin/activate

# pip güncelle
pip install --upgrade pip
```

### Bağımlılıkları Yükle

```bash
# Tüm gerekli Python paketlerini yükle
pip install streamlit==1.51.0
pip install apscheduler==3.11.0
pip install pandas==2.3.3
pip install sqlalchemy==2.0.44
pip install psycopg2-binary==2.9.9
pip install cryptography==41.0.7
pip install python-okx
```

---

## 4️⃣ Environment Variables Ayarları

### .env Dosyası Oluştur

```bash
# .env dosyası oluştur
nano .env
```

### .env İçeriği

```bash
# PostgreSQL Database
DATABASE_URL=postgresql://bot_user:GüçlüŞifre123!@localhost:5432/okx_trading_bot

# OKX API Keys (Demo Trading)
OKX_DEMO_API_KEY=your_api_key_here
OKX_DEMO_API_SECRET=your_api_secret_here
OKX_DEMO_PASSPHRASE=your_passphrase_here

# Session Secret (şifreleme için, rastgele 32 karakter)
SESSION_SECRET=your_random_32_character_secret_key_here

# PostgreSQL Connection Details (ayrı olarak gerekli)
PGHOST=localhost
PGPORT=5432
PGDATABASE=okx_trading_bot
PGUSER=bot_user
PGPASSWORD=GüçlüŞifre123!
```

### Environment Variables'ları Yükle

```bash
# .env'i shell'e yükle
export $(cat .env | xargs)

# Veya .bashrc'ye ekle (kalıcı)
echo 'export $(cat /home/botuser/okx-trading-bot/.env | xargs)' >> ~/.bashrc
source ~/.bashrc
```

### SESSION_SECRET Oluşturma

```bash
# Rastgele 32 karakter oluştur
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

---

## 5️⃣ Database Schema Oluştur

### SQL Schema Çalıştır

```bash
# PostgreSQL'e bağlan
psql -h localhost -U bot_user -d okx_trading_bot

# SQL komutlarını çalıştır (PostgreSQL shell içinde)
```

```sql
-- API Credentials Tablosu
CREATE TABLE IF NOT EXISTS api_credentials (
    id SERIAL PRIMARY KEY,
    api_key_encrypted TEXT NOT NULL,
    api_secret_encrypted TEXT NOT NULL,
    passphrase_encrypted TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Positions Tablosu
CREATE TABLE IF NOT EXISTS positions (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL,
    side VARCHAR(10) NOT NULL,
    position_side VARCHAR(10),
    entry_price DECIMAL(20, 8) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    leverage INTEGER NOT NULL,
    tp_usdt DECIMAL(20, 8),
    sl_usdt DECIMAL(20, 8),
    tp_order_id VARCHAR(50),
    sl_order_id VARCHAR(50),
    position_id VARCHAR(50),
    is_open BOOLEAN DEFAULT TRUE,
    opened_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    closed_at TIMESTAMP,
    pnl DECIMAL(20, 8),
    close_reason VARCHAR(50),
    parent_position_id INTEGER
);

-- Settings Tablosu
CREATE TABLE IF NOT EXISTS settings (
    id SERIAL PRIMARY KEY,
    key VARCHAR(100) UNIQUE NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_positions_open ON positions(is_open);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_settings_key ON settings(key);

\q
```

---

## 6️⃣ Streamlit Konfigürasyonu

### .streamlit Dizini Oluştur

```bash
mkdir -p ~/.streamlit
```

### config.toml Oluştur

```bash
nano ~/.streamlit/config.toml
```

### config.toml İçeriği

```toml
[server]
port = 8501
address = "127.0.0.1"
headless = true
enableCORS = false
enableXsrfProtection = false

[browser]
serverAddress = "yourdomain.com"
serverPort = 80
gatherUsageStats = false

[theme]
base = "dark"
```

---

## 7️⃣ systemd Service Kurulumu

### Service Dosyası Oluştur

```bash
# Root kullanıcısına dön
exit  # botuser'dan çık

# Service dosyasını oluştur
sudo nano /etc/systemd/system/okx-trading-bot.service
```

### Service İçeriği

```ini
[Unit]
Description=OKX Trading Bot - Streamlit App
After=network.target postgresql.service
Wants=postgresql.service

[Service]
Type=simple
User=botuser
WorkingDirectory=/home/botuser/okx-trading-bot
Environment="PATH=/home/botuser/okx-trading-bot/venv/bin"
EnvironmentFile=/home/botuser/okx-trading-bot/.env
ExecStart=/home/botuser/okx-trading-bot/venv/bin/streamlit run app.py --server.port=8501 --server.address=127.0.0.1
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### Service'i Etkinleştir ve Başlat

```bash
# systemd'yi yeniden yükle
sudo systemctl daemon-reload

# Service'i etkinleştir (boot'ta otomatik başlar)
sudo systemctl enable okx-trading-bot.service

# Service'i başlat
sudo systemctl start okx-trading-bot.service

# Durumu kontrol et
sudo systemctl status okx-trading-bot.service

# Log'ları izle
sudo journalctl -u okx-trading-bot -f
```

---

## 8️⃣ Nginx Reverse Proxy Kurulumu

### Nginx Konfigürasyonu

```bash
# Nginx site konfigürasyonu oluştur
sudo nano /etc/nginx/sites-available/okx-trading-bot
```

### Nginx Konfigürasyon İçeriği

```nginx
# WebSocket upgrade map (Streamlit için kritik!)
map $http_upgrade $connection_upgrade {
    default upgrade;
    '' close;
}

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    
    # Maksimum upload boyutu
    client_max_body_size 100M;
    
    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        
        # WebSocket desteği (Streamlit için GEREKLİ!)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
        
        # Proxy headers
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        proxy_redirect off;
        proxy_buffering off;
        
        # Timeout ayarları (uzun işlemler için)
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        proxy_connect_timeout 86400s;
    }
}
```

### Nginx'i Etkinleştir

```bash
# Site'ı etkinleştir (symlink oluştur)
sudo ln -s /etc/nginx/sites-available/okx-trading-bot /etc/nginx/sites-enabled/

# Varsayılan site'ı kaldır (opsiyonel)
sudo rm /etc/nginx/sites-enabled/default

# Nginx konfigürasyonunu test et
sudo nginx -t

# Nginx'i yeniden başlat
sudo systemctl restart nginx
```

---

## 9️⃣ SSL/HTTPS Kurulumu (Let's Encrypt)

### Certbot Kur

```bash
# Ubuntu/Debian
sudo apt install certbot python3-certbot-nginx -y

# CentOS/RHEL
sudo yum install certbot python3-certbot-nginx -y
```

### SSL Sertifikası Al

```bash
# Otomatik nginx konfigürasyonu ile SSL kur
sudo certbot --nginx -d yourdomain.com -d www.yourdomain.com

# Sorulara cevaplar:
# - Email: your-email@example.com
# - Terms: Agree (A)
# - Redirect HTTP to HTTPS: Yes (2)
```

### Otomatik Yenileme Testi

```bash
# Yenileme testini çalıştır
sudo certbot renew --dry-run

# Cron job zaten oluşturulmuş olmalı (kontrol et)
sudo systemctl status certbot.timer
```

---

## 🔟 Uygulama Yönetimi

### Service Komutları

```bash
# Servisi başlat
sudo systemctl start okx-trading-bot

# Servisi durdur
sudo systemctl stop okx-trading-bot

# Servisi yeniden başlat (kod değişikliklerinden sonra)
sudo systemctl restart okx-trading-bot

# Servis durumunu kontrol et
sudo systemctl status okx-trading-bot

# Boot'ta otomatik başlatmayı aktif et
sudo systemctl enable okx-trading-bot

# Boot'ta otomatik başlatmayı kapat
sudo systemctl disable okx-trading-bot
```

### Log İzleme

```bash
# Gerçek zamanlı log izleme
sudo journalctl -u okx-trading-bot -f

# Son 100 satır log
sudo journalctl -u okx-trading-bot -n 100

# Bugünün logları
sudo journalctl -u okx-trading-bot --since today

# Belirli tarih aralığı
sudo journalctl -u okx-trading-bot --since "2024-01-01" --until "2024-01-31"

# Nginx logları
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

### Kod Güncelleme (Git ile)

```bash
# botuser kullanıcısına geç
sudo su - botuser

# Kod güncelle
cd ~/okx-trading-bot
git pull origin main

# Virtual environment aktif et
source venv/bin/activate

# Yeni paketler varsa yükle
pip install -r requirements.txt

# botuser'dan çık
exit

# Servisi yeniden başlat
sudo systemctl restart okx-trading-bot
```

---

## 1️⃣1️⃣ Güvenlik Ayarları

### Firewall Kuralları

```bash
# Sadece gerekli portları aç
sudo ufw allow 22/tcp      # SSH
sudo ufw allow 80/tcp      # HTTP
sudo ufw allow 443/tcp     # HTTPS

# Streamlit portunu KAPAT (nginx üzerinden erişilmeli)
sudo ufw deny 8501/tcp

# PostgreSQL portunu KAPAT (sadece localhost)
sudo ufw deny 5432/tcp

# Firewall durumu
sudo ufw status verbose
```

### SSH Güvenliği (Opsiyonel ama Önerilen)

```bash
# SSH için key-based authentication kullan
# Kendi bilgisayarında SSH key oluştur:
ssh-keygen -t ed25519 -C "your-email@example.com"

# Public key'i sunucuya kopyala:
ssh-copy-id botuser@YOUR_SERVER_IP

# Sunucuda password authentication'ı kapat
sudo nano /etc/ssh/sshd_config

# Şu satırları değiştir:
# PasswordAuthentication no
# PubkeyAuthentication yes

# SSH'ı yeniden başlat
sudo systemctl restart sshd
```

### Fail2Ban Kurulumu (Brute Force Koruması)

```bash
# Fail2ban kur
sudo apt install fail2ban -y

# Konfigürasyon dosyası oluştur
sudo cp /etc/fail2ban/jail.conf /etc/fail2ban/jail.local
sudo nano /etc/fail2ban/jail.local

# [sshd] bölümünü bul ve aktif et:
# enabled = true
# maxretry = 3

# Fail2ban başlat
sudo systemctl start fail2ban
sudo systemctl enable fail2ban

# Durumu kontrol et
sudo fail2ban-client status
```

---

## 1️⃣2️⃣ İzleme ve Performans

### Sistem Kaynaklarını İzleme

```bash
# Gerçek zamanlı sistem monitörü
htop

# Disk kullanımı
df -h

# Bellek kullanımı
free -h

# Streamlit process'ini izle
ps aux | grep streamlit

# Port dinleme kontrolü
sudo netstat -tulpn | grep 8501
```

### Uptime Monitoring (Harici Servisler)

**Ücretsiz seçenekler:**
- UptimeRobot (https://uptimerobot.com)
- Pingdom (https://www.pingdom.com)
- StatusCake (https://www.statuscake.com)

**Ayarlar:**
- URL: `https://yourdomain.com`
- Check interval: 5 dakika
- Alert email: your-email@example.com

---

## 1️⃣3️⃣ Yedekleme Stratejisi

### Database Yedekleme

```bash
# Otomatik yedekleme scripti
nano /home/botuser/backup.sh
```

```bash
#!/bin/bash
BACKUP_DIR="/home/botuser/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="okx_trading_bot"

mkdir -p $BACKUP_DIR

# PostgreSQL dump
pg_dump -U bot_user -h localhost $DB_NAME | gzip > $BACKUP_DIR/db_backup_$DATE.sql.gz

# Eski yedekleri sil (30 günden eski)
find $BACKUP_DIR -name "db_backup_*.sql.gz" -mtime +30 -delete

echo "Backup completed: db_backup_$DATE.sql.gz"
```

```bash
# Script'i çalıştırılabilir yap
chmod +x /home/botuser/backup.sh

# Cron job ekle (her gün saat 03:00'te)
crontab -e

# Şu satırı ekle:
0 3 * * * /home/botuser/backup.sh >> /home/botuser/backup.log 2>&1
```

### Kod Yedekleme

```bash
# Git repository'e push et (otomatik yedekleme)
cd /home/botuser/okx-trading-bot
git add .
git commit -m "Production backup $(date +%Y-%m-%d)"
git push origin main
```

---

## 1️⃣4️⃣ Sorun Giderme

### Yaygın Sorunlar ve Çözümler

| Sorun | Çözüm |
|-------|-------|
| **"Please wait..." sonsuza kadar bekliyor** | Nginx WebSocket headers eksik. Config'i kontrol et: `proxy_set_header Upgrade $http_upgrade;` |
| **Port 8501'e dışarıdan erişilebiliyor** | Firewall konfigürasyonu yanlış. `sudo ufw deny 8501/tcp` çalıştır |
| **SSL sertifika hatası** | `sudo certbot renew --force-renewal` çalıştır |
| **Uygulama başlamıyor** | Log'lara bak: `sudo journalctl -u okx-trading-bot -n 50` |
| **Database bağlantı hatası** | DATABASE_URL doğru mu? PostgreSQL çalışıyor mu? `sudo systemctl status postgresql` |
| **"Module not found" hatası** | Virtual environment aktif mi? `source venv/bin/activate` ve `pip list` kontrol et |
| **Yavaş performans** | RAM/CPU yetersiz olabilir. `htop` ile kontrol et. Sunucuyu büyüt. |
| **CORS hatası** | config.toml'de `enableCORS = false` ayarlı olmalı |

### Debug Modu

```bash
# Streamlit'i debug modu ile manuel başlat
cd /home/botuser/okx-trading-bot
source venv/bin/activate
streamlit run app.py --server.port 8501 --logger.level=debug
```

### Health Check

```bash
# Streamlit health endpoint
curl http://localhost:8501/_stcore/health

# Expected response: {"status": "ok"}
```

---

## 1️⃣5️⃣ Production Checklist

Deployment öncesi kontrol listesi:

- ✅ PostgreSQL kurulu ve çalışıyor
- ✅ Database oluşturuldu ve tablolar var
- ✅ Environment variables doğru ayarlanmış (.env dosyası)
- ✅ SESSION_SECRET rastgele ve güçlü
- ✅ OKX API keys demo trading için
- ✅ Python dependencies yüklenmiş
- ✅ systemd service çalışıyor ve boot'ta aktif
- ✅ Nginx reverse proxy çalışıyor
- ✅ SSL sertifikası kurulu (HTTPS)
- ✅ Firewall sadece 22, 80, 443 portlarına izin veriyor
- ✅ Yedekleme stratejisi aktif
- ✅ Uptime monitoring kurulu
- ✅ Log rotation ayarlanmış
- ✅ Domain DNS kayıtları doğru (A record)

---

## 1️⃣6️⃣ Domain Ayarları

### DNS Kayıtları (Hosting sağlayıcınızda)

```
Type  | Name | Value          | TTL
------|------|----------------|-----
A     | @    | YOUR_SERVER_IP | 3600
A     | www  | YOUR_SERVER_IP | 3600
```

### Domain Kontrolü

```bash
# DNS propagation kontrol et
nslookup yourdomain.com

# Nginx ile test
curl -I http://yourdomain.com
```

---

## 1️⃣7️⃣ İlk Kullanım

### Uygulamayı Açın

Tarayıcıda: `https://yourdomain.com`

### İlk Kurulum Adımları

1. **Settings** sekmesine gidin
2. **OKX API Keys** girin (Demo Trading keys)
3. **Auto-reopen delay** ayarlayın (varsayılan: 1 dakika)
4. **Save API Keys** butonuna tıklayın
5. **▶️ Botu Başlat** butonuna tıklayın
6. **New Trade** sekmesinden ilk pozisyonunuzu açın

---

## 1️⃣8️⃣ Performans Optimizasyonu

### PostgreSQL Tuning (Büyük Sunucular İçin)

```bash
sudo nano /etc/postgresql/14/main/postgresql.conf
```

```ini
# 4GB RAM için örnek ayarlar
shared_buffers = 1GB
effective_cache_size = 3GB
maintenance_work_mem = 256MB
checkpoint_completion_target = 0.9
wal_buffers = 16MB
default_statistics_target = 100
random_page_cost = 1.1
effective_io_concurrency = 200
work_mem = 10485kB
min_wal_size = 1GB
max_wal_size = 4GB
```

```bash
# PostgreSQL'i yeniden başlat
sudo systemctl restart postgresql
```

### Nginx Caching (Opsiyonel)

```nginx
# Static dosyalar için cache
location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
    expires 1y;
    add_header Cache-Control "public, immutable";
}
```

---

## 1️⃣9️⃣ Ek Özellikler

### Auto-Deploy Script (Git ile)

```bash
# auto_deploy.sh oluştur
nano /home/botuser/auto_deploy.sh
```

```bash
#!/bin/bash
cd /home/botuser/okx-trading-bot
git pull origin main
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart okx-trading-bot
echo "Deployment completed at $(date)"
```

```bash
chmod +x /home/botuser/auto_deploy.sh

# Manuel kullanım
./auto_deploy.sh
```

### Email Alerts (Kritik Hatalar İçin)

```bash
# Postfix kur
sudo apt install postfix mailutils -y

# /etc/aliases düzenle
sudo nano /etc/aliases

# En sona ekle:
root: your-email@example.com

# Aliases'ı güncelle
sudo newaliases

# Test email gönder
echo "Test email" | mail -s "Test Subject" your-email@example.com
```

---

## ⚠️ Önemli Notlar

1. **Demo Trading**: Bu bot OKX Demo Trading için yapılandırılmıştır. Gerçek para kullanmaz!

2. **API Keys**: Demo API keys'i OKX Dashboard → API Management'tan alın.

3. **Database Güvenliği**: Production'da kesinlikle güçlü şifreler kullanın!

4. **Backup**: Database yedeklerini düzenli alın. Pozisyon verileri kaybolabilir!

5. **Monitoring**: Uptime monitoring kurarak 7/24 çalışma garantisi sağlayın.

6. **Updates**: Düzenli olarak system updates ve security patches uygulayın:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```

7. **Logs**: Disk dolmasını önlemek için log rotation aktif olmalı (systemd varsayılan)

---

## 📞 Destek ve Yardım

### Loglar

Sorun yaşarsanız, şu logları kontrol edin:

```bash
# Uygulama logları
sudo journalctl -u okx-trading-bot -n 100

# Nginx logları
sudo tail -n 100 /var/log/nginx/error.log

# PostgreSQL logları
sudo tail -n 100 /var/log/postgresql/postgresql-14-main.log
```

### Test Komutları

```bash
# Streamlit çalışıyor mu?
curl http://localhost:8501/_stcore/health

# Nginx çalışıyor mu?
sudo systemctl status nginx

# PostgreSQL çalışıyor mu?
sudo systemctl status postgresql

# Port dinleme kontrolü
sudo netstat -tulpn | grep -E "8501|80|443|5432"
```

---

## 🎉 Tebrikler!

Bot artık kendi sunucunuzda çalışıyor! 

**Erişim:** `https://yourdomain.com`

**Güvenlik Kontrolleri:**
- ✅ HTTPS aktif
- ✅ Firewall yapılandırılmış
- ✅ systemd ile otomatik restart
- ✅ Database yedekleme aktif

**İyi Trading'ler!** 🚀📈
