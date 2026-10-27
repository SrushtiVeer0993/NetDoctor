from datetime import datetime

from pydantic import BaseModel, Field


class DiagnosisRequest(BaseModel):
    external_host: str = "8.8.8.8"
    dns_domain: str = "google.com"
    websites: list[str] = Field(default_factory=list)
    discover_devices: bool = False


class DiagnosisSummary(BaseModel):
    id: int
    created_at: datetime
    health_score: int
    gateway_reachable: bool | None
    internet_reachable: bool | None
    latency_avg_ms: float | None = None
    packet_loss_pct: float | None = None
    dns_response_ms: float | None = None
    top_finding: str | None = None

    class Config:
        from_attributes = True


class DiagnosisResult(DiagnosisSummary):
    result_json: dict
