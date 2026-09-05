"""アドベンチャーモードの API モデル。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..consts.adventure_narration import (
    NARRATION_PRONOUN_DEFAULT,
    NARRATION_PRONOUN_MAX_LENGTH,
    NARRATION_VOICE_DEFAULT,
    NarrationVoice,
)
from ..consts.adventure_romance import (
    ROMANCE_DAYS_MAX,
    ROMANCE_PLAYER_NAME_MAX_LENGTH,
    ROMANCE_SLOTS_PER_DAY,
    ROMANCE_TALK_INPUT_MAX,
)
from ..consts.adventure_setup import SCENARIO_CONSTRAINTS_MAX_ITEMS
from ..consts.adventure_speech import (
    PARTNER_SPEECH_STYLE_MAX_LENGTH,
    SPEECH_CUSTOM_MAX_LENGTH,
    SPEECH_STYLE_DEFAULT,
    SpeechStyle,
)
from ..consts.adventure_turns import (
    ADVENTURE_TURNS_DEFAULT,
    ADVENTURE_TURNS_MAX,
    ADVENTURE_TURNS_MIN,
)

# scenario_max_turns の受理上限。romance は日数×2 を手数として送るため、
# 通常プリセットの上限(ADVENTURE_TURNS_MAX)より広く取る。
# 非 romance の超過分はサービス側の clamp_generated_max_turns が丸める
SCENARIO_MAX_TURNS_REQUEST_MAX = max(
    ADVENTURE_TURNS_MAX, ROMANCE_DAYS_MAX * ROMANCE_SLOTS_PER_DAY
)

# run 単位で上書きできる NovelAI 画像モデル（consts/novelai_models.py と同期）
AdventureImageModel = Literal[
    "nai-diffusion-4-5-full",
    "nai-diffusion-4-5-curated",
    "nai-diffusion-5-full",
    "nai-diffusion-5-curated",
]


class AdventureSetupGenerateRequest(BaseModel):
    # 開始素材はゲームセッション（＋履歴時点）か Prompt Expander エントリのどちらか。
    # 両方あれば Prompt Expander エントリを優先する
    source_session_id: str | None = Field(default=None, min_length=1)
    source_history_id: str | None = None
    source_prompt_expander_entry_id: str | None = Field(default=None, max_length=80)
    preset: Literal["infiltration", "escape", "negotiation", "disguise", "romance"]

    @model_validator(mode="after")
    def _require_source(self) -> AdventureSetupGenerateRequest:
        if not self.source_session_id and not self.source_prompt_expander_entry_id:
            raise ValueError(
                "source_session_id か source_prompt_expander_entry_id のいずれかが必要です"
            )
        return self

    # 自動生成のゴール文面は「N手以内に〜」という尺で書かれるため、
    # 案の生成時点でもターン予算を渡す
    scenario_max_turns: int = Field(
        default=ADVENTURE_TURNS_DEFAULT,
        ge=ADVENTURE_TURNS_MIN,
        le=SCENARIO_MAX_TURNS_REQUEST_MAX,
    )
    # ユーザーが入力済みの舞台・ゴール・制約。空でなければ生成の下書きとして
    # LLM に渡し、意味を保ったまま仕上げ・補完させる（AdventureCreateRequest と同じ上限）
    scenario_setting: str = Field(default="", max_length=600)
    scenario_objective: str = Field(default="", max_length=600)
    scenario_constraints: list[str] = Field(
        default_factory=list, max_length=SCENARIO_CONSTRAINTS_MAX_ITEMS
    )
    # 対面会話モード(romance 専用)。ゴール文面を日数でなくターン数で書かせる
    companion_mode: bool = False


class AdventureCreateRequest(BaseModel):
    source_session_id: str | None = Field(default=None, min_length=1)
    source_history_id: str | None = None
    source_prompt_expander_entry_id: str | None = Field(default=None, max_length=80)
    preset: Literal["infiltration", "escape", "negotiation", "disguise", "romance"]
    custom_setup: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _require_source(self) -> AdventureCreateRequest:
        # リプレイ（replay_run_id）は元 run から素材を引き継ぐため素材未指定を許す
        if (
            not self.source_session_id
            and not self.source_prompt_expander_entry_id
            and not self.replay_run_id
        ):
            raise ValueError(
                "source_session_id か source_prompt_expander_entry_id のいずれかが必要です"
            )
        return self

    scenario_setting: str = Field(default="", max_length=600)
    scenario_objective: str = Field(default="", max_length=600)
    scenario_constraints: list[str] = Field(
        default_factory=list, max_length=SCENARIO_CONSTRAINTS_MAX_ITEMS
    )
    scenario_template_id: str | None = Field(default=None, max_length=80)
    replay_run_id: str | None = Field(default=None, max_length=80)
    # 自動生成タイプのみで使用。作品シナリオはテンプレJSON、
    # リプレイは元 run の max_turns を引き継ぐ
    scenario_max_turns: int = Field(
        default=ADVENTURE_TURNS_DEFAULT,
        ge=ADVENTURE_TURNS_MIN,
        le=SCENARIO_MAX_TURNS_REQUEST_MAX,
    )
    # 語りの人称。既定は従来どおりの二人称
    narration_voice: NarrationVoice = NARRATION_VOICE_DEFAULT
    # first_person のときだけ使う一人称語
    narration_pronoun: str = Field(
        default=NARRATION_PRONOUN_DEFAULT,
        min_length=1,
        max_length=NARRATION_PRONOUN_MAX_LENGTH,
    )
    # 主人公のセリフの口調。既定は丁寧語
    player_speech_style: SpeechStyle = SPEECH_STYLE_DEFAULT
    # custom のときだけ使う自由入力
    player_speech_custom: str = Field(default="", max_length=SPEECH_CUSTOM_MAX_LENGTH)
    # 既定OFF: ユーザーが明示ONしない限り精密参照でAnlasを消費しない
    use_precise_reference: bool = False
    # 既定OFF: OFF時は中央の立ち絵のみ更新し、背景合成シーンは初回のみ生成
    enable_composite_scene: bool = False
    # 衣装レイヤー考慮。ONなら外衣に覆われた下着を画像タグから除外する
    respect_clothing_layers: bool = False
    # romance の主人公テンプレートキャラクター。未指定なら既定(char1)
    romance_player_character_id: str | None = Field(default=None, max_length=40)
    # romance の主人公を特定セッション時点の変身状態にする場合に指定。
    # session_id があればテンプレートキャラクターより優先される
    romance_player_session_id: str | None = Field(default=None, max_length=80)
    romance_player_history_id: str | None = Field(default=None, max_length=80)
    # romance の主人公の呼び名(攻略対象がセリフで呼ぶ名前)。空なら
    # テンプレートキャラクター名またはセッションの主人公名を使う
    romance_player_name: str = Field(
        default="", max_length=ROMANCE_PLAYER_NAME_MAX_LENGTH
    )
    # romance の攻略対象の口調。空なら人物像からLLMが自動で決める
    romance_partner_speech_style: str = Field(
        default="", max_length=PARTNER_SPEECH_STYLE_MAX_LENGTH
    )
    # この run 専用の NovelAI 画像モデル。未指定ならグローバル設定に従う
    image_model: AdventureImageModel | None = None
    # 対面会話モード(romance 専用。他プリセットでは無視される)。
    # ONなら手番の画像は背景(現在地変化時のみ)と攻略対象の立ち絵だけになる
    companion_mode: bool = False
    # 対面会話モードで攻略対象の立ち絵の代わりに描く 3D アバター(VRM)の登録 ID
    companion_avatar_id: str | None = Field(default=None, max_length=80)
    # 持ち物システム(既定 OFF、全プリセット)。作品シナリオでは無視される
    inventory_enabled: bool = False


class AdventureSettingsUpdateRequest(BaseModel):
    use_precise_reference: bool
    enable_composite_scene: bool
    # 未指定なら既存の run 設定を維持する
    respect_clothing_layers: bool | None = None
    player_speech_style: SpeechStyle | None = None
    player_speech_custom: str | None = Field(
        default=None, max_length=SPEECH_CUSTOM_MAX_LENGTH
    )
    # romance 以外の run では無視される
    partner_speech_style: str | None = Field(
        default=None, max_length=PARTNER_SPEECH_STYLE_MAX_LENGTH
    )
    # "default" で run 単位の上書きを解除。未指定(None)なら既存値を維持する
    image_model: Literal["default"] | AdventureImageModel | None = None
    # 対面会話モード。未指定なら既存値を維持する(romance 以外では無視)
    companion_mode: bool | None = None
    # 3D アバター。"none" で解除、登録 ID で設定。未指定(None)なら既存値を維持する
    companion_avatar_id: str | None = Field(default=None, max_length=80)
    # 持ち物システム。未指定なら既存値を維持する(作品シナリオでは無視)
    inventory_enabled: bool | None = None


class AdventureTalkRequest(BaseModel):
    # トークモード(手番を消費しない会話)の1メッセージ。romance 専用
    user_input: str = Field(min_length=1, max_length=ROMANCE_TALK_INPUT_MAX)


class AdventureRealityRulesUpdateRequest(BaseModel):
    # 一覧を丸ごと置き換える。件数・表記の正規化はサービス側で行うため、
    # ここの上限は明らかに異常な量を弾くためだけのもの
    rules: list[str] = Field(default_factory=list, max_length=64)


class AdventureItemActionRequest(BaseModel):
    # 持ち物パネルの行動。item_id は所持品の ID、target は渡す相手(NPC 名)
    item_id: str = Field(min_length=1, max_length=40)
    action: Literal["give", "use", "wear", "unwear", "discard"]
    target: str | None = Field(default=None, max_length=60)


class AdventurePromptPreviewRequest(BaseModel):
    # 「この入力で送信したら何が送られるか」を組み立てるための仮の入力
    user_input: str = Field(default="", max_length=2000)
    input_kind: Literal[
        "choice",
        "free_text",
        "reality_alter",
        "gift",
        "work",
        "confess",
        "item_action",
    ] = "free_text"
    gift_id: str | None = Field(default=None, max_length=40)
    item_action: AdventureItemActionRequest | None = None


class AdventureRewindRequest(BaseModel):
    # この手番の完了時点まで巻き戻す(それ以降のターンを削除する)
    turn_number: int = Field(ge=0)


class AdventureTurnRequest(BaseModel):
    client_turn_id: str = Field(min_length=1, max_length=80)
    user_input: str = Field(min_length=1, max_length=1000)
    # reality_alter はサーバ側で「現実改変：〜」を検出したときにも設定される。
    # gift / work / confess は romance プリセット専用の行動
    input_kind: Literal[
        "choice",
        "free_text",
        "reality_alter",
        "gift",
        "work",
        "confess",
        "item_action",
    ] = "free_text"
    # romance のプレゼント購入で贈る品を機械可読 ID で指定する
    gift_id: str | None = Field(default=None, max_length=40)
    # 持ち物パネルの行動(input_kind=item_action のとき必須)
    item_action: AdventureItemActionRequest | None = None
    # false のとき主人公の立ち絵の毎ターン生成を省略する。
    # 精密参照OFFかつ非合成モードの run でのみ有効
    generate_portrait: bool = True
    # false のとき攻略対象(romance)の立ち絵の毎ターン生成を省略する。条件は同上
    generate_partner_portrait: bool = True
    # false のとき、この手番では新しい手掛かりを抽出しない。判定処理自体は
    # 走るため時間短縮はわずか。作品シナリオの決定論的な手掛かりには影響しない
    generate_clues: bool = True


class AdventureImageRequest(BaseModel):
    scene_tags: str = Field(default="", max_length=1800)
    player_tags: str = Field(default="", max_length=1200)
    npc_tags: list[str] = Field(default_factory=list, max_length=3)
    redraw_from_reference: bool = True
    # portrait は立ち絵だけを作り直す。生成失敗ターンからの復旧に使う。
    # partner は romance の攻略対象の立ち絵だけを作り直す(対面会話モードの↻)
    target: Literal["scene", "portrait", "partner"] = "scene"
