from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TranscriptSegment(BaseModel):
    timestamp: int  # ��ƾ��
    text: str
    speaker: str

class ConferenceRecord(BaseModel):
    id: str
    title: str
    date: datetime
    duration: float  # ���
    file_path: str
    summary: str
    is_transcribed: bool
    transcript_segments: List[TranscriptSegment]

    summary_url: Optional[str] = None
    transcript_url: Optional[str] = None
