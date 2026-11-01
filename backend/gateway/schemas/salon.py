"""サロン経営モードの API モデル。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..consts.salon import SALON_DEFAULT_DIFFICULTY, SALON_NAME_MAX
from .session import SessionRequestResponse


class SalonCreateRequest(BaseModel):
    name: str = Field(..., max_length=SALON_NAME_MAX, description="サロンの名前")
    difficulty: Literal["easy", "normal", "hard"] = Field(
        SALON_DEFAULT_DIFFICULTY, description="経営の難易度。開業資金が変わる"
    )


class SalonLanguageRequest(BaseModel):
    language: str | None = Field(
        None, description="依頼・口コミの言語。未指定はユーザー設定"
    )


class SalonCustomer(BaseModel):
    source: str = Field(
        ..., description="template(同梱キャラ) / custom(カスタムキャラ)"
    )
    id: str
    name: str


class SalonVisitResponse(BaseModel):
    id: str
    week: int
    slot: int
    customer: SalonCustomer
    session_id: str | None
    status: str = Field(..., description="booked / serving / done / declined")
    satisfaction: int | None
    fulfilled: bool
    payment: int
    reputation_delta: int
    review: str | None
    visit_number: int = Field(..., description="このお客様の何回目の来店か")
    previous_review: str | None = Field(None, description="前回の来店の口コミ")


class SalonWeekResponse(BaseModel):
    """締めた週の収支。"""

    week: int
    revenue: int
    salary: int
    fixed_cost: int
    served: int
    declined: int
    cash_end: int
    reputation_end: int


class SalonResultResponse(BaseModel):
    outcome: str = Field(..., description="success / partial / bankrupt")
    cash: int
    profit: int | None = None


class SalonRunResponse(BaseModel):
    id: str
    name: str
    status: str = Field(..., description="active / completed / bankrupt")
    week: int
    total_weeks: int
    cash: int
    reputation: int
    difficulty: str = Field(..., description="経営の難易度 (easy / normal / hard)")
    initial_cash: int = Field(..., description="開業資金。決算の成功の線")
    weekly_fixed_cost: int
    weekly_salary: int
    base_price: int
    turn_limit: int
    question_limit: int
    visits: list[SalonVisitResponse]
    weeks: list[SalonWeekResponse]
    result: SalonResultResponse | None
    created_at: str | None
    updated_at: str | None


class SalonRunListResponse(BaseModel):
    runs: list[SalonRunResponse]


class SalonVisitStartResponse(BaseModel):
    session_id: str
    request: SessionRequestResponse | None
    run: SalonRunResponse
    cost_usd: float | None = None


class SalonAchievementUnlocked(BaseModel):
    """決算で解除された実績(手番の achievement イベントと同じ形)。"""

    achievement_id: str
    name: str
    description: str
    icon: str
    category: str


class SalonCloseWeekResponse(BaseModel):
    run: SalonRunResponse
    achievements: list[SalonAchievementUnlocked] = Field(default_factory=list)


class SalonCheckoutResponse(BaseModel):
    run: SalonRunResponse
    visit: SalonVisitResponse
    cost_usd: float | None = None
