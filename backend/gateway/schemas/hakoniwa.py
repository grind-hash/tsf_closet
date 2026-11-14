"""AI箱庭モードの API モデル。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ..consts.hakoniwa import (
    HAKONIWA_APPEARANCE_TEXT_MAX,
    HAKONIWA_CUSTOM_RULE_NAME_MAX,
    HAKONIWA_CUSTOM_RULE_TEXT_MAX,
    HAKONIWA_DIRECTED_EVENT_PARTNERS_MAX,
    HAKONIWA_DIRECTED_EVENT_TEXT_MAX,
    HAKONIWA_MANUAL_TAGS_INPUT_MAX,
    HAKONIWA_MAX_RESIDENTS,
    HAKONIWA_PERSONALITY_MAX,
    HAKONIWA_REALITY_TEXT_MAX,
    HAKONIWA_RESIDENT_NAME_MAX,
    HAKONIWA_RULE_APPEARANCE_TEXT_MAX,
    HAKONIWA_TRANSFORM_TEXT_MAX,
    HAKONIWA_WORLD_NAME_MAX,
)
from ..consts.hakoniwa_play import (
    HAKONIWA_CHAT_MESSAGE_MAX,
    HAKONIWA_PLAYER_NAME_MAX,
    HAKONIWA_THEME_TEXT_MAX,
    HAKONIWA_WORLD_MEMO_MAX,
)
from ..consts.hakoniwa_random import (
    HAKONIWA_RANDOM_COUNT_DEFAULT,
    HAKONIWA_RANDOM_COUNT_MAX,
    HAKONIWA_RANDOM_COUNT_MIN,
)

Gender = Literal["female", "male"]
# 住民がほかの住民を呼ぶときのくせ(consts の HAKONIWA_ADDRESS_STYLES と同じ並び)
AddressStyle = Literal["given_chan", "given_san", "given", "family_san", "family"]


class HakoniwaLanguageRequest(BaseModel):
    language: str | None = Field(
        None, description="表示・生成の言語。未指定はユーザー設定"
    )


class HakoniwaCharacterEntry(BaseModel):
    character_preset_id: str = Field(
        ..., description="キャラクター画面で作ったキャラの id"
    )
    gender: Gender | None = Field(
        None, description="キャラクターの性別が未設定のときに使う性別"
    )


class HakoniwaRandomResident(BaseModel):
    """おまかせの住民の定義(作成画面のプレビューと、世界を作るときの入力)。"""

    name: str = Field(..., max_length=HAKONIWA_RESIDENT_NAME_MAX)
    gender: Gender
    age: str = ""
    job: str = ""
    personality: str = Field(..., max_length=HAKONIWA_PERSONALITY_MAX)
    pronoun: str = ""
    address_style: AddressStyle = Field(
        "given_san", description="ほかの住民を呼ぶときのくせ"
    )
    appearance_text: str = Field("", max_length=HAKONIWA_APPEARANCE_TEXT_MAX)
    base_tags: str = Field("", description="外見の英語タグ(画像生成用)")


class HakoniwaRandomResidentsRequest(HakoniwaLanguageRequest):
    count: int = Field(
        HAKONIWA_RANDOM_COUNT_DEFAULT,
        ge=HAKONIWA_RANDOM_COUNT_MIN,
        le=HAKONIWA_RANDOM_COUNT_MAX,
        description="組む人数(1人の入れ替えは 1)",
    )
    exclude_names: list[str] = Field(
        default_factory=list,
        max_length=HAKONIWA_MAX_RESIDENTS * 2,
        description="重ねない名前(ほかの住民の名前)",
    )


class HakoniwaRandomResidentsResponse(BaseModel):
    residents: list[HakoniwaRandomResident]
    source: Literal["llm", "template"] = Field(
        ..., description="llm: テキストモデルで作った / template: 語彙の組み合わせ"
    )
    cost_usd: float | None = None


class HakoniwaThemeInput(BaseModel):
    """実験テーマ。自由文があれば自由文、無ければプリセット。どちらも空ならテーマ無し。"""

    preset_id: str | None = Field(
        None, description="swap / dress / dissonance / transform / free"
    )
    text: str = Field("", max_length=HAKONIWA_THEME_TEXT_MAX)


class HakoniwaCreateRequest(HakoniwaLanguageRequest):
    name: str = Field(..., max_length=HAKONIWA_WORLD_NAME_MAX, description="世界の名前")
    preset_ids: list[str] = Field(
        default_factory=list,
        max_length=HAKONIWA_MAX_RESIDENTS,
        description="住民にするプリセットの id",
    )
    characters: list[HakoniwaCharacterEntry] = Field(
        default_factory=list,
        max_length=HAKONIWA_MAX_RESIDENTS,
        description="住民にする登録キャラクター",
    )
    dissonance_enabled: bool = Field(
        True, description="世界の違和感(住民が書き換えに気づいていく)を使うか"
    )
    custom_residents: list[HakoniwaRandomResident] = Field(
        default_factory=list,
        max_length=HAKONIWA_MAX_RESIDENTS,
        description="おまかせの住民(作成画面で組んだ定義)",
    )
    experiment_theme: HakoniwaThemeInput | None = Field(
        None, description="実験テーマ。未指定はテーマ無し"
    )


class HakoniwaSettingsRequest(HakoniwaLanguageRequest):
    web_search_enabled: bool | None = Field(
        None, description="Web検索を使うか。未指定は変更しない"
    )
    image_model: str | None = Field(
        None, description="アバター生成の画像モデル。default はユーザー設定に従う"
    )
    dissonance_enabled: bool | None = Field(
        None, description="世界の違和感を使うか。未指定は変更しない"
    )
    world_memo: str | None = Field(
        None,
        max_length=HAKONIWA_WORLD_MEMO_MAX,
        description="世界のメモ(全生成に最優先の指示として載せる)。未指定は変更しない",
    )
    experiment_theme: HakoniwaThemeInput | None = Field(
        None,
        description="実験テーマ。未指定は変更しない(両方空で送るとテーマ無し)",
    )
    player_name: str | None = Field(
        None,
        max_length=HAKONIWA_PLAYER_NAME_MAX,
        description=(
            "住民がプレイヤーを呼ぶときの名前(空なら名前で呼ばない)。未指定は変更しない"
        ),
    )


class HakoniwaRuleToggleRequest(HakoniwaLanguageRequest):
    active: bool
    area_id: str | None = Field(
        None, description="いま見ている場所。切り替え直後の反応の話し手をそこから選ぶ"
    )


class HakoniwaCustomRuleRequest(HakoniwaLanguageRequest):
    name: str = Field(..., max_length=HAKONIWA_CUSTOM_RULE_NAME_MAX)
    text: str = Field(..., max_length=HAKONIWA_CUSTOM_RULE_TEXT_MAX)
    appearance_text: str = Field(
        "",
        max_length=HAKONIWA_RULE_APPEARANCE_TEXT_MAX,
        description="掟が住民の見た目に与える変化の説明(任意。タグを作るときの元)",
    )
    appearance_tags: str = Field(
        "",
        max_length=HAKONIWA_MANUAL_TAGS_INPUT_MAX,
        description="掟の見た目のタグ(そのまま姿の生成に使う)。空なら見た目を変えない",
    )
    body_gender: Gender | None = Field(
        None,
        description="掟の姿で住民の体をこの性別にする。None は住民それぞれのまま(保存のたびに送る)",
    )


class HakoniwaLookRequest(HakoniwaLanguageRequest):
    regenerate: bool = Field(
        False, description="生成済みの住民も描き直す。false はまだの住民だけ"
    )
    resident_id: str | None = Field(
        None,
        description=(
            "この住民の姿だけを生成する(画面は1人ずつ呼んで進み具合を出す)。"
            "省略すると対象の住民全員を順に生成する"
        ),
    )


class HakoniwaResidentRequest(HakoniwaLanguageRequest):
    name: str = Field(..., max_length=HAKONIWA_RESIDENT_NAME_MAX)
    personality: str = Field(..., max_length=HAKONIWA_PERSONALITY_MAX)
    gender: Gender
    appearance_text: str = Field(
        "",
        max_length=HAKONIWA_APPEARANCE_TEXT_MAX,
        description="外見の説明(日本語の文章か英語のタグ)。画像タグは別に作る",
    )
    dress_text: str = Field(
        "",
        max_length=HAKONIWA_APPEARANCE_TEXT_MAX,
        description="ドレスの掟で着るドレス姿の説明(任意)",
    )
    address_style: AddressStyle | None = Field(
        None,
        description="ほかの住民を呼ぶときのくせ。未指定ならプリセットか既定のまま",
    )
    base_tags: str = Field(
        "",
        max_length=HAKONIWA_MANUAL_TAGS_INPUT_MAX,
        description="いつもの姿の画像タグ(必須。そのまま姿の生成に使う)",
    )
    dress_tags: str = Field(
        "",
        max_length=HAKONIWA_MANUAL_TAGS_INPUT_MAX,
        description="ドレス姿の画像タグ。空ならドレス姿を生成するときにいつもの姿から考える",
    )


class HakoniwaRuleLookTagsRequest(HakoniwaLanguageRequest):
    name: str = Field("", max_length=HAKONIWA_CUSTOM_RULE_NAME_MAX)
    text: str = Field("", max_length=HAKONIWA_CUSTOM_RULE_TEXT_MAX)
    appearance_text: str = Field(
        "", max_length=HAKONIWA_RULE_APPEARANCE_TEXT_MAX, description="見た目の説明"
    )


class HakoniwaResidentTagsRequest(HakoniwaLanguageRequest):
    appearance_text: str = Field(
        ...,
        max_length=HAKONIWA_APPEARANCE_TEXT_MAX,
        description="外見(dress ならドレス姿)の説明。日本語の文章か英語のタグ",
    )
    gender: Gender
    dress: bool = Field(False, description="ドレスの掟で着るドレス姿のタグを作る")


class HakoniwaTagsResponse(BaseModel):
    tags: str
    cost_usd: float | None = None


class HakoniwaCharacterResidentRequest(HakoniwaLanguageRequest):
    character_preset_id: str
    gender: Gender | None = None


class HakoniwaTransformRequest(HakoniwaLanguageRequest):
    instruction: str = Field(..., min_length=1, max_length=HAKONIWA_TRANSFORM_TEXT_MAX)


class HakoniwaRealityRequest(HakoniwaLanguageRequest):
    instruction: str = Field(
        ...,
        min_length=1,
        max_length=HAKONIWA_REALITY_TEXT_MAX,
        description="その住民についての新しい世界の常識(例: 昔からグラビアアイドル)",
    )
    change_look: bool = Field(
        True, description="変身と同じ仕組みで、改変に合う姿も生成する"
    )


class HakoniwaDirectedEventRequest(HakoniwaLanguageRequest):
    instruction: str = Field(
        ..., min_length=1, max_length=HAKONIWA_DIRECTED_EVENT_TEXT_MAX
    )
    scope: Literal["solo", "selected", "room"] = Field(
        "solo",
        description="solo: 本人だけ / selected: 選んだ住民と / room: 同じ部屋の住民と",
    )
    partner_ids: list[str] = Field(
        default_factory=list,
        max_length=HAKONIWA_DIRECTED_EVENT_PARTNERS_MAX,
        description="selected のときに一緒に出る住民の id",
    )
    location: str | None = Field(
        None, max_length=40, description="出来事の場所の id(空ならおまかせ)"
    )


class HakoniwaContinueEventRequest(HakoniwaLanguageRequest):
    instruction: str = Field(
        ..., min_length=1, max_length=HAKONIWA_DIRECTED_EVENT_TEXT_MAX
    )


class HakoniwaReapplyRequest(HakoniwaLanguageRequest):
    image: str = Field(..., description="履歴の変身の画像ファイル名")


class HakoniwaAvatarRequest(HakoniwaLanguageRequest):
    variant: Literal["base", "dress"] = "base"


class HakoniwaFavoriteRequest(HakoniwaLanguageRequest):
    favorite: bool


class HakoniwaLine(BaseModel):
    speaker: str = Field(..., description="話す住民の id")
    text: str


class HakoniwaSceneSuggestion(BaseModel):
    level: str = Field(..., description="normal / strong")
    reason: str


class HakoniwaWebSource(BaseModel):
    title: str
    url: str


class HakoniwaWebSearch(BaseModel):
    query: str
    retrieved_at: str
    status: Literal["used", "unused", "no_results", "failed", "blocked"]
    sources: list[HakoniwaWebSource] = Field(default_factory=list)


class HakoniwaEvent(BaseModel):
    id: str
    day: int
    title: str
    narration: str
    lines: list[HakoniwaLine]
    participants: list[str]
    mood_delta: dict[str, int]
    affinity_delta: int
    source: str = Field(..., description="llm / template / player")
    web_search: HakoniwaWebSearch | None = None
    kind: str | None = Field(
        None,
        description="transform(変身の出来事)・reality(住民の改変)・directed(指示した出来事)など",
    )
    change_text: str | None = None
    instruction: str | None = Field(
        None, description="書き手が指示して起こした出来事(directed)の指示文"
    )
    location: str | None = Field(
        None, description="エリアの外で起きた出来事の場所(浴室・商店街など)"
    )
    continues: str | None = Field(
        None, description="続きとして起こした出来事の、元になった出来事の id"
    )
    favorite: bool = False
    area: str = Field("living", description="出来事の起きた場所")
    scene_image: str | None = Field(None, description="場面絵のファイル名")
    scene_image_url: str | None = None
    scene_suggestion: HakoniwaSceneSuggestion | None = Field(
        None, description="場面絵をすすめる理由(生成済みなら null)"
    )
    arc_id: str | None = Field(None, description="続きを描いた物語の弧の id")
    arc_climax: bool | None = Field(None, description="物語の弧の山場の出来事")
    bgm: str | None = Field(
        None,
        description="出来事を見せる間の BGM のキー(LLM が選んだときだけ。無ければふだんの曲)",
    )


class HakoniwaAdaptation(BaseModel):
    kind: str = Field(..., description="swap / transform")
    stage: int = Field(..., description="0 戸惑い〜3 受容(世界の側は 0 驚き〜3 定着)")


class HakoniwaRemnant(BaseModel):
    kind: str = Field(..., description="swap / transform")
    text: str
    days_left: int


class HakoniwaMemory(BaseModel):
    day: int
    kind: str
    text: str


class HakoniwaDissonance(BaseModel):
    enabled: bool
    value: int
    stage: str = Field(
        ..., description="stillness / stirring / probing / confrontation"
    )
    acknowledged: bool = Field(..., description="対面を経て書き手の存在を公認した")
    next_stage: str | None = None
    remaining: int | None = Field(None, description="次の段階までの残り")


class HakoniwaStoryArc(BaseModel):
    id: str
    kind: str = Field(..., description="investigation / swap / transform / bond")
    resident_ids: list[str]
    progress: int
    beats_to_climax: int
    status: str = Field(..., description="active / closed")
    started_day: int
    closed_day: int | None = None
    close_reason: str | None = Field(None, description="climax / resolved / faded")


class HakoniwaTransformation(BaseModel):
    description: str
    tags: str
    image: str
    image_url: str | None
    day: int
    kind: str | None = Field(
        None, description="reality は住民の改変で変えた姿(昔からそうだと受け止める)"
    )


class HakoniwaReality(BaseModel):
    id: str
    text: str = Field(..., description="その住民についての世界の常識")
    day: int


class HakoniwaResident(BaseModel):
    id: str
    source: str = Field(..., description="preset / character / custom")
    preset_id: str | None
    character_preset_id: str | None
    name: str
    gender: Gender
    body_gender: Gender = Field(..., description="いま見えている体の性別")
    age: str
    job: str
    personality: str
    pronoun: str
    address_style: AddressStyle = Field(
        "given_san", description="ほかの住民を呼ぶときのくせ"
    )
    addresses: dict[str, str] = Field(
        default_factory=dict,
        description="ほかの住民(id)をふだん何と呼ぶか(台詞で使う呼び方)",
    )
    appearance_text: str
    base_tags: str = Field(..., description="通常の姿の画像タグ")
    dress_text: str
    dress_tags: str
    mood: int
    affinities: dict[str, int]
    player_affinity: int = Field(
        0, description="プレイヤーへの好感度(-50..50)。会話の中身で動く"
    )
    transformation: HakoniwaTransformation | None
    transformation_history: list[HakoniwaTransformation]
    realities: list[HakoniwaReality] = Field(
        default_factory=list, description="住民の改変(古い順)"
    )
    swapped_with: str | None
    display_avatar_url: str | None = Field(..., description="いま表示する姿")
    display_kind: str = Field(
        ..., description="transform / combo / rule / dress / base"
    )
    display_owner_id: str = Field(
        ..., description="表示する姿の持ち主(入れ替わり中は相手)"
    )
    own_avatar_url: str | None
    avatar_url: str | None
    dress_avatar_url: str | None
    current_area: str = Field("living", description="いまいる場所")
    adaptation: HakoniwaAdaptation | None = Field(
        None, description="変身・入れ替わりへの本人の適応"
    )
    world_adaptation: HakoniwaAdaptation | None = Field(
        None, description="いまの姿への周囲(世界)の適応"
    )
    remnant: HakoniwaRemnant | None = Field(
        None, description="変身・入れ替わりが解けたあとの名残"
    )
    memories: list[HakoniwaMemory] = Field(
        default_factory=list, description="覚えている大きな出来事"
    )


class HakoniwaSynergy(BaseModel):
    with_id: str = Field(..., description="組み合わせる相手の掟")
    label: str
    hint: str
    active: bool = Field(..., description="両方とも有効で、相性が発動している")


class HakoniwaIntervention(BaseModel):
    selected: str = Field(..., description="次の「1日進める」で効かせる介入")
    choices: list[str] = Field(
        ..., description="いま選べる介入(見守る・後押し・書き換え)"
    )


class HakoniwaLookStatus(BaseModel):
    ready: int = Field(..., description="今の見た目で姿を生成済みの住民の数")
    stale: int = Field(..., description="見た目を変える前に生成した姿の住民の数")
    total: int
    pending: list[str] = Field(
        default_factory=list,
        description="まだ生成していないか、見た目を変える前の姿の住民の id(住民の並び順)",
    )


class HakoniwaRuleCard(BaseModel):
    id: str
    name: str
    description: str
    custom: bool
    active: bool
    appearance_text: str | None = Field(None, description="見た目の説明(自作の掟)")
    appearance_tags: str | None = Field(
        None, description="見た目のタグ(自作の掟)。空なら見た目を変えない"
    )
    body_gender: Gender | None = Field(
        None, description="掟の姿の体の性別(自作の掟。None は住民それぞれのまま)"
    )
    look: HakoniwaLookStatus | None = Field(None, description="掟の姿の生成状況")
    synergies: list[HakoniwaSynergy] | None = Field(
        None, description="既定の掟どうしの相性"
    )


class HakoniwaComboLook(HakoniwaLookStatus):
    rule_ids: list[str]
    names: list[str] = Field(..., description="重なっている自作の掟の名前")
    includes_dress: bool


class HakoniwaMemoLook(HakoniwaLookStatus):
    tags: str = Field(
        ..., description="世界のメモから作った、住民全員に効く見た目のタグ"
    )
    body_gender: str | None = Field(
        None, description="メモが定める体の性別(None は住民それぞれのまま)"
    )


class HakoniwaSlot(BaseModel):
    x: int
    y: int
    furniture_id: str | None


class HakoniwaArea(BaseModel):
    id: str
    name: str
    background_url: str
    slots: list[HakoniwaSlot]


class HakoniwaLocation(BaseModel):
    id: str
    name: str
    background_url: str | None = Field(
        None, description="ADV の背景にする同梱の画像(場面の絵が無いとき)"
    )


class HakoniwaFurniture(BaseModel):
    id: str
    name: str
    url: str


class HakoniwaAchievementUnlocked(BaseModel):
    """新しく達成した観察記録(通知用)。"""

    achievement_id: str
    name: str
    description: str
    icon: str
    category: str


class HakoniwaWorldResponse(BaseModel):
    web_search_enabled: bool = Field(False, description="この世界でWeb検索を使うか")
    web_search_configured: bool = Field(
        False, description="TavilyのAPIキーが設定済みか"
    )
    new_achievements: list[HakoniwaAchievementUnlocked] = Field(
        default_factory=list,
        description="この応答で新しく達成した観察記録(実績)。通知に使う",
    )
    id: str
    name: str
    day: int
    created_at: str | None
    updated_at: str | None
    background_url: str
    image_model: str
    image_model_effective: str
    image_model_default: str = Field(..., description="ユーザー設定の画像モデル")
    image_model_options: list[str]
    transparency: str = Field(
        ..., description="native(V5 の透過生成)/ removal(白背景を表示側で抜く)"
    )
    active_rules: list[str]
    swap_pair: list[str] | None
    rule_cards: list[HakoniwaRuleCard]
    residents: list[HakoniwaResident]
    events: list[HakoniwaEvent]
    areas: list[HakoniwaArea]
    locations: list[HakoniwaLocation] = Field(
        default_factory=list,
        description="出来事の場所(場面の絵の背景)。エリアとエリアの外の場所",
    )
    furniture_catalog: list[HakoniwaFurniture]
    last_digest: dict[str, Any] | None = Field(
        None, description="直近の1日のまとめ(種類と参照。文は表示側で組み立てる)"
    )
    dissonance: HakoniwaDissonance
    story_arcs: list[HakoniwaStoryArc] = Field(
        default_factory=list, description="進行中と、最近閉じた物語の弧"
    )
    combo_look: HakoniwaComboLook | None = Field(
        None, description="見た目の掟が2つ以上重なっているときの複合の姿"
    )
    memo_look: HakoniwaMemoLook | None = Field(
        None,
        description="世界のメモが住民全員に与える姿(メモが姿を変えていなければ null)",
    )
    memo_look_planned: bool = Field(
        False, description="いまの世界のメモが姿に関わるかを、もう確かめたか"
    )
    world_memo: str = Field("", description="世界のメモ")
    player_name: str = Field(
        "", description="住民がプレイヤーを呼ぶときの名前(空なら名前で呼ばない)"
    )
    experiment_theme: HakoniwaThemeInput | None = Field(
        None, description="実験テーマ(テーマ無しは null)"
    )
    intervention: HakoniwaIntervention


class HakoniwaResidentPreview(BaseModel):
    id: str
    name: str
    avatar_url: str | None


class HakoniwaWorldSummary(BaseModel):
    id: str
    name: str
    day: int
    resident_count: int
    event_count: int
    created_at: str | None
    updated_at: str | None
    residents: list[HakoniwaResidentPreview]


class HakoniwaWorldListResponse(BaseModel):
    worlds: list[HakoniwaWorldSummary]


class HakoniwaPreset(BaseModel):
    id: str
    gender: Gender
    name: str
    age: str
    job: str
    personality: str
    avatar_url: str
    dress_avatar_url: str


class HakoniwaCatalogRuleCard(BaseModel):
    id: str
    name: str
    description: str


class HakoniwaCatalogResponse(BaseModel):
    presets: list[HakoniwaPreset]
    rule_cards: list[HakoniwaCatalogRuleCard]
    background_url: str
    image_model_options: list[str]


class HakoniwaReactionLine(BaseModel):
    resident_id: str
    text: str


class HakoniwaRuleReaction(BaseModel):
    """掟を切り替えた直後の住民の反応(年代記には残さない)。"""

    card_id: str
    active: bool
    area: str | None = None
    lines: list[HakoniwaReactionLine]


class HakoniwaDayResponse(BaseModel):
    world: HakoniwaWorldResponse
    new_events: list[HakoniwaEvent]
    digest: dict[str, Any] | None = Field(None, description="その日のまとめ")
    reaction: HakoniwaRuleReaction | None = Field(
        None, description="掟の切り替え直後の反応(掟の切り替えのときだけ)"
    )
    cost_usd: float | None = None


class HakoniwaFurnitureRequest(HakoniwaLanguageRequest):
    area_id: str
    slot: int = Field(..., ge=0)
    furniture_id: str | None = Field(None, description="null で片付ける")


class HakoniwaResidentChangeResponse(BaseModel):
    world: HakoniwaWorldResponse
    resident_id: str


class HakoniwaGreetingResponse(BaseModel):
    resident_id: str
    text: str
    source: str = Field(..., description="llm / template")
    cost_usd: float | None = None


class HakoniwaImageResponse(BaseModel):
    world: HakoniwaWorldResponse
    cost_usd: float | None = None


class HakoniwaMemoLookPlanResponse(BaseModel):
    world: HakoniwaWorldResponse
    changes_look: bool = Field(..., description="世界のメモが住民全員の姿を変えるか")
    cost_usd: float | None = None


class HakoniwaEventLookChange(BaseModel):
    resident_id: str
    description: str = Field(..., description="出来事のあとの姿の短い説明")


class HakoniwaEventLookPlanResponse(BaseModel):
    world: HakoniwaWorldResponse
    changes: list[HakoniwaEventLookChange] = Field(
        ..., description="出来事の結果として姿が変わる住民(誰も変わらなければ空)"
    )
    cost_usd: float | None = None


class HakoniwaLookResponse(BaseModel):
    world: HakoniwaWorldResponse
    generated: int = Field(..., description="姿を生成した住民の数")
    failed: int = Field(..., description="生成できなかった住民の数")
    cost_usd: float | None = None


class HakoniwaInterventionRequest(HakoniwaLanguageRequest):
    choice: str = Field(..., description="watch / nudge / rewrite / arc_boost など")


class HakoniwaTouchRequest(HakoniwaLanguageRequest):
    part: Literal["head", "chest", "lower"]


class HakoniwaTouchResponse(BaseModel):
    world: HakoniwaWorldResponse
    resident_id: str
    part: str
    text: str
    source: str = Field(..., description="llm / template")
    mood_delta: int
    cost_usd: float | None = None


class HakoniwaChatRequest(HakoniwaLanguageRequest):
    message: str = Field(..., max_length=HAKONIWA_CHAT_MESSAGE_MAX)
    allow_image: bool = Field(
        True,
        description="変身の指示なら、そのまま画像を生成してよいか(V5 の確認が要るなら false)",
    )
    confirmed_instruction: str | None = Field(
        None, description="確認のあと送り直すときの変身の指示(分類せずに変身する)"
    )


class HakoniwaChatEntry(BaseModel):
    role: Literal["player", "resident", "system"]
    text: str
    kind: str | None = Field(None, description="alteration / alteration_reaction")
    source: str | None = None
    web_search: HakoniwaWebSearch | None = None
    affinity_delta: int | None = Field(
        None, description="この返事で動いたプレイヤーへの好感度(動かなければ無し)"
    )


class HakoniwaChatAlteration(BaseModel):
    action: str = Field(..., description="transform / clear / none")
    instruction: str
    executed: bool
    needs_confirmation: bool = Field(
        ..., description="画像の生成の前に確認が要るので、まだ実行していない"
    )


class HakoniwaChatResponse(BaseModel):
    world: HakoniwaWorldResponse | None = Field(
        None, description="確認待ちで何も変えていないときは null"
    )
    reply: HakoniwaChatEntry | None
    history: list[HakoniwaChatEntry]
    alteration: HakoniwaChatAlteration
    new_events: list[HakoniwaEvent] = Field(
        default_factory=list, description="会話からの変身で年代記に積んだ出来事"
    )
    cost_usd: float | None = None


class HakoniwaChatHistoryResponse(BaseModel):
    resident_id: str
    history: list[HakoniwaChatEntry]
