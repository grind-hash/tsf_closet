"""サロン経営モードの API モデル。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ..consts.salon import (
    SALON_DEFAULT_DIFFICULTY,
    SALON_DEFAULT_SEASON_LENGTH,
    SALON_NAME_MAX,
)
from .session import SessionRequestResponse

CustomerGender = Literal["any", "man", "woman"]
DesiredBody = Literal["any", "female", "male"]


class SalonCreateRequest(BaseModel):
    name: str = Field(..., max_length=SALON_NAME_MAX, description="サロンの名前")
    difficulty: Literal["easy", "normal", "hard"] = Field(
        SALON_DEFAULT_DIFFICULTY, description="経営の難易度。開業資金が変わる"
    )
    sensitive: bool = Field(
        False,
        description="過激施術(成人向けの依頼)。開店後もオーナー室で切り替えられる",
    )
    season_length: Literal["short", "standard"] = Field(
        SALON_DEFAULT_SEASON_LENGTH,
        description="1 期の長さ(short=4 週 / standard=12 週)。開業資金と開店時の評判も変わる",
    )
    customer_gender: CustomerGender = Field(
        "any", description="来客の種類: お客様の性別(any は絞らない)"
    )
    desired_body: DesiredBody = Field(
        "any", description="来客の種類: お客様が願う体(any は生成が選ぶ)"
    )


class SalonSettingsRequest(BaseModel):
    """オーナー室の設定。指定した項目だけを変える。"""

    sensitive: bool | None = Field(
        None,
        description="過激施術(成人向けの依頼)。NSFW モードが ON のときだけ効く",
    )
    customer_gender: CustomerGender | None = Field(
        None, description="お客様の性別。次の週の予約から効く"
    )
    desired_body: DesiredBody | None = Field(
        None, description="お客様が願う体。次に接客を始めるお客様から効く"
    )


class SalonCustomerCountsResponse(BaseModel):
    """来客の種類で選べるお客様の人数(性別ごと)。"""

    any: int
    man: int
    woman: int


class SalonLanguageRequest(BaseModel):
    language: str | None = Field(
        None, description="依頼・口コミの言語。未指定はユーザー設定"
    )


class SalonCustomer(BaseModel):
    source: str = Field(
        ...,
        description="template(同梱キャラ) / custom(カスタムキャラ) / "
        "preset(キャラクター画面で作ったキャラ)",
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
    kept_look: bool = Field(
        False, description="願いを叶え、施術した姿のまま帰った(翌週もこの姿で来る)"
    )
    returning_look: bool = Field(
        False, description="前回持ち帰った姿のまま来店する予約"
    )
    experience_bonus: int = Field(
        0,
        description="過激施術のお披露目で体験まで描けたときの満足度への加点"
        "(satisfaction に含む)",
    )
    extra_cost: int = Field(
        0, description="資金で足した施術の代金(購入時に現金から引いている)"
    )
    tip: int = Field(0, description="評判に応じたチップ(payment に含む)")
    regular_fee: int = Field(
        0, description="姿を持ち越して続けて来た常連の指名料(payment に含む)"
    )


class SalonWeekResponse(BaseModel):
    """締めた週の収支。"""

    week: int
    revenue: int
    extra_cost: int = Field(0, description="追加施術の代金の合計(現金から引いた分)")
    salary: int
    fixed_cost: int
    served: int
    declined: int
    cash_end: int
    reputation_end: int


class SalonResultResponse(BaseModel):
    outcome: str = Field(..., description="success / partial / bankrupt")
    cash: int
    profit: int | None = Field(None, description="期の黒字(期末 − 期首の現金)")
    season: int = Field(1, description="何期目の決算か")
    start_cash: int | None = Field(None, description="期首の現金(成功の線)")


class SalonRunResponse(BaseModel):
    id: str
    name: str
    status: str = Field(
        ...,
        description="active / completed(期の決算済み。次の期へ進める) / bankrupt",
    )
    week: int = Field(..., description="開店からの通しの週")
    total_weeks: int = Field(..., description="今の期の最終週(通しの週)")
    cash: int
    reputation: int
    difficulty: str = Field(..., description="経営の難易度 (easy / normal / hard)")
    initial_cash: int = Field(..., description="開業資金。1 期目の決算の成功の線")
    season_length: str = Field(..., description="期の長さ (short / standard)")
    season_weeks: int = Field(..., description="1 期の週数")
    season: int = Field(1, description="今の期(1 から)")
    season_start_week: int = Field(1, description="今の期の最初の週(通しの週)")
    season_start_cash: int = Field(..., description="期首の現金。今の期の成功の線")
    seasons: list[SalonResultResponse] = Field(
        default_factory=list, description="決算を終えた期の結果(古い順)"
    )
    sensitive: bool = Field(
        False, description="過激施術の設定。NSFW モードが OFF の間は効かない"
    )
    customer_gender: str = Field("any", description="来客の種類: お客様の性別")
    desired_body: str = Field("any", description="来客の種類: お客様が願う体")
    weekly_fixed_cost: int
    weekly_salary: int
    base_price: int
    turn_limit: int
    question_limit: int
    extra_turn_price: int = Field(..., description="資金で足す施術1手の値段")
    extra_turns_max: int = Field(..., description="来店1回につき足せる施術の手数")
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


class SalonExtraTurnResponse(BaseModel):
    run: SalonRunResponse
    request: SessionRequestResponse | None


class SalonCheckoutResponse(BaseModel):
    run: SalonRunResponse
    visit: SalonVisitResponse
    cost_usd: float | None = None
