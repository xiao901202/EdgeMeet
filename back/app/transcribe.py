from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse, FileResponse
import os

router = APIRouter()
UPLOAD_DIR = os.path.abspath("./uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # 建立資料夾與儲存音訊檔
    filename = file.filename
    base_name = os.path.splitext(filename)[0]
    target_dir = os.path.join(UPLOAD_DIR, base_name)
    os.makedirs(target_dir, exist_ok=True)

    audio_path = os.path.join(target_dir, filename)
    with open(audio_path, "wb") as f:
        f.write(contents)

    # 模擬本地產生轉錄與摘要
    transcript_text = f"{filename} 的轉錄內容\n這是一段模擬的轉錄文字。"
    summary_text = f"{filename} 的摘要\n這是一段模擬的會議摘要。"

    transcript_path = os.path.join(target_dir, "transcript.txt")
    summary_path = os.path.join(target_dir, "summary.txt")

    with open(transcript_path, "w", encoding="utf-8") as tf:
        tf.write(transcript_text)

    with open(summary_path, "w", encoding="utf-8") as sf:
        sf.write(summary_text)

    # 讀取文字內容以回傳
    with open(transcript_path, "r", encoding="utf-8") as tf:
        transcript_content = tf.read()

    with open(summary_path, "r", encoding="utf-8") as sf:
        summary_content = sf.read()

    return JSONResponse(content={
        "filename": filename,
        "status": "uploaded",
        "paths": {
            "audio_url": f"/uploads/{base_name}/{filename}",
            "transcript_url": f"/uploads/{base_name}/transcript.txt",
            "summary_url": f"/uploads/{base_name}/summary.txt",
        },
        "transcript": transcript_content,
        "summary": summary_content
    })
