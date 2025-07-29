# Panduan Instalasi dan Manajemen Agen VPS

Dokumen ini memberikan panduan langkah demi langkah untuk menginstal, mengkonfigurasi, dan mengelola Agen VPS pada server Linux.

---

## 1. Prasyarat

- Server VPS baru yang menjalankan **Ubuntu 20.04 atau lebih baru**.
- Akses ke server melalui SSH dengan pengguna yang memiliki hak `sudo`.

---

## 2. Proses Instalasi

Proses instalasi ditangani oleh skrip `install.sh`. Skrip ini akan menginstal perangkat lunak yang diperlukan, mengkonfigurasi agen, dan menjalankannya sebagai layanan sistem.

### Langkah 1: Salin File Agen ke VPS

Salin seluruh direktori `vps-agent` dari proyek lokal Anda ke direktori home pengguna di VPS Anda. Anda dapat menggunakan `scp` (Secure Copy) untuk ini.

Buka terminal di komputer **lokal** Anda, navigasikan ke direktori proyek Anda, dan jalankan perintah berikut (ganti `pengguna_vps` dan `alamat_ip_vps`):

```bash
scp -r vps-agent/ pengguna_vps@alamat_ip_vps:~/
```

### Langkah 2: Jalankan Skrip Instalasi

Masuk ke VPS Anda melalui SSH:

```bash
ssh pengguna_vps@alamat_ip_vps
```

Navigasikan ke direktori agen yang baru saja Anda salin dan jalankan skrip instalasi:

```bash
cd vps-agent
bash install.sh
```

### Langkah 3: Konfigurasi Kunci API

Selama instalasi, skrip akan menanyakan Anda untuk Kunci API:

```
Masukkan Kunci API yang ingin Anda gunakan (biarkan kosong untuk membuat secara acak):
```

- **Opsi 1 (Direkomendasikan):** Tekan **Enter** (biarkan kosong). Skrip akan secara otomatis membuat kunci API yang kuat dan aman untuk Anda.
- **Opsi 2:** Anda dapat mengetik kunci API kustom Anda sendiri dan menekan Enter.

---

## 3. Mengelola Agen Setelah Instalasi

Setelah skrip selesai, ia akan menampilkan informasi penting yang Anda perlukan untuk menghubungkan agen ke platform streaming utama Anda.

### Menemukan Detail Koneksi Anda

Skrip akan menampilkan output yang terlihat seperti ini:

```
--------------------------------------------------
Harap simpan informasi berikut di tempat yang aman dan masukkan ke dalam platform Anda:
  Alamat IP VPS: 192.168.1.100
  Port Agen: 8001
  Kunci API Anda: 2d8b3c... (kunci yang sangat panjang) ...a9f4
--- Spesifikasi VPS Terdeteksi ---
  Total Core CPU: 4
  Total RAM: 8 GB
--------------------------------------------------
```

- **Alamat IP VPS**: Ini adalah alamat IP publik dari server VPS Anda.
- **Port Agen**: Selalu `8001`.
- **Kunci API Anda**: Ini adalah token rahasia yang digunakan untuk mengamankan komunikasi.

Salin ketiga nilai ini. Anda akan memasukkannya ke dalam formulir "Tambah VPS" di antarmuka web platform streaming Anda.

### Perintah Manajemen Layanan

Agen berjalan sebagai layanan `systemd` di latar belakang. Anda dapat mengelolanya dengan perintah berikut:

- **Memeriksa Status Agen:**
  Untuk melihat apakah agen sedang berjalan dan memeriksa log terbarunya.
  ```bash
  sudo systemctl status vps-agent
  ```

- **Melihat Log Secara Langsung:**
  Untuk melihat output log dari agen secara real-time, yang berguna untuk debugging.
  ```bash
  sudo journalctl -u vps-agent -f
  ```

- **Memulai Ulang Agen:**
  Jika Anda perlu memulai ulang layanan agen karena alasan apa pun.
  ```bash
  sudo systemctl restart vps-agent
  ```

- **Menghentikan Agen:**
  ```bash
  sudo systemctl stop vps-agent
  ```

- **Memulai Agen:**
  ```bash
  sudo systemctl start vps-agent