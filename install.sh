#!/bin/bash

# Skrip untuk menginstal dan mengkonfigurasi Agen VPS untuk Platform Streaming
# Cukup jalankan skrip ini di VPS Linux baru (disarankan Ubuntu 20.04+).

# --- Konfigurasi ---
REPO_URL="https://github.com/maniqofgod/streamcurl-agent.git"
# --------------------

# Warna untuk output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Fungsi untuk mencetak pesan
log_info() {
    echo -e "${GREEN}[INFO] $1${NC}"
}

log_warn() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

log_error() {
    echo -e "${RED}[ERROR] $1${NC}"
}

# Pastikan skrip tidak dijalankan sebagai root secara langsung
if [ "$EUID" -eq 0 ]; then
  log_error "Jangan jalankan skrip ini sebagai root. Jalankan sebagai pengguna biasa, skrip akan meminta password sudo jika diperlukan."
  exit 1
fi

log_info "Memulai penyiapan Agen VPS..."

# 1. Instal Dependensi Sistem
log_info "Memeriksa dan menginstal dependensi sistem (git, ffmpeg, python3, pip)..."
sudo apt-get update > /dev/null 2>&1
if ! command -v git &> /dev/null || ! command -v ffmpeg &> /dev/null || ! command -v python3 &> /dev/null || ! command -v pip3 &> /dev/null; then
    sudo apt-get install -y git ffmpeg python3-pip
else
    log_info "Dependensi sistem sudah terinstal."
fi

# 2. Klona atau Perbarui Repositori Aplikasi
REPO_NAME=$(basename -s .git "$REPO_URL")
AGENT_DIR="/home/$(whoami)/$REPO_NAME"

log_info "Mengklona atau memperbarui repositori dari $REPO_URL..."
if [ -d "$AGENT_DIR/.git" ]; then
    log_info "Direktori repositori sudah ada. Menjalankan 'git pull'..."
    cd "$AGENT_DIR"
    if ! git pull; then
        log_error "Gagal menjalankan 'git pull'. Harap periksa repositori Anda untuk konflik atau masalah lainnya."
        exit 1
    fi
else
    log_info "Mengklona repositori baru ke $AGENT_DIR..."
    if ! git clone "$REPO_URL" "$AGENT_DIR"; then
        log_error "Gagal mengklona repositori. Periksa URL dan pastikan repositori bersifat publik."
        exit 1
    fi
fi

# Pindah ke direktori agen
log_info "Masuk ke direktori agen di $AGENT_DIR"
cd "$AGENT_DIR" || { log_error "Gagal masuk ke direktori agen di $AGENT_DIR."; exit 1; }

# 3. Instal Dependensi Python
log_info "Menginstal dependensi Python dari requirements.txt..."
pip3 install -r requirements.txt > /dev/null 2>&1

# 4. Konfigurasi Kunci API
log_info "Konfigurasi Kunci API..."
read -p "Masukkan Kunci API yang ingin Anda gunakan (biarkan kosong untuk membuat secara acak): " USER_API_KEY
if [ -z "$USER_API_KEY" ]; then
    log_info "Membuat Kunci API acak..."
    USER_API_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')
fi

tee .env > /dev/null <<EOF
VPS_AGENT_API_KEY=$USER_API_KEY
EOF

# 5. Buat Layanan Systemd
AGENT_PORT=8001
SERVICE_FILE="/etc/systemd/system/vps-agent.service"
CURRENT_USER=$(whoami)

log_info "Membuat layanan systemd..."

SERVICE_CONTENT="[Unit]
Description=VPS Agent for Streaming Platform
After=network.target

[Service]
User=$CURRENT_USER
Group=$(id -gn "$CURRENT_USER")
WorkingDirectory=$AGENT_DIR
# Muat variabel lingkungan dari file .env
EnvironmentFile=$AGENT_DIR/.env
ExecStart=$(which python3) -m uvicorn main:app --host 0.0.0.0 --port $AGENT_PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target"

echo "$SERVICE_CONTENT" | sudo tee $SERVICE_FILE > /dev/null

log_info "Mengaktifkan dan memulai layanan vps-agent..."
sudo systemctl daemon-reload
sudo systemctl enable vps-agent.service > /dev/null 2>&1
sudo systemctl restart vps-agent.service

# 6. Konfigurasi Firewall
log_info "Mengkonfigurasi firewall untuk mengizinkan port $AGENT_PORT..."
sudo ufw allow $AGENT_PORT/tcp > /dev/null 2>&1
sudo ufw reload > /dev/null 2>&1

# 7. Deteksi Sumber Daya Sistem
log_info "Mendeteksi sumber daya sistem..."
CPU_CORES=$(nproc)
# Dapatkan total RAM dalam MB dan bulatkan ke GB terdekat
TOTAL_RAM_MB=$(free -m | awk '/^Mem:/{print $2}')
TOTAL_RAM_GB=$(( (TOTAL_RAM_MB + 512) / 1024 )) # Pembulatan ke atas

# Selesai
log_info "Penyiapan Selesai!"
echo -e "--------------------------------------------------"
echo -e "${YELLOW}Harap simpan informasi berikut di tempat yang aman dan masukkan ke dalam platform Anda:${NC}"
echo -e "  ${GREEN}Alamat IP VPS: $(hostname -I | awk '{print $1}')${NC}"
echo -e "  ${GREEN}Port Agen: $AGENT_PORT${NC}"
echo -e "  ${GREEN}Kunci API Anda: $USER_API_KEY${NC}"
echo -e "  ${YELLOW}--- Spesifikasi VPS Terdeteksi ---${NC}"
echo -e "  ${GREEN}Total Core CPU: $CPU_CORES${NC}"
echo -e "  ${GREEN}Total RAM: $TOTAL_RAM_GB GB${NC}"
echo -e "--------------------------------------------------"
echo -e "Anda dapat memeriksa status layanan dengan menjalankan: ${YELLOW}sudo systemctl status vps-agent${NC}"
