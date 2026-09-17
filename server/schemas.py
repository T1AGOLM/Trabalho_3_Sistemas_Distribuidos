"""Esquemas Pydantic (contrato da API)."""
from __future__ import annotations

from pydantic import BaseModel


class AudioOut(BaseModel):
    id: str
    original_name: str
    original_ext: str
    mime_type: str
    size_bytes: int
    duration_sec: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bitrate: int | None = None
    processing_type: str
    created_at: str | None = None
    path_original: str | None = None
    path_processed: str | None = None

    @classmethod
    def from_row(cls, row) -> "AudioOut":
        d = row.to_dict() if hasattr(row, "to_dict") else dict(row)
        return cls(**d)
