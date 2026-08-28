from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class MutationRequestModel(ContractModel):
    model_config = ConfigDict(extra="forbid")


class ApiError(ContractModel):
    error_code: str = Field(validation_alias=AliasChoices("error_code", "code"))
    error_message: str = Field(validation_alias=AliasChoices("error_message", "message"))
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ApiMeta(ContractModel):
    page: str | None = None
    selected_date: str | None = None
    generated_at: str | None = None
    version: str = "v1"


class ApiEnvelope(ContractModel):
    ok: bool = True
    data: Any = None
    error: ApiError | None = None
    meta: ApiMeta = Field(default_factory=ApiMeta)


class MetricDto(ContractModel):
    title: str = ""
    value: str = ""
    body: str = ""
    tone: str = "neutral"


class ShellPageDto(ContractModel):
    dates: list[str] = Field(default_factory=list)
    selectedDate: str = ""
    chainStatus: str = ""
    statusBadgeState: str = "idle"
    statusBarText: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)


class TodayPageDto(ContractModel):
    selectedDate: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    todayAnalysis: dict[str, Any] = Field(default_factory=dict)
    dashboard: dict[str, Any] = Field(default_factory=dict)
    research: dict[str, Any] = Field(default_factory=dict)
    dailyFirstOpen: dict[str, Any] = Field(default_factory=dict)
    portfolio: dict[str, Any] = Field(default_factory=dict)
    longMemory: dict[str, Any] = Field(default_factory=dict)
    system: dict[str, Any] = Field(default_factory=dict)


class PortfolioPageDto(ContractModel):
    selectedDate: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    portfolio: dict[str, Any] = Field(default_factory=dict)


class ExecutionPageDto(ContractModel):
    selectedDate: str = ""
    executionSync: dict[str, Any] = Field(default_factory=dict)
    portfolio: dict[str, Any] = Field(default_factory=dict)
    system: dict[str, Any] = Field(default_factory=dict)


class ResearchPageDto(ContractModel):
    selectedDate: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    research: dict[str, Any] = Field(default_factory=dict)


class IntelligencePageDto(ContractModel):
    selectedDate: str = ""
    intelligence: dict[str, Any] = Field(default_factory=dict)


class RealtimePageDto(ContractModel):
    selectedDate: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    realtime: dict[str, Any] = Field(default_factory=dict)


class ReviewPageDto(ContractModel):
    selectedDate: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    review: dict[str, Any] = Field(default_factory=dict)
    longMemory: dict[str, Any] = Field(default_factory=dict)


class ShadowReviewMissingArtifactDto(ContractModel):
    kind: str = ""
    path: str | None = None
    reason: str = ""
    message: str = ""


class ShadowReviewArtifactsDto(ContractModel):
    legacyAdvicePath: str | None = None
    shadowAdvicePath: str | None = None
    shadowTracePath: str | None = None
    evalReportPath: str | None = None
    exists: dict[str, bool] = Field(default_factory=dict)
    missing: list[ShadowReviewMissingArtifactDto] = Field(default_factory=list)


class ShadowReviewItemDto(ContractModel):
    reviewId: str = ""
    fundCode: str = ""
    fundName: str = ""
    category: str = "missing"
    severity: str = "info"
    displayLabel: str = ""
    nonExecutable: Literal[True] = True
    displayOnly: Literal[True] = True
    legacy: dict[str, Any] | None = None
    shadow: dict[str, Any] | None = None
    diff: dict[str, Any] = Field(default_factory=dict)
    display: dict[str, Any] = Field(default_factory=dict)


class ShadowReviewGuardrailsDto(ContractModel):
    nonExecutable: Literal[True] = True
    executionDisabled: Literal[True] = True
    affectsPortfolio: Literal[False] = False
    affectsAdviceAccuracy: Literal[False] = False
    affectsLongMemoryPromotion: Literal[False] = False
    allowExecutionEvidence: Literal[False] = False
    displayOnly: Literal[True] = True


class ShadowReviewPageDto(ContractModel):
    selectedDate: str = ""
    status: str = "missing"
    generatedAt: str = ""
    nonExecutable: Literal[True] = True
    displayOnly: Literal[True] = True
    summary: dict[str, Any] = Field(default_factory=dict)
    artifacts: ShadowReviewArtifactsDto = Field(default_factory=ShadowReviewArtifactsDto)
    items: list[ShadowReviewItemDto] = Field(default_factory=list)
    runtime: dict[str, Any] = Field(default_factory=dict)
    guardrails: ShadowReviewGuardrailsDto = Field(default_factory=ShadowReviewGuardrailsDto)


class SystemPageDto(ContractModel):
    selectedDate: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    system: dict[str, Any] = Field(default_factory=dict)
    shell: dict[str, Any] = Field(default_factory=dict)


class FundDetailDto(ContractModel):
    fundCode: str = ""
    fundName: str = ""
    selectedDate: str = ""
    range: str = ""
    portfolio: dict[str, Any] = Field(default_factory=dict)
    realtime: dict[str, Any] = Field(default_factory=dict)
    research: dict[str, Any] = Field(default_factory=dict)
    analysisDetail: dict[str, Any] = Field(default_factory=dict)
    history: dict[str, Any] = Field(default_factory=dict)
    performance: dict[str, Any] = Field(default_factory=dict)
    tradeMarkers: list[dict[str, Any]] = Field(default_factory=list)
    longMemory: dict[str, Any] = Field(default_factory=dict)
    system: dict[str, Any] = Field(default_factory=dict)


