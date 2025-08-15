# EdgeMeet (Under develop)

This app(EdgeMeet) is provided as an offline AI meeting assistant sample, built using fine-tuned Whisper speech-to-text (ASR) and Llama 3.1 TAIDE summarization models. The application runs fully on-device, ensuring no cloud transmission and complete control over sensitive meeting data.

On Snapdragon X Elite, the models are optimized to leverage the Neural Processing Unit (NPU) for low-latency inference. The ASR supports multiple languages, including Chinese, English, and Taiwanese Hokkien, delivering accurate transcriptions and concise summaries in real time. Elsewhere, the models will run on the CPU.

This project was developed for the Qualcomm Edge AI Developer Hackathon.

---
## Preview

![EdgeMeet Preview](public/images/preview.png)

---
## 目錄

- [功能特色](#功能特色)
- [專案結構](#專案結構)
- [快速開始](#快速開始)
- [後端-api](#後端-api)
- [資料格式](#資料格式)
- [前端關鍵檔案與流程](#前端關鍵檔案與流程)
- [設定](#設定)

---

## 功能特色

- 🎙️ **錄音（NAudio）**：裝置選擇、開始/停止、播放、拖曳跳段、播放進度同步  
- ⚡ **即時上傳**：每 20s 上傳一次（與前段 **2s overlap**）  
- 🧩 **即時摘要**：上傳成功後 **延遲 1 秒** 讀取 `/summary`，只取 `per_segment` **最大 index** 為當前段摘要  
- 🧾 **完整輸出**：停止錄音 → 串接 `stream_chunks/` 得 `base.wav` → **記憶體切段** → 覆蓋 `transcript.json` / `summary.json`  
- 🧠 **智慧摘要顯示**：錄音/播放中顯示「本段摘要」，其他時候顯示「整體摘要」

---

## 專案結構

### 前端（WinUI 3）

```text
ConferenceAssistant/
├─ Assets/
├─ Controls/
│  └─ RecordingStatusControl.xaml(.cs)
├─ Converters/
│  └─ ValueConverters.cs
├─ Models/
│  ├─ ConferenceRecordDto.cs
│  └─ IndexedSample.cs
├─ ViewModels/
│  ├─ MainViewModel.cs
│  └─ MainViewModel.Streaming.cs
├─ App.xaml(.cs)
└─ MainWindow.xaml(.cs)
```

### 後端（FastAPI）

```text
app/
├─ main.py # FastAPI app 入口
├─ routes.py # /uploads 靜態、範例路由
├─ schemas.py # Pydantic 模型
└─ transcribe.py # 轉錄/摘要 API（ingest_chunk / finalize_stream / summary ...）

uploads/ # 執行後產物（每個錄音 base 一個資料夾）
└─ <base_name>/
├─ base.wav
├─ transcript.json
├─ summary.json
└─ stream_chunks/ # 001.wav, 002.wav, ...（保留）
```
---

## 快速開始

### 後端
Pre.
請先依照網站指示安裝 Turu for Qualcomm AI Hackathon
https://turu.thuniverse.ai/download/turu-25h1-wos/

1. 建立虛擬環境並安裝依賴 (Python 3.10.8)
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   pip install -r requirements.txt   # fastapi uvicorn pydub python-multipart 等
   ```
2. 安裝 ffmpeg 並確保在 PATH（pydub 需要）。

3. 打開 Turu 平台

4. 啟動後端
    ```bash
   uvicorn app.main:app --reload
   ```
### 前端

- 使用 Visual Studio 2022（含 .NET 8、Windows App SDK/WinUI 3 工作負載）開啟 ConferenceAssistant，F5 執行。

- 依程式設定，預設呼叫 http://127.0.0.1:8000 後端。

---

## 後端-api


| Method & Path            | 說明                                                                 | 參數（Query / Body）                                                                 | 回傳（摘要）                                                          |
|--------------------------|----------------------------------------------------------------------|--------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| **POST** `/ingest_chunk` | 上傳一段 20s WAV、即時 upsert 該段到 JSON                            | Query：`base_name`, `index` ；Body：`multipart/form-data` 欄位 `file`               | `{ index, start, end, text, summary }`                                |
| **POST** `/finalize_stream` | 停止錄音：串接 `stream_chunks/` → `base.wav` → 記憶體切段 → 覆蓋 JSON | Query：`base_name`                                                                   | `{ filename, base_name, status, paths }`                              |
| **GET** `/summary`       | 取得整體摘要與每段摘要                                               | Query：`base_name`                                                                   | `{ overall_summary, per_segment: [{ index, summary }], ... }`         |
| **GET** `/segment_at`    | 取得時間點所屬段落                                                   | Query：`base_name`, `t`                                                              | `{ index, start, end, text, summary }`                                |
| **GET** `/segments_in_range` | 取得區間內所有段落                                               | Query：`base_name`, `start`, `end`                                                   | `{ range, segments: [...] }`                                          |


---

## 資料格式

### `transcript.json`

```json
{
  "base_name": "recording_20250814_015628",
  "chunk_seconds": 20,
  "overlap_seconds": 2,
  "segments": [
    { "index": 1, "start": 0,  "end": 20, "text": "..." },
    { "index": 2, "start": 18, "end": 38, "text": "..." }
  ]
}
```

###summary.json
```json
{
  "base_name": "recording_20250814_015628",
  "overall_summary": "...",
  "chunk_seconds": 20,
  "overlap_seconds": 2,
  "per_segment": [
    { "index": 1, "summary": "..." },
    { "index": 2, "summary": "..." }
  ]
}
```
---

## 前端關鍵檔案與流程

### 重要檔案

- **`ViewModels/MainViewModel.cs`**  
  核心狀態、播放/跳段、`SmartSummary` 計算、呼叫 `/summary`、`/segment_at`，停止錄音後觸發 `finalize_stream`。

- **`ViewModels/MainViewModel.Streaming.cs`**  
  即時上傳：每湊滿 **20s** 的原始 bytes → 以 `WaveFileWriter` 包成 WAV → `POST /ingest_chunk`。  
  上傳後立即顯示該段**轉錄**；**1 秒後**呼叫 `/summary`，只取 `per_segment` 的**最大 `index`** 進行更新：
  - `CurrentSegmentSummary`（右側摘要卡）
  - `SegmentSummaries`（清單；Upsert；維持排序）  
  所有 UI 更新透過 `_dispatcherQueue.TryEnqueue(...)` 進行。

- **`Controls/RecordingStatusControl.xaml(.cs)`**  
  錄音狀態視覺元件：樣式切換、動畫與狀態文字。

- **`Models/ConferenceRecordDto.cs`**  
  後端 API 對應模型（`ApiSegment`、`ApiSummary` 等）與清單項目 `SegmentSummaryItem`。
  
### 即時流程（圖）

```text
flowchart LR
  A[NAudio 錄音] -->|20s/段, 2s overlap| B[封裝 WAV (WaveFileWriter)]
  B --> C[POST /ingest_chunk]
  C -->|即時 upsert| D[transcript.json & summary.json]
  C -->|回 segment| E[UI 立即顯示本段轉錄]
  E --> F[延遲 1 秒 GET /summary]
  F -->|per_segment 最大 index| G[CurrentSegmentSummary & SegmentSummaries]
  A -->|停止| H[POST /finalize_stream]
  H -->|stream_chunks → base.wav → 記憶體切段| D
```
---
## 設定

- 片段規格：`CHUNK_SECONDS = 20`、`OVERLAP_SECONDS = 2`（前後端需一致）
- 音訊規格：`base.wav` 統一為 `16 kHz / mono / 16-bit PCM`
- 上傳資料夾：`uploads/<base_name>/`
- 環境檔：可於 `.env` 或程式碼調整主機/連接埠/路徑

---
## License
[Apache License](LICENSE)