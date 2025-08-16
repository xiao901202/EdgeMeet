from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Tuple
from pathlib import Path
import os
import math
import json
import wave
import numpy as np
from io import BytesIO

# 音訊處理（需 ffmpeg 或 avlib）：pip install pydub
from pydub import AudioSegment

# AI 模型相關 imports
from kuwa.client import KuwaClient
from qai_hub_models.models.whisper_large_v3_turbo.model import WhisperLargeV3Turbo
from qai_hub_models.models._shared.hf_whisper.app import HfWhisperApp

router = APIRouter()

UPLOAD_DIR = Path("./uploads").resolve()
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# ===== 規格 =====
CHUNK_SECONDS = 20          # 每段長度
OVERLAP_SECONDS = 2         # 與前段重疊
TARGET_SR = 16000           # 建議轉錄取樣率
TARGET_CH = 1               # 單聲道
TARGET_BITS = 16            # 16-bit PCM

# ===== AI 模型參數 =====
VOLUME_THRESHOLD = 3        # 音量閾值
SUMMARY_BATCH_SIZE = 3      # 每3段做一次摘要

# ===== 檔名/資料夾 =====
TRANSCRIPT_JSON = "transcript.json"  # 逐段清單（含 start/end/text）
SUMMARY_JSON   = "summary.json"      # 整體摘要 +（可選）逐段摘要
FULL_WAV       = "base.wav"          # 伺服端規一化後的完整 WAV
CHUNK_DIRNAME  = "chunks"            # 片段資料夾（001.wav, 002.wav, ...）
STREAM_CHUNKS  = "stream_chunks"     # 串流上傳暫存的 20s 分段（001.wav, 002.wav, ...）

# ===== 狀態標記 =====
PROCESSING_TEXT = "處理中..."
PROCESSING_SUMMARY = "處理中..."

# ===== 全域 AI 模型實例 =====
whisper_app = None
kuwa_client = None

def init_ai_models():
    """初始化 AI 模型"""
    global whisper_app, kuwa_client
    try:
        print("正在載入 Whisper 模型...")
        model = WhisperLargeV3Turbo.from_pretrained()
        whisper_app = HfWhisperApp(model)
        print("✅ Whisper 模型載入完成")
        
        # 初始化 KuwaClient
        kuwa_client = KuwaClient(
            base_url="http://127.0.0.1",
            model=".bot/TAIDE LX 8B",
            auth_token=os.environ.get("KUWA_API_KEY")
        )
        print("✅ KuwaClient 初始化完成")
        
    except Exception as e:
        print(f"❌ AI 模型初始化失敗: {e}")
        raise e

# 在模組載入時初始化模型
try:
    init_ai_models()
except Exception as e:
    print(f"警告：AI 模型初始化失敗，將使用模擬模式: {e}")
    whisper_app = None
    kuwa_client = None


