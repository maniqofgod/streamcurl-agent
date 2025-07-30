from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import os
import logging
import signal
from pathlib import Path
import requests
import threading

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ambil API Key dari environment variable untuk keamanan
API_KEY = os.getenv("VPS_AGENT_API_KEY", "change-this-in-production")
PID_DIR = Path("/tmp/stream_pids")
PID_DIR.mkdir(exist_ok=True)

app = FastAPI()

# Tambahkan CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Mengizinkan semua origin. Batasi ini di produksi jika memungkinkan.
    allow_credentials=True,
    allow_methods=["*"],  # Mengizinkan semua metode (GET, POST, dll.)
    allow_headers=["*"],  # Mengizinkan semua header
)

# Kamus untuk menyimpan proses yang sedang berjalan
# Key: stream_id, Value: subprocess.Popen object
stream_processes = {}

class StreamStartRequest(BaseModel):
    ffmpeg_command: list
    stream_id: int
    callback_url: str | None = None
    callback_api_key: str | None = None

class StreamStopRequest(BaseModel):
    stream_id: int

# Dependensi untuk memeriksa API Key
async def verify_api_key(request: Request):
    auth_header = request.headers.get("Authorization")
    logger.info(f"Menerima permintaan dari {request.client.host} dengan header: {request.headers}")
    
    if not auth_header or not auth_header.startswith("Bearer "):
        logger.warning(f"Upaya akses tidak sah dari IP: {request.client.host}. Header 'Authorization' hilang atau formatnya salah.")
        raise HTTPException(status_code=403, detail="Akses ditolak: Header 'Authorization' tidak valid.")
        
    provided_key = auth_header.split(" ")[1]
    
    if provided_key != API_KEY:
        # Log a masked version of the key for security
        masked_key = f"{provided_key[:4]}...{provided_key[-4:]}" if len(provided_key) > 8 else provided_key
        logger.warning(
            f"Upaya akses tidak sah dari IP: {request.client.host}. "
            f"Kunci yang diberikan ({masked_key}) tidak cocok dengan kunci yang diharapkan."
        )
        raise HTTPException(status_code=403, detail="Akses ditolak: API Key tidak valid.")
        
    return True

def get_pid_file(stream_id: int) -> Path:
    return PID_DIR / f"stream_{stream_id}.pid"

def is_process_running(pid: int) -> bool:
    """Memeriksa apakah proses dengan PID yang diberikan sedang berjalan."""
    if pid is None:
        return False
    try:
        # Mengirim sinyal 0 tidak membunuh proses, tetapi akan menimbulkan error jika proses tidak ada
        os.kill(pid, 0)
    except OSError:
        return False
    else:
        return True

def send_callback(url: str, api_key: str, stream_id: int, status: str, details: str):
    """Mengirim pembaruan status kembali ke backend dalam thread terpisah."""
    try:
        headers = {"X-Agent-Token": api_key}
        payload = {"stream_id": stream_id, "status": status, "details": details}
        requests.post(url, json=payload, headers=headers, timeout=15)
        logger.info(f"Callback terkirim ke {url} untuk stream {stream_id} dengan status {status}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Gagal mengirim callback ke {url} untuk stream {stream_id}: {e}")

def log_ffmpeg_output(process: subprocess.Popen, stream_id: int):
    """Membaca dan mencatat output dari proses FFmpeg."""
    for line in iter(process.stdout.readline, ''):
        logger.info(f"FFMPEG (stream {stream_id}): {line.strip()}")
    process.stdout.close()
    return_code = process.wait()
    if return_code:
        logger.error(f"Proses FFmpeg untuk stream {stream_id} berhenti dengan kode error: {return_code}")

@app.post("/stream/start", dependencies=[Depends(verify_api_key)])
async def start_stream(request: StreamStartRequest):
    stream_id = request.stream_id
    pid_file = get_pid_file(stream_id)

    if pid_file.exists():
        try:
            pid = int(pid_file.read_text())
            if is_process_running(pid):
                logger.warning(f"Stream {stream_id} sudah berjalan dengan PID {pid}.")
                raise HTTPException(status_code=409, detail=f"Stream {stream_id} sudah berjalan.")
        except (ValueError, FileNotFoundError):
            pass

    command = request.ffmpeg_command
    logger.info(f"Menerima permintaan untuk memulai stream {stream_id} dengan perintah: {' '.join(command)}")

    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, universal_newlines=True
        )
        
        stream_processes[stream_id] = process
        pid_file.write_text(str(process.pid))
        
        # Mulai thread untuk mencatat output FFmpeg
        log_thread = threading.Thread(target=log_ffmpeg_output, args=(process, stream_id))
        log_thread.start()
        
        logger.info(f"Proses FFmpeg untuk stream {stream_id} dimulai dengan PID: {process.pid}")

        if request.callback_url and request.callback_api_key:
            threading.Thread(
                target=send_callback,
                args=(request.callback_url, request.callback_api_key, stream_id, "LIVE", f"Stream started on VPS with PID {process.pid}")
            ).start()

        return {"message": "Proses streaming berhasil dimulai.", "pid": process.pid, "stream_id": stream_id}
    except Exception as e:
        logger.error(f"Gagal memulai proses FFmpeg untuk stream {stream_id}: {e}")
        
        if request.callback_url and request.callback_api_key:
             threading.Thread(
                target=send_callback,
                args=(request.callback_url, request.callback_api_key, stream_id, "Error", str(e))
            ).start()

        raise HTTPException(status_code=500, detail=f"Gagal memulai FFmpeg: {str(e)}")

@app.post("/stream/stop", dependencies=[Depends(verify_api_key)])
async def stop_stream(request: StreamStopRequest):
    stream_id = request.stream_id
    pid_file = get_pid_file(stream_id)
    
    logger.info(f"Menerima permintaan untuk menghentikan stream {stream_id}")

    pid = None
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text())
        except (ValueError, FileNotFoundError):
            logger.warning(f"File PID untuk stream {stream_id} rusak atau tidak dapat dibaca.")
    
    if not pid or not is_process_running(pid):
        if pid_file.exists():
            pid_file.unlink() # Hapus file PID yang usang
        logger.info(f"Stream {stream_id} tidak sedang berjalan atau PID tidak ditemukan.")
        return {"message": "Stream tidak sedang berjalan."}

    try:
        os.kill(pid, signal.SIGTERM)
        logger.info(f"Sinyal SIGTERM dikirim ke proses {pid} untuk stream {stream_id}.")
        
        # Hapus dari pelacakan
        if stream_id in stream_processes:
            del stream_processes[stream_id]
        if pid_file.exists():
            pid_file.unlink()
            
        return {"message": f"Permintaan penghentian untuk stream {stream_id} berhasil dikirim."}
    except OSError as e:
        logger.error(f"Gagal menghentikan proses {pid} untuk stream {stream_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Gagal menghentikan proses: {e}")

@app.get("/stream/status/{stream_id}", dependencies=[Depends(verify_api_key)])
async def get_stream_status(stream_id: int):
    pid_file = get_pid_file(stream_id)
    
    if not pid_file.exists():
        return {"status": "Idle", "stream_id": stream_id}

    try:
        pid = int(pid_file.read_text())
        if is_process_running(pid):
            return {"status": "Running", "stream_id": stream_id, "pid": pid}
        else:
            # Proses tidak berjalan, file PID usang
            logger.warning(f"File PID usang ditemukan untuk stream {stream_id} (PID: {pid}). Menghapus file.")
            pid_file.unlink()
            return {"status": "Idle", "stream_id": stream_id}
    except (ValueError, FileNotFoundError):
        return {"status": "Idle", "stream_id": stream_id}

@app.get("/health")
async def health_check():
    """Endpoint sederhana untuk memeriksa apakah agen berjalan."""
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    logger.info("Memulai VPS Agent...")
    uvicorn.run(app, host="0.0.0.0", port=8001)