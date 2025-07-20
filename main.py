from fastapi import FastAPI, Depends, HTTPException, Request
from pydantic import BaseModel
import subprocess
import os
import logging
import signal
from pathlib import Path

# Konfigurasi logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Ambil API Key dari environment variable untuk keamanan
API_KEY = os.getenv("VPS_AGENT_API_KEY", "change-this-in-production")
PID_DIR = Path("/tmp/stream_pids")
PID_DIR.mkdir(exist_ok=True)

app = FastAPI()

# Kamus untuk menyimpan proses yang sedang berjalan
# Key: stream_id, Value: subprocess.Popen object
stream_processes = {}

class StreamStartRequest(BaseModel):
    ffmpeg_command: list
    stream_id: int

class StreamStopRequest(BaseModel):
    stream_id: int

# Dependensi untuk memeriksa API Key
async def verify_api_key(request: Request):
    provided_key = request.headers.get("X-API-Key")
    if not provided_key or provided_key != API_KEY:
        logger.warning(f"Upaya akses tidak sah dari IP: {request.client.host}")
        raise HTTPException(status_code=403, detail="Akses ditolak: API Key tidak valid atau tidak ada.")
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
            # File PID rusak atau hilang, lanjutkan
            pass

    command = request.ffmpeg_command
    logger.info(f"Menerima permintaan untuk memulai stream {stream_id} dengan perintah: {' '.join(command)}")

    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, universal_newlines=True
        )
        
        # Simpan proses dan PID-nya
        stream_processes[stream_id] = process
        pid_file.write_text(str(process.pid))
        
        logger.info(f"Proses FFmpeg untuk stream {stream_id} dimulai dengan PID: {process.pid}")
        return {"message": "Proses streaming berhasil dimulai.", "pid": process.pid, "stream_id": stream_id}
    except Exception as e:
        logger.error(f"Gagal memulai proses FFmpeg untuk stream {stream_id}: {e}")
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