from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TranscriptSegment(BaseModel):
    timestamp: int  # 秒數整數
    text: str
    speaker: str

class ConferenceRecord(BaseModel):
    id: str
    title: str
    date: datetime
    duration: float  # 秒數
    file_path: str
    summary: str
    is_transcribed: bool
    transcript_segments: List[TranscriptSegment]

    summary_url: Optional[str] = None
    transcript_url: Optional[str] = None
