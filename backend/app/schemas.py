from pydantic import BaseModel


class RecordingCompleteResponse(BaseModel):
    session_id: str
    recording_path: str
    saved: bool


class JobStatusResponse(BaseModel):
    status: str
    message: str | None = None
    current_file: str | None = None
    processed: int = 0
    total: int = 0
    done: bool = False
