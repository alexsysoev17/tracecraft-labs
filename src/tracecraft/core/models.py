"""Versioned, strict contracts. Source text is data, never execution authority."""
from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field

Mode = Literal['fixture', 'local', 'live', 'replay']

class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Scope(Contract):
    tenant: str = 'demo'
    project: str = 'public-lab'
    brand: str = 'luma'
    snapshot: str = 'v2'
    principal: str = 'demo-reader'
    permissions: list[str] = Field(default_factory=lambda: ['public'])
    locale: str = 'ru'
    context: str = ''
    acl_version: str = '1'

class SourceDocument(Contract):
    id: str
    brand: str
    version: str
    path: str
    sha256: str
    data_origin: str
    ingestion_status: str = 'ready'
    metadata: dict[str, Any] = Field(default_factory=dict)

class EvidenceChunk(Contract):
    id: str
    document_id: str
    brand: str
    snapshot: str = 'v2'
    title: str
    text: str
    section: str
    source_hash: str
    data_origin: str = 'synthetic'
    tenant: str = 'demo'
    permissions: list[str] = Field(default_factory=lambda: ['public'])
    status: Literal['reviewed', 'unreviewed', 'superseded'] = 'reviewed'
    authority: Literal['explicit', 'observed', 'inferred'] = 'explicit'
    polarity: Literal['positive', 'negative', 'neutral', 'mixed', 'unknown'] = 'neutral'
    kind: str = 'rule'
    mandatory: bool = False
    topic: str = ''
    rule_key: str = ''
    value: str = ''
    links: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    start: int = 0
    end: int = 0

class BrandRule(EvidenceChunk):
    kind: str = 'rule'

class RetrievalHit(Contract):
    evidence: EvidenceChunk
    score: float
    rank: int
    ranks: dict[str, int] = Field(default_factory=dict)

class RetrievalResult(Contract):
    query: str
    method: str
    status: str = 'ready'
    hits: list[RetrievalHit] = Field(default_factory=list)
    required: list[EvidenceChunk] = Field(default_factory=list)
    context: list[EvidenceChunk] = Field(default_factory=list)
    latency_ms: float = 0
    mode: Mode = 'fixture'
    embedding_model: str | None = None
    reason: str | None = None

class Claim(Contract):
    text: str
    evidence_id: str
    quote: str

class Usage(Contract):
    calls: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None

class Answer(Contract):
    status: Literal['supported', 'insufficient_evidence', 'conflict', 'needs_review']
    text: str
    evidence_ids: list[str] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    retrieval: RetrievalResult | None = None
    mode: Mode = 'fixture'
    data_origin: str = 'synthetic'
    measurement_status: str = 'measured'
    review_status: str = 'machine_checked'
    generation_kind: str = 'extractive'
    latency_ms: float = 0
    usage: Usage = Field(default_factory=Usage)
    run_id: str = ''

class RunManifest(Contract):
    schema_version: str = 'tracecraft.run/1'
    id: str
    module: str
    mode: Mode
    data_origin: str = 'synthetic'
    measurement_status: str = 'running'
    review_status: str = 'not_human_reviewed'
    config: dict[str, Any]
    config_hash: str
    code_revision: str | None
    dirty_tree: bool | None
    code_source_hash: str | None = None
    started_at: str
    finished_at: str | None = None
    status: str = 'running'
    usage: Usage = Field(default_factory=Usage)

class TraceSpan(Contract):
    schema_version: str = 'tracecraft.span/1'
    id: str
    run_id: str
    parent_id: str | None = None
    timestamp: str
    stage: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    status: str = 'ok'
    error: str | None = None
    data_origin: str = 'synthetic'

class ToolCall(Contract):
    name: Literal['search_rules','read_evidence','validate_requirements','request_clarification','draft_handoff','request_review']
    arguments: dict[str, Any]
    idempotency_key: str

class Artifact(Contract):
    id: str
    run_id: str
    name: str
    content: str
    sha256: str
    media_type: str

class Approval(Contract):
    run_id: str
    artifact_hash: str
    input_hash: str
    decision: Literal['approved','rejected']
    reviewer: str = 'local-human'

class EvalCase(Contract):
    id: str
    family: str
    split: Literal['development','validation','test']
    category: str
    query: str
    brand: str = 'luma'
    snapshot: str = 'v2'
    locale: str = 'ru'
    expected_status: str
    evidence_ids: list[str] = Field(default_factory=list)
    allowed_claims: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    severity: str = 'normal'
    review_status: str = 'machine_authored'
    gold_spans: list[dict[str, Any]] = Field(default_factory=list)

class EvalResult(Contract):
    case_id: str
    passed: bool | None
    checks: dict[str, Any]
    answer: dict[str, Any]
    latency_ms: float
    error: str | None = None

class CacheEntry(Contract):
    id: str
    query: str
    namespace: str
    created_at: float
    expires_at: float
    answer: Answer
    dependencies: dict[str, str]
    vector: list[float] | None = None
    embedding_model: str | None = None
