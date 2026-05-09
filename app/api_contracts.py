from __future__ import annotations

from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    model_config = ConfigDict(extra="allow")


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
    dailyFirstOpen: dict[str, Any] = Field(default_factory=dict)


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


class RealtimePageDto(ContractModel):
    selectedDate: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    realtime: dict[str, Any] = Field(default_factory=dict)


class ReviewPageDto(ContractModel):
    selectedDate: str = ""
    summary: dict[str, Any] = Field(default_factory=dict)
    review: dict[str, Any] = Field(default_factory=dict)
    longMemory: dict[str, Any] = Field(default_factory=dict)


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


def model_dump_compat(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def coerce_model(model_cls: type[BaseModel], payload: dict[str, Any]) -> dict[str, Any]:
    return model_dump_compat(model_cls.model_validate(payload))
