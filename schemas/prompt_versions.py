from pydantic import BaseModel, Field

from schemas.schemas import RequiredPromptText


class PromptChainCreate(BaseModel):
    project: RequiredPromptText
    name: RequiredPromptText
    description: str | None = None
    content: RequiredPromptText
    notes: str | None = None


class PromptChainVersionCreate(BaseModel):
    content: RequiredPromptText
    notes: str | None = None


class PromptChainOut(BaseModel):
    id: int
    project: str
    name: str
    description: str | None = None
    created_at: str
    updated_at: str
    created_by_username: str
    updated_by_username: str


class PromptChainVersionOut(BaseModel):
    id: int
    chain_id: int
    version_no: int
    content: str
    notes: str | None = None
    created_at: str
    created_by_username: str


class PromptVersionMetricsOut(BaseModel):
    version_no: int
    tokens: int
    reliability: float
    cache_hit_probability: float
    injection_risk: float = 0.0
    contradiction_risk: float = 0.0
    ambiguity_risk: float = 0.0
    delta_tokens: int = 0
    delta_reliability: float = 0.0
    delta_cache_hit: float = 0.0
    delta_injection_risk: float = 0.0
    delta_contradiction_risk: float = 0.0
    delta_ambiguity_risk: float = 0.0


class PromptChainAnalysisSummaryOut(BaseModel):
    versions: int
    average_tokens: float
    average_reliability: float
    average_cache_hit_probability: float
    average_injection_risk: float = 0.0
    average_contradiction_risk: float = 0.0
    average_ambiguity_risk: float = 0.0
    trend_tokens: int
    trend_reliability: float
    trend_cache_hit_probability: float
    trend_injection_risk: float = 0.0
    trend_contradiction_risk: float = 0.0
    trend_ambiguity_risk: float = 0.0


class PromptChainAnalysisOut(BaseModel):
    chain_id: int
    chain_name: str
    summary: PromptChainAnalysisSummaryOut
    points: list[PromptVersionMetricsOut] = Field(default_factory=list)


class PromptVersionAnalysisOut(BaseModel):
    chain_id: int
    chain_name: str
    version_no: int
    tokens: int
    reliability: float
    cache_hit_probability: float
    injection_risk: float = 0.0
    contradiction_risk: float = 0.0
    ambiguity_risk: float = 0.0
    security_markers: list[str] = Field(default_factory=list)


class PromptOrchestratorPreviewOut(BaseModel):
    chain_id: int
    chain_name: str
    version_no: int
    source_prompt: str
    retrieved_context: list[str] = Field(default_factory=list)
    analysis: PromptVersionAnalysisOut
    recommendations: list[str] = Field(default_factory=list)
    improved_prompt: str
    generated_at: str
    log_path: str
    log_text: str


class PromptTestRunLlmConfigOut(BaseModel):
    provider: str
    model: str
    backend: str
    base_url: str | None = None
    llm_invoked: bool = False


class PromptTestRunTokenUsageOut(BaseModel):
    prompt_tokens: int
    completion_tokens: int = 0
    total_tokens: int


class PromptTestRunSecurityOut(BaseModel):
    injection_risk: float
    contradiction_risk: float
    ambiguity_risk: float
    markers: list[str] = Field(default_factory=list)


class PromptTestRunRagOut(BaseModel):
    enabled: bool = False
    source_path: str | None = None
    top_k: int = 0
    chunks: list[str] = Field(default_factory=list)


class PromptTestRunOut(BaseModel):
    id: str
    created_at: str
    chain_id: int
    chain_name: str
    version_no: int
    actor_username: str | None = None
    full_prompt: str
    fixed_part: str
    semi_fixed_part: str
    variable_part: str
    variables: list[str] = Field(default_factory=list)
    reliability: float
    cache_hit_probability: float
    latency_ms: float
    llm: PromptTestRunLlmConfigOut
    llm_error: str = ""
    llm_response: str = ""
    prompt_with_rag: str = ""
    rag: PromptTestRunRagOut
    security: PromptTestRunSecurityOut
    token_usage: PromptTestRunTokenUsageOut
