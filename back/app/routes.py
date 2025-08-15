from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
import os
from .schemas import ConferenceRecord
from .transcribe import router as transcribe_router

router = APIRouter()
UPLOAD_DIR = os.path.abspath("./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 模擬記憶體資料庫
conference_records = []


@router.get("/")
async def health_check():
    return {"status": "ok"}


@router.get("/uploads/{folder}/{filename}")
async def get_uploaded_file(folder: str, filename: str):
    file_path = os.path.join(UPLOAD_DIR, folder, filename)
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    media_type = "application/octet-stream"
    if filename.endswith(".wav"):
        media_type = "audio/wav"
    elif filename.endswith(".txt"):
        media_type = "text/plain"

    return FileResponse(file_path, media_type=media_type, filename=filename)


@router.post("/record")
async def receive_conference_record(record: ConferenceRecord):
    filename = os.path.basename(record.file_path)
    folder = os.path.splitext(filename)[0]

    record.summary_url = f"/uploads/{folder}/summary.txt"
    record.transcript_url = f"/uploads/{folder}/transcript.txt"

    conference_records.append(record)

    return {
        "message": "Record received",
        "title": record.title,
        "segments_count": len(record.transcript_segments),
        "summary_url": record.summary_url,
        "transcript_url": record.transcript_url
    }


@router.get("/records")
async def list_conference_records():
    for record in conference_records:
        if not record.summary_url or not record.transcript_url:
            filename = os.path.basename(record.file_path)
            folder = os.path.splitext(filename)[0]
            record.summary_url = f"/uploads/{folder}/summary.txt"
            record.transcript_url = f"/uploads/{folder}/transcript.txt"
    return conference_records


# 轉錄 router
router.include_router(transcribe_router)