class ExecutionTradeRequestDto(MutationRequestModel):
    trade_id: str | None = None
    trade_date: str | None = None
    trade_time: str | None = None
    fund_code: str = ""
    fund_name: str = ""
    operation_type: str = ""
    amount: float | int | str | None = None
    units: float | int | str | None = None
    nav: float | int | str | None = None
    fee: float | int | str | None = None
    status: str | None = None
    confirm_date: str | None = None
    settlement_date: str | None = None
    linked_suggestion_id: str | None = None
    linked_advice_date: str | None = None
    source: str | None = None
    platform: str | None = None
    user_note: str | None = None


class ExecutionConversionRequestDto(MutationRequestModel):
    conversion_id: str | None = None
    trade_date: str | None = None
    trade_time: str | None = None
    out_fund_code: str = ""
    out_fund_name: str = ""
    out_amount: float | int | str | None = None
    out_units: float | int | str | None = None
    out_nav: float | int | str | None = None
    in_fund_code: str = ""
    in_fund_name: str = ""
    in_amount: float | int | str | None = None
    in_units: float | int | str | None = None
    in_nav: float | int | str | None = None
    fee: float | int | str | None = None
    status: str | None = None
    linked_suggestion_id: str | None = None
    linked_advice_date: str | None = None
    source: str | None = None
    platform: str | None = None
    user_note: str | None = None


class ScreenshotFileDto(MutationRequestModel):
    name: str = Field(default="screenshot.png", min_length=1, max_length=255)
    data: str = Field(min_length=1)


class ExecutionScreenshotParseRequestDto(MutationRequestModel):
    import_id: str | None = Field(default=None, max_length=80)
    snapshot_date: str | None = None
    auto_parse: bool = True
    files: list[ScreenshotFileDto] = Field(min_length=1, max_length=4)


class ExecutionReconcileApplyRequestDto(MutationRequestModel):
    reconcileId: str = Field(min_length=1, max_length=80)
    previewSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expectedPortfolioStateSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    dropMissing: bool = False
    confirmReplace: str | None = None


class ExecutionFundLookupRequestDto(MutationRequestModel):
    name: str = Field(min_length=1, max_length=120)


class ExecutionFundRegisterRequestDto(MutationRequestModel):
    reconcileId: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    expectedPreviewSha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    displayName: str = Field(min_length=1, max_length=120)
    fundCode: str = Field(pattern=r"^\d{6}$")
    userConfirmed: Literal[True]


class RunTaskRequestDto(MutationRequestModel):
    date: str | None = None
    runDate: str | None = None
    force: bool = False
    automatic: bool = False


class LongMemoryActionRequestDto(MutationRequestModel):
    memoryId: str = Field(min_length=1)
    action: Literal["approve", "reject", "archive", "demote"]
    note: str = ""


class ExecutionReconcilePreviewRequestDto(MutationRequestModel):
    items: list[dict[str, Any]] = Field(default_factory=list)
    positions: list[dict[str, Any]] = Field(default_factory=list)
    snapshotDate: str | None = None
    snapshot_date: str | None = None
    source: str = "manual_position_snapshot"


class ExecutionConfirmationUpdateRequestDto(MutationRequestModel):
    date: str | None = None
    asOf: str | None = None


class OpenUrlRequestDto(MutationRequestModel):
    url: str = Field(min_length=1)


class RagSearchRequestDto(MutationRequestModel):
    query: str = Field(min_length=1)
    date: str | None = None
    selectedDate: str | None = None
    fundCode: str | None = None
    fundCodes: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    sourceKinds: list[str] = Field(default_factory=list)
    topK: int = Field(default=8, ge=1, le=100)
    tokenBudget: int = Field(default=6000, ge=1)
    includeNegativeMemory: bool = False
    includeExecution: bool = False
    profile: str = "rag_admin"
    intent: str = "rag_admin_search"
    writeTrace: bool = True


class RagEvalRequestDto(MutationRequestModel):
    date: str | None = None
    selectedDate: str | None = None
    compareLegacy: bool = True
    writeTrace: bool = True


class RagReindexRequestDto(MutationRequestModel):
    date: str | None = None
    selectedDate: str | None = None
    domain: str | list[str] | None = None
    domains: list[str] = Field(default_factory=list)
    write: bool = False
    dryRun: bool = True
    embed: bool = False
    embeddingDryRun: bool = True
    embedLimit: int | None = Field(default=None, ge=1)
    confirmWrite: str | None = None


class RagMaintenanceRequestDto(MutationRequestModel):
    action: Literal["check_integrity", "vacuum", "rebuild", "purge_domain"]
    domain: str = ""
    date: str | None = None
    selectedDate: str | None = None
    embed: bool = False
    embeddingDryRun: bool = True
    confirm: str | None = None


def model_dump_compat(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def coerce_model(model_cls: type[BaseModel], payload: dict[str, Any]) -> dict[str, Any]:
    return model_dump_compat(model_cls.model_validate(payload))
