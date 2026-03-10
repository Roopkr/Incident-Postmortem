from pydantic import BaseModel, ConfigDict, Field


class IncidentUnderstandingDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_time: str = Field(..., description="Incident start timestamp in ISO format")
    impacted_services: list[str] = Field(default_factory=list)
    severity: str = Field(..., description="Incident severity, e.g. SEV-1")


class TimelineEventDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: str
    event_type: str
    details: str


class HypothesisDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cause: str
    rationale: str
    supporting_timestamps: list[str] = Field(default_factory=list)


class HypothesisListDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hypotheses: list[HypothesisDTO] = Field(min_length=2, max_length=3)


class EvidenceEvaluationDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_root_cause: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_timestamps: list[str] = Field(default_factory=list)
    reasoning: str


class PostmortemReportDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executive_summary: str
    impact: str
    timeline: list[str] = Field(default_factory=list)
    root_cause: str
    action_items: list[str] = Field(default_factory=list)
    confidence_score: float = Field(ge=0.0, le=1.0)
    uncertainty: str = ""
