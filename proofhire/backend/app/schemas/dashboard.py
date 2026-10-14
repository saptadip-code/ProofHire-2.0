"""Response models for /dashboard/* (guidebook Section 5.4 and B4).

    DashboardSummary   GET /dashboard/summary
    TrendPoint         GET /dashboard/trends  (a list of these)
    GET /dashboard/model-metrics returns the contents of metrics.json plus model_version.
    That body is passed through as stored (Member 1 owns its content), so it has no model here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class LevelCounts(BaseModel):
    low: int
    medium: int
    high: int


class TopEvidence(BaseModel):
    code: str
    label: str
    count: int


class ReportCounts(BaseModel):
    total: int
    pending: int
    approved: int
    rejected: int


class LlmStats(BaseModel):
    calls: int
    success_rate: float | None  # 0..1; null when there were no calls
    avg_latency_ms: float | None  # null when there were no calls
    template_fallbacks: int


class DashboardSummary(BaseModel):
    total_assessments: int
    by_level: LevelCounts
    avg_risk_score: float | None  # null when there are no assessments
    top_evidence: list[TopEvidence]
    reports: ReportCounts
    connections_found: int
    llm: LlmStats
    data_scope: Literal["real_only", "including_demo"]


class TrendPoint(BaseModel):
    date: str  # YYYY-MM-DD (UTC)
    count: int
    high: int
    medium: int
    low: int
