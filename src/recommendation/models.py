from pydantic import BaseModel


class RecommendationItem(BaseModel):
    short_text: str
    max_score: float
    providers: list[str]
    detail: str | None = None
    personal_relevance_score: float | None = None
    anomaly_suppressed: bool = False


class RecommendationResponse(BaseModel):
    device_id: str
    trace_id: str
    recommendations: list[RecommendationItem]
    providers_called: list[str]
    providers_succeeded: list[str]
    duration_ms: int
    credits_remaining: int
    reward_tier: str


class InsufficientCreditsError(BaseModel):
    detail: str = "Insufficient credits"
    device_id: str
    credit_balance: int


class AllProvidersFailedResponse(BaseModel):
    detail: str = "All recommendation providers failed or timed out"
    trace_id: str
    providers_attempted: list[str]
    duration_ms: int