# ===============================
# 工具/輔助
# ===============================
def _canonicalize_bytes_to_wav16k_mono(contents: bytes, out_wav: Path, src_ext: str) -> Path:
    """
    將上傳 bytes（依副檔名推格式）直接轉成 16k/mono/16bit WAV，輸出到 out_wav。
    不在磁碟上留下原始檔。
    """
    ext = (src_ext or "").lstrip(".").lower() or None
    audio = AudioSegment.from_file(BytesIO(contents), format=ext)
    audio = audio.set_frame_rate(TARGET_SR).set_channels(TARGET_CH).set_sample_width(TARGET_BITS // 8)
    audio.export(out_wav.as_posix(), format="wav")
    return out_wav


def _ensure_folder(base_name: str) -> Path:
    folder = UPLOAD_DIR / base_name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _index_to_times(i: int) -> Tuple[float, float]:
    """第 i 段（1-based）的 [start, end) 秒數（含 2 秒重疊邏輯的步進）。"""
    step = CHUNK_SECONDS - OVERLAP_SECONDS
    start = (i - 1) * step
    end   = start + CHUNK_SECONDS
    return float(start), float(end)


def _time_to_index(t: float, total_seconds: float) -> int:
    """時間 t（秒）對應到第幾段（1-based）。"""
    if t < 0: t = 0.0
    step = CHUNK_SECONDS - OVERLAP_SECONDS
    idx = int(t // step) + 1
    # 上限保護（以最後一段 end 略估總長）
    max_idx = max(1, math.ceil((max(0.0, total_seconds) - OVERLAP_SECONDS) / step))
    return min(idx, max_idx)


def check_audio_volume(wav_path: Path) -> float:
    """檢查音量強度"""
    try:
        with wave.open(str(wav_path), 'rb') as wf:
            frames = wf.readframes(wf.getnframes())
            audio_data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32767.0
            volume = np.linalg.norm(audio_data)
            return float(volume)  # 明確轉換為 Python 原生 float
    except Exception as e:
        print(f"❌ 無法讀取音訊檔案 {wav_path}: {e}")
        return 0.0


def _init_json_files(folder: Path, total_estimated_segments: int = 0) -> Tuple[Path, Path]:
    """初始化 JSON 檔案，預先創建帶有處理中狀態的結構"""
    tr_path = folder / TRANSCRIPT_JSON
    sm_path = folder / SUMMARY_JSON
    
    # 初始化 transcript.json
    if not tr_path.exists():
        tr_data = {
            "base_name": folder.name,
            "chunk_seconds": CHUNK_SECONDS,
            "overlap_seconds": OVERLAP_SECONDS,
            "segments": []
        }
        
        # 如果知道預估段數，可以預先創建佔位符
        if total_estimated_segments > 0:
            for i in range(1, total_estimated_segments + 1):
                start, end = _index_to_times(i)
                tr_data["segments"].append({
                    "index": i,
                    "start": start,
                    "end": end,
                    "text": PROCESSING_TEXT,
                    "summary": PROCESSING_SUMMARY,  # transcript 中暫時保留 summary 欄位
                    "volume": 0.0
                })
        
        _write_json(tr_path, tr_data)
    
    # summary.json 將在 overall 摘要完成後才創建
    return tr_path, sm_path


async def transcribe_with_whisper(chunk_path: Path, idx: int) -> Dict[str, Any]:
    """使用真實的 Whisper 模型進行轉錄"""
    start, end = _index_to_times(idx)
    
    # 檢查音量
    volume = check_audio_volume(chunk_path)
    print(f"📶 第 {idx:03d} 段音量: {volume:.4f}")
    
    if volume < VOLUME_THRESHOLD:
        print(f"🔇 第 {idx:03d} 段音量過低（<{VOLUME_THRESHOLD}），跳過轉錄")
        text = ""
    else:
        try:
            if whisper_app:
                print(f"🎧 開始轉錄第 {idx:03d} 段: {chunk_path.name}")
                text = whisper_app.transcribe(str(chunk_path))
                print(f"第 {idx:03d} 段轉錄結果: {text}")
            else:
                # 模擬模式
                text = f"（模擬）第 {idx:03d} 段的轉錄文字（{start:.1f}s ~ {end:.1f}s）。"
                
        except Exception as e:
            print(f"❌ 轉錄第 {idx:03d} 段失敗: {e}")
            text = f"轉錄失敗: {str(e)}"
    
    return {
        "index": idx,
        "start": start,
        "end": end,
        "text": text,
        "summary": PROCESSING_SUMMARY,  # 摘要稍後生成
        "volume": float(volume)
    }


async def generate_batch_summary(segments: List[Dict[str, Any]], batch_start_idx: int) -> str:
    """為一個批次（3段或剩餘段落）生成摘要"""
    if not kuwa_client:
        return f"（模擬）第 {batch_start_idx} ~ {batch_start_idx + len(segments) - 1} 段摘要"
    
    # 收集批次內的有效文字
    batch_texts = []
    for seg in segments:
        text = seg.get("text", "").strip()
        if text and text != PROCESSING_TEXT and not text.startswith("轉錄失敗") and not text.startswith("（模擬）"):
            batch_texts.append(text)
    
    if not batch_texts:
        return f"第 {batch_start_idx} ~ {batch_start_idx + len(segments) - 1} 段摘要（無有效內容）"
    
    try:
        combined_text = "\n".join(batch_texts)
        prompt = f"""請簡短摘要以下第 {batch_start_idx}-{batch_start_idx + len(segments) - 1} 段的內容（2-3句）：\n{combined_text}"""
        
        message = [{"role": "user", "content": prompt}]
        
        summary_result = ""
        print(f"📝 生成第 {batch_start_idx}-{batch_start_idx + len(segments) - 1} 段的批次摘要...")
        async for chunk in kuwa_client.chat_complete(messages=message, streaming=True):
            summary_result += chunk
            
        return f"第 {batch_start_idx} ~ {batch_start_idx + len(segments) - 1} 段摘要: {summary_result.strip()}"
        
    except Exception as e:
        print(f"❌ 批次摘要生成失敗: {e}")
        return f"第 {batch_start_idx} ~ {batch_start_idx + len(segments) - 1} 段摘要（生成失敗）"


async def generate_overall_summary(all_segments: List[Dict[str, Any]], base_name: str) -> str:
    """基於批次摘要代表段落生成整體摘要"""
    if not kuwa_client:
        return "（模擬）這是基於批次摘要生成的整體摘要。"
    
    # 找出每個批次的最後一段（包含完整批次摘要的段落）
    batch_summaries = []
    processed_indices = set()
    
    for seg in all_segments:
        idx = seg.get("index")
        summary = seg.get("summary", "")
        
        if (idx not in processed_indices and 
            summary and 
            summary != PROCESSING_SUMMARY and 
            summary.startswith("index ") and 
            "的摘要" in summary):
            
            # 解析摘要中的範圍，例如 "index 1 ~ 3 的摘要: ..."
            try:
                range_part = summary.split("的摘要")[0]  # "index 1 ~ 3"
                if "~" in range_part:
                    start_str, end_str = range_part.replace("index ", "").split(" ~ ")
                    start_idx = int(start_str.strip())
                    end_idx = int(end_str.strip())
                    
                    # 確保這是批次的最後一段
                    if idx == end_idx:
                        batch_summaries.append(summary)
                        # 標記這個範圍的所有index為已處理
                        for i in range(start_idx, end_idx + 1):
                            processed_indices.add(i)
            except:
                continue
    
    if not batch_summaries:
        # 回退方案：使用所有有效的轉錄文字
        all_text = []
        for seg in all_segments:
            text = seg.get("text", "").strip()
            if text and text != PROCESSING_TEXT and not text.startswith("轉錄失敗"):
                all_text.append(text)
        
        if not all_text:
            return "無有效內容可供摘要。"
        
        combined_text = "\n".join(all_text)
    else:
        combined_text = "\n".join(batch_summaries)
    
    try:
        prompt = """
你是專業記錄分析師，需要生成完整的會議或內容摘要。
規則：
1. 基於提供的分段摘要，生成完整的整體摘要
2. 摘要應包括：
   - 主要主題（1-2句）
   - 關鍵內容要點（條列式）
   - 重要結論或決議（如有）
3. 使用繁體中文
4. 保持簡潔但完整

請根據以下內容生成整體摘要：
        """
        
        message = [{"role": "user", "content": f"{prompt}\n{combined_text}"}]
        
        overall_summary = ""
        print(f"📋 生成 {base_name} 的整體摘要（基於 {len(batch_summaries)} 個批次摘要）...")
        async for chunk in kuwa_client.chat_complete(messages=message, streaming=True):
            overall_summary += chunk
            
        return overall_summary.strip()
        
    except Exception as e:
        print(f"❌ 整體摘要生成失敗: {e}")
        return f"摘要生成失敗: {str(e)}"


def _write_json(path: Path, data: Any):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _update_segment_in_json(tr_path: Path, segment: Dict[str, Any]):
    """更新單個段落到 transcript.json"""
    if tr_path.exists():
        tr_data = _read_json(tr_path)
    else:
        return
    
    segments = tr_data.get("segments", [])
    idx = segment["index"]
    
    # 找到對應的段落並更新
    for i, seg in enumerate(segments):
        if seg.get("index") == idx:
            segments[i] = segment
            break
    else:
        # 如果沒找到，添加新段落
        segments.append(segment)
        segments.sort(key=lambda x: x.get("index", 0))
    
    tr_data["segments"] = segments
    _write_json(tr_path, tr_data)


def _update_batch_summary_in_json(tr_path: Path, batch_segments: List[Dict[str, Any]], batch_summary: str):
    """更新整個批次的摘要到 transcript.json"""
    if tr_path.exists():
        tr_data = _read_json(tr_path)
    else:
        return
    
    segments = tr_data.get("segments", [])
    
    # 更新批次中所有段落的摘要
    for batch_seg in batch_segments:
        idx = batch_seg["index"]
        for i, seg in enumerate(segments):
            if seg.get("index") == idx:
                segments[i]["summary"] = batch_summary  # 直接套用批次摘要
    
    tr_data["segments"] = segments
    _write_json(tr_path, tr_data)


def _create_summary_json(folder: Path, all_segments: List[Dict[str, Any]], overall_summary: str):
    """創建新格式的 summary.json，在 overall 摘要完成後執行"""
    sm_path = folder / SUMMARY_JSON
    
    # 建立新格式的 summary.json
    sm_data = {
        "base_name": folder.name,
        "chunk_seconds": CHUNK_SECONDS,
        "overlap_seconds": OVERLAP_SECONDS,
        "per_segment": [],
        "overall_summary": overall_summary
    }
    
    # 為每個段落建立獨立的摘要記錄
    for seg in all_segments:
        idx = seg.get("index")
        summary = seg.get("summary", "")
        
        # 根據批次位置決定摘要內容
        if "處理中" in summary:
            # 如果還在處理中，保持處理中狀態
            segment_summary = summary
        elif summary.startswith("index ") and "的摘要" in summary:
            # 如果是批次摘要，分析這個段落在批次中的位置
            try:
                range_part = summary.split("的摘要")[0]  # "index 1 ~ 3"
                if "~" in range_part:
                    start_str, end_str = range_part.replace("index ", "").split(" ~ ")
                    start_idx = int(start_str.strip())
                    end_idx = int(end_str.strip())
                    
                    if start_idx <= idx <= end_idx:
                        segment_summary = summary
                        # if idx == end_idx:
                        #     # 批次的最後一段，顯示完整摘要
                        #     segment_summary = summary
                        # else:
                        #     # 批次中的其他段落，顯示處理中狀態
                        #     position = idx - start_idx + 1
                        #     total_in_batch = end_idx - start_idx + 1
                        #     segment_summary = f"處理中({position}/{total_in_batch})"
                    else:
                        segment_summary = summary
                else:
                    segment_summary = summary
            except:
                segment_summary = summary
        else:
            segment_summary = summary
        
        sm_data["per_segment"].append({
            "index": idx,
            "summary": segment_summary
        })
    
    # 按 index 排序
    sm_data["per_segment"].sort(key=lambda x: x.get("index", 0))
    
    _write_json(sm_path, sm_data)
    print(f"✅ 新格式 summary.json 已建立，包含 {len(sm_data['per_segment'])} 個段落摘要")


# ===== 串流模式輔助 =====
def _ensure_stream_dir(base_name: str) -> Path:
    folder = _ensure_folder(base_name)
    sdir = folder / STREAM_CHUNKS
    sdir.mkdir(parents=True, exist_ok=True)
    return sdir


def _stitch_stream_chunks_to_base(base_name: str) -> Path:
    """
    將 /uploads/<base>/stream_chunks/ 內的 001.wav,002.wav... 依序串接成 base.wav，
    並規一化為 16k/mono/16bit，最後輸出為 base.wav。
    """
    folder = _ensure_folder(base_name)
    chunk_dir = folder / STREAM_CHUNKS
    if not chunk_dir.exists():
        raise HTTPException(status_code=400, detail="No chunks uploaded")

    files = sorted(chunk_dir.glob("*.wav"))
    if not files:
        raise HTTPException(status_code=400, detail="No chunk files found")

    merged = AudioSegment.silent(duration=0)
    for p in files:
        merged += AudioSegment.from_wav(p.as_posix())

    # 規一化輸出 base.wav
    full_wav = folder / FULL_WAV
    merged = merged.set_frame_rate(TARGET_SR).set_channels(TARGET_CH).set_sample_width(TARGET_BITS // 8)
    merged.export(full_wav.as_posix(), format="wav")
    return full_wav


# ===============================
# 串流模式的全域狀態管理
# ===============================
stream_states = {}  # base_name -> {"pending_segments": [], "processed_count": 0}

def _get_stream_state(base_name: str) -> Dict[str, Any]:
    if base_name not in stream_states:
        stream_states[base_name] = {
            "pending_segments": [],
            "processed_count": 0
        }
    return stream_states[base_name]


@router.post("/transcribe")
async def transcribe(file: UploadFile = File(...)):
    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    orig_name = file.filename
    base_name = os.path.splitext(orig_name)[0]
    folder = _ensure_folder(base_name)

    # 1) 直接由 bytes 生成規一化完整 WAV（不存原始檔）
    full_wav = folder / FULL_WAV
    _canonicalize_bytes_to_wav16k_mono(contents, full_wav, os.path.splitext(orig_name)[1])

    # 2) 計算預估段數並初始化 JSON 檔案（只初始化 transcript.json）
    audio = AudioSegment.from_wav(full_wav.as_posix())
    total_ms = len(audio)
    step_ms = (CHUNK_SECONDS - OVERLAP_SECONDS) * 1000
    estimated_segments = max(1, math.ceil(total_ms / step_ms))
    
    tr_path, sm_path = _init_json_files(folder, estimated_segments)

    # 3) 創建臨時切片資料夾進行轉錄
    temp_chunks_dir = folder / "temp_chunks"
    temp_chunks_dir.mkdir(exist_ok=True)
    
    # 清空舊的臨時檔案
    for p in temp_chunks_dir.glob("*.wav"):
        try:
            p.unlink()
        except:
            pass

    # 4) 實際切片並轉錄，每3段做一次摘要
    chunk_ms = CHUNK_SECONDS * 1000
    segments = []
    pending_for_summary = []
    index = 1
    
    for start_ms in range(0, max(total_ms, 1), step_ms):
        if start_ms >= total_ms:
            break
            
        end_ms = start_ms + chunk_ms
        chunk = audio[start_ms:end_ms]
        chunk_path = temp_chunks_dir / f"{index:03d}.wav"
        chunk.export(chunk_path.as_posix(), format="wav")

        # 轉錄當前段落
        seg = await transcribe_with_whisper(chunk_path, index)

        # 設定明確的「處理中(位置/批次大小)」狀態，避免被通用 PROCESSING_SUMMARY 覆寫
        position_in_batch = ((index - 1) % SUMMARY_BATCH_SIZE) + 1
        seg["summary"] = f"處理中({position_in_batch}/{SUMMARY_BATCH_SIZE})"

        segments.append(seg)
        pending_for_summary.append(seg)

        # 立即更新到 transcript.json
        _update_segment_in_json(tr_path, seg)
        print(f"✅ 第 {index:03d} 段轉錄完成並已寫入（summary: {seg['summary']}）")
        
        # 每3段或最後一批，生成批次摘要
        if len(pending_for_summary) >= SUMMARY_BATCH_SIZE or (start_ms + chunk_ms >= total_ms):
            batch_start_idx = pending_for_summary[0]["index"]
            batch_end_idx = pending_for_summary[-1]["index"]
            
            # 生成批次摘要
            batch_summary_text = await generate_batch_summary(pending_for_summary, batch_start_idx)
            
            # 更新批次中所有段落的摘要
            _update_batch_summary_in_json(tr_path, pending_for_summary, batch_summary_text)
            print(f"✅ 第 {batch_start_idx}-{batch_end_idx} 段批次摘要完成並已寫入")
            
            # 清空待摘要列表
            pending_for_summary = []
        
        index += 1
        
        if start_ms + chunk_ms >= total_ms:
            break
    
    # 5) 生成整體摘要
    # ⚠️ 重點：重新讀取 transcript.json 取得最新的段落資料（含批次摘要）
    tr_data = _read_json(tr_path)
    segments = tr_data.get("segments", [])

    overall_summary = await generate_overall_summary(segments, base_name)

    # 6) 建立新格式的 summary.json（在 overall 摘要完成後）
    _create_summary_json(folder, segments, overall_summary)

    # 7) 清理臨時檔案
    try:
        import shutil
        shutil.rmtree(temp_chunks_dir, ignore_errors=True)
    except Exception:
        pass

    print(f"🎉 完整轉錄完成，共處理 {len(segments)} 個片段")

    return JSONResponse({
        "filename": f"{base_name}.wav",
        "base_name": base_name,
        "status": "ok",
        "total_segments": len(segments),
        "paths": {
            "audio_url":      f"/uploads/{base_name}/{FULL_WAV}",
            "transcript_url": f"/uploads/{base_name}/{TRANSCRIPT_JSON}",
            "summary_url":    f"/uploads/{base_name}/{SUMMARY_JSON}",
        }
    })


# ===============================
# 串流式：每段立即轉錄，每3段做一次摘要
# ===============================
@router.post("/ingest_chunk")
async def ingest_chunk(base_name: str = Query(...), index: int = Query(...), file: UploadFile = File(...)):
    folder = _ensure_folder(base_name)
    sdir = _ensure_stream_dir(base_name)
    contents = await file.read()
    out_wav = sdir / f"{index:03d}.wav"
    _canonicalize_bytes_to_wav16k_mono(contents, out_wav, os.path.splitext(file.filename)[1])

    # 初始化 JSON 檔案（如果是第一次，只初始化 transcript.json）
    if index == 1:
        _init_json_files(folder)

    # 取得串流狀態
    state = _get_stream_state(base_name)

    # 轉錄當前段落
    seg = await transcribe_with_whisper(out_wav, index)

    # 設定「處理中(位置/批次大小)」標記（避免被通用字串覆蓋）
    position_in_batch = ((index - 1) % SUMMARY_BATCH_SIZE) + 1
    seg["summary"] = f"處理中({position_in_batch}/{SUMMARY_BATCH_SIZE})"

    state["pending_segments"].append(seg)
    state["processed_count"] += 1

    # 檢查是否為批次的最後一段（每3段或最後一批）
    tr_path = folder / TRANSCRIPT_JSON
    
    if len(state["pending_segments"]) >= SUMMARY_BATCH_SIZE:
        # 批次滿了，處理摘要
        batch_segments = state["pending_segments"][:SUMMARY_BATCH_SIZE]
        state["pending_segments"] = state["pending_segments"][SUMMARY_BATCH_SIZE:]

        batch_start_idx = batch_segments[0]["index"]
        batch_end_idx = batch_segments[-1]["index"]

        # 生成批次摘要
        batch_summary_text = await generate_batch_summary(batch_segments, batch_start_idx)

        # 更新批次摘要到所有段落
        for batch_seg in batch_segments:
            batch_seg["summary"] = batch_summary_text

        # ***重點修正：批次完成後，才將轉錄和摘要一起寫入 JSON***
        for batch_seg in batch_segments:
            _update_segment_in_json(tr_path, batch_seg)
        
        print(f"✅ 串流第 {batch_start_idx}-{batch_end_idx} 段批次完成（轉錄+摘要一起寫入）")
    
    else:
        # ***批次未滿，僅寫入轉錄結果（摘要保持處理中狀態）***
        _update_segment_in_json(tr_path, seg)
        print(f"✅ 串流第 {index:03d} 段轉錄完成並已寫入（等待批次摘要）")

    return seg


# ===============================
# 串流完成：處理剩餘段落並生成最終摘要
# ===============================
@router.post("/finalize_stream")
async def finalize_stream(base_name: str):
    """
    停止錄音時呼叫：
    1. 處理剩餘未滿3段的內容
    2. 串接音訊檔案
    3. 生成最終整體摘要
    """
    folder = _ensure_folder(base_name)
    state = _get_stream_state(base_name)

    # 1) 處理剩餘的未滿3段的內容
    if state["pending_segments"]:
        batch_start_idx = state["pending_segments"][0]["index"]
        batch_end_idx = state["pending_segments"][-1]["index"]
        
        # 生成最後一批的摘要
        batch_summary_text = await generate_batch_summary(state["pending_segments"], batch_start_idx)
        
        # ***重點修正：更新摘要到段落物件中，然後一起寫入 JSON***
        for pending_seg in state["pending_segments"]:
            pending_seg["summary"] = batch_summary_text
        
        # 將轉錄和摘要一起寫入 JSON
        tr_path = folder / TRANSCRIPT_JSON
        for pending_seg in state["pending_segments"]:
            _update_segment_in_json(tr_path, pending_seg)
            
        print(f"✅ 最終批次第 {batch_start_idx}-{batch_end_idx} 段完成（轉錄+摘要一起寫入，共 {len(state['pending_segments'])} 段）")
        
        # 清空待處理列表
        state["pending_segments"] = []

    # 2) 串接音訊檔案
    try:
        full_wav = _stitch_stream_chunks_to_base(base_name)
        print(f"✅ 已完成音訊串接：{full_wav}")
    except Exception as e:
        print(f"⚠️ 音訊串接失敗: {e}")

    # 3) 讀取所有轉錄結果，生成最終整體摘要
    tr_path = folder / TRANSCRIPT_JSON
    
    if tr_path.exists():
        tr_data = _read_json(tr_path)
        segments = tr_data.get("segments", [])
        
        # 生成最終整體摘要
        overall_summary = await generate_overall_summary(segments, base_name)
        
        # 4) 建立新格式的 summary.json（在 overall 摘要完成後）
        _create_summary_json(folder, segments, overall_summary)
        
        print(f"✅ 最終整體摘要已生成並寫入新格式 summary.json")

    # 5) 清理串流狀態
    if base_name in stream_states:
        del stream_states[base_name]

    # 6) 清理：刪掉舊的 chunks/，保留 stream_chunks/
    try:
        import shutil
        shutil.rmtree((folder / CHUNK_DIRNAME), ignore_errors=True)
        print("🗑️ 清理舊的 chunks 資料夾")
    except Exception as e:
        print(f"清理時發生錯誤: {e}")

    print(f"🎉 串流轉錄完成，共處理 {state['processed_count']} 個片段")

    return JSONResponse({
        "filename": f"{base_name}.wav",
        "base_name": base_name,
        "status": "finalized",
        "total_segments": state["processed_count"],
        "paths": {
            "audio_url":      f"/uploads/{base_name}/{FULL_WAV}",
            "transcript_url": f"/uploads/{base_name}/{TRANSCRIPT_JSON}",
            "summary_url":    f"/uploads/{base_name}/{SUMMARY_JSON}",
        }
    })


# ===============================
# 查詢介面
# ===============================
@router.get("/segment_at")
async def segment_at(base_name: str = Query(...), t: float = Query(..., ge=0.0)):
    """依時間點 t（秒）回傳該段的轉錄與摘要。"""
    folder = _ensure_folder(base_name)
    tr_path = folder / TRANSCRIPT_JSON
    if not tr_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found. Please transcribe first.")

    tr = _read_json(tr_path)
    segs: List[Dict[str, Any]] = tr.get("segments", [])
    total_seconds = segs[-1]["end"] if segs else 0.0
    idx = _time_to_index(t, total_seconds)

    if 1 <= idx <= len(segs):
        return segs[idx - 1]
    else:
        raise HTTPException(status_code=404, detail="Time out of transcript range")


@router.get("/segments_in_range")
async def segments_in_range(
    base_name: str = Query(...),
    start: float = Query(..., ge=0.0),
    end: float = Query(..., gt=0.0)
):
    """依時間範圍 [start, end) 回傳覆蓋到的所有段落（已含重疊）。"""
    if end <= start:
        raise HTTPException(status_code=400, detail="end must be greater than start")

    folder = _ensure_folder(base_name)
    tr_path = folder / TRANSCRIPT_JSON
    if not tr_path.exists():
        raise HTTPException(status_code=404, detail="Transcript not found. Please transcribe first.")

    tr = _read_json(tr_path)
    segs: List[Dict[str, Any]] = tr.get("segments", [])

    hit: List[Dict[str, Any]] = []
    for s in segs:
        s0, s1 = float(s["start"]), float(s["end"])
        if not (s1 <= start or s0 >= end):
            hit.append(s)

    return {"base_name": base_name, "range": [start, end], "segments": hit}


@router.get("/summary")
async def get_summary(base_name: str = Query(...)):
    """取回整體摘要（以及可選的逐段摘要）。"""
    folder = _ensure_folder(base_name)
    sp = folder / SUMMARY_JSON
    if not sp.exists():
        raise HTTPException(status_code=404, detail="Summary not found. Please transcribe first.")
    return _read_json(sp)


@router.get("/status")
async def get_status(base_name: str = Query(...)):
    """取得轉錄和摘要的進度狀態"""
    folder = _ensure_folder(base_name)
    tr_path = folder / TRANSCRIPT_JSON
    sm_path = folder / SUMMARY_JSON
    
    status_info = {
        "base_name": base_name,
        "transcript_exists": tr_path.exists(),
        "summary_exists": sm_path.exists(),
        "total_segments": 0,
        "completed_transcripts": 0,
        "processing_summaries": 0,
        "completed_summaries": 0
    }
    
    if tr_path.exists():
        tr_data = _read_json(tr_path)
        segments = tr_data.get("segments", [])
        status_info["total_segments"] = len(segments)
        
        # 計算完成的轉錄和摘要數量
        completed_transcripts = 0
        processing_summaries = 0
        completed_summaries = 0
        
        for seg in segments:
            text = seg.get("text", "")
            summary = seg.get("summary", "")
            
            # 計算轉錄完成數
            if text and text != PROCESSING_TEXT:
                completed_transcripts += 1
            
            # 計算摘要狀態
            if "處理中" in summary:
                processing_summaries += 1
            elif "index " in summary and "的摘要" in summary:
                completed_summaries += 1
        
        status_info["completed_transcripts"] = completed_transcripts
        status_info["processing_summaries"] = processing_summaries
        status_info["completed_summaries"] = completed_summaries
    
    return status_info


@router.get("/model_status")
async def model_status():
    """檢查 AI 模型狀態"""
    return {
        "whisper_loaded": whisper_app is not None,
        "kuwa_client_ready": kuwa_client is not None,
        "status": "ready" if (whisper_app and kuwa_client) else "partial" if (whisper_app or kuwa_client) else "simulation_mode",
        "summary_batch_size": SUMMARY_BATCH_SIZE,
        "chunk_seconds": CHUNK_SECONDS,
        "overlap_seconds": OVERLAP_SECONDS
    }


# ===============================
# 重新處理摘要的輔助端點（可選）
# ===============================
@router.post("/regenerate_summaries")
async def regenerate_summaries(base_name: str = Query(...)):
    """重新生成所有摘要（基於現有的轉錄結果）"""
    folder = _ensure_folder(base_name)
    tr_path = folder / TRANSCRIPT_JSON
    
    if not tr_path.exists():
        raise HTTPException(status_code=404, detail="No transcript found")
    
    tr_data = _read_json(tr_path)
    segments = tr_data.get("segments", [])
    
    if not segments:
        raise HTTPException(status_code=400, detail="No segments found")
    
    # 重新生成批次摘要
    for i in range(0, len(segments), SUMMARY_BATCH_SIZE):
        batch_segments = segments[i:i + SUMMARY_BATCH_SIZE]
        batch_start_idx = batch_segments[0]["index"]
        
        # 生成批次摘要
        batch_summary_text = await generate_batch_summary(batch_segments, batch_start_idx)
        
        # 更新批次中所有段落的摘要
        _update_batch_summary_in_json(tr_path, batch_segments, batch_summary_text)
    
    # 重新讀取更新後的資料
    tr_data = _read_json(tr_path)
    updated_segments = tr_data.get("segments", [])
    
    # 生成整體摘要
    overall_summary = await generate_overall_summary(updated_segments, base_name)
    
    # 建立新格式的 summary.json
    _create_summary_json(folder, updated_segments, overall_summary)
    
    return JSONResponse({
        "base_name": base_name,
        "status": "regenerated",
        "total_segments": len(segments)
    })