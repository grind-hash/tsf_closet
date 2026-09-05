"""通常プレイ（着せ替え / 行動 / 画像のみ）のリクエストモデル。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PlayRequest(BaseModel):
    """着せ替えプレイリクエスト"""

    session_id: str | None = Field(None, description="既存セッションID（継続プレイ時）")
    character_id: str | None = Field(None, description="キャラクターID（新規開始時）")
    character_image: str | None = Field(
        None, description="Base64エンコード画像（カスタム時）"
    )
    instruction: str = Field(
        ..., description="着せ替え指示テキスト", min_length=1, max_length=500
    )
    # 衣装参照画像
    costume_image: str | None = Field(
        None, description="Base64エンコードされた参照衣装画像"
    )
    # NovelAI専用: マスク & プロンプト制御
    mask_image: str | None = Field(
        None,
        description="Base64エンコードされたインペイント用マスク画像（透明=保持, 白=変更）",
    )
    mask_id: str | None = Field(
        None, description="保存済みマスクID（/game/masks で取得）"
    )
    inpaint_strength: float | None = Field(
        None, description="NovelAI inpaintImg2ImgStrength (0.05-0.99 推奨)"
    )
    inpaint_noise: float | None = Field(
        None, description="NovelAI img2img noise (0-0.5 推奨)"
    )
    negative_prompt: str | None = Field(
        None, description="NovelAI専用ネガティブプロンプト"
    )
    prompt_override: str | None = Field(
        None,
        description="NovelAI専用: LLM生成をスキップしてこのプロンプトをそのまま使う",
    )
    # 変身タイプ: costume=衣装変更, reality=現実改変
    transformation_type: str = Field(
        "costume", description="変身タイプ (costume=衣装変更, reality=現実改変)"
    )
    # 指示タイプ: dress_up, reality_alter, action, conversation, image_only
    instruction_type: str | None = Field(
        None,
        description=(
            "指示タイプ (dress_up, reality_alter, action, conversation, image_only)"
        ),
    )
    use_memory: bool = Field(
        False,
        description="保存済みメモリテキスト（ユーザーの嗜好傾向）を生成に反映するか",
    )
    use_play_memory: bool = Field(
        False, description="セッション単位のプレイメモを生成に反映するか"
    )
    use_history_lookback: bool | None = Field(
        None,
        description="履歴遡及を利用するか（未指定時は操作種別の既定値を使用）",
    )
    respect_clothing_layers: bool = Field(
        False,
        description="外衣による下着・身体属性の被覆を画像と心境で考慮するか",
    )
    language: str | None = Field(
        None, description="応答言語（ja/en、未指定時はユーザー設定を使用）"
    )


class CharacterReferenceParam(BaseModel):
    """NovelAI Character Reference parameter."""

    image: str = Field(..., min_length=1, description="Base64 encoded image data")
    type: Literal["character", "style", "character&style"] = Field(
        "character&style", description="Reference type"
    )
    strength: float = Field(1.0, ge=0.0, le=1.0, description="Reference strength")
    fidelity: float = Field(1.0, ge=0.0, le=1.0, description="Reference fidelity")


class PlayStreamRequest(BaseModel):
    """ストリーミング着せ替えリクエスト"""

    instruction: str = Field(
        ..., min_length=1, max_length=500, description="着せ替え指示"
    )
    session_id: str | None = Field(None, description="既存セッションID")
    character_id: str | None = Field(None, description="キャラクターID")
    character_image: str | None = Field(None, description="Base64エンコード画像")
    base_history_id: str | None = Field(None, description="履歴からのベース画像ID")
    costume_image: str | None = Field(None, description="衣装参照画像（Base64）")
    # 変身タイプ
    transformation_type: str = Field(
        "costume", description="変身タイプ (costume=衣装変更, reality=現実改変)"
    )
    # 007-chat-interactive-ux: 指示タイプ（チャット表示用）
    instruction_type: str | None = Field(
        None,
        description=(
            "指示タイプ (dress_up=着せ替え, reality_alter=現実改変, "
            "conversation=会話, action=行動, image_only=画像のみ)"
        ),
    )
    # NovelAI専用フィールド
    mask_image: str | None = Field(
        None, description="Base64エンコードされたインペイントマスク"
    )
    mask_id: str | None = Field(
        None, description="保存済みマスクID（/game/masks で取得）"
    )
    inpaint_strength: float | None = Field(
        None, description="inpaintImg2ImgStrength (0.05-0.99)"
    )
    inpaint_noise: float | None = Field(None, description="img2img noise (0-0.5)")
    negative_prompt: str | None = Field(None, description="NovelAIネガティブプロンプト")
    prompt_override: str | None = Field(
        None, description="LLM生成をスキップしこのプロンプトを使う"
    )
    # ユーザー設定（リクエストごとにオーバーライド可能）
    nsfw_mode: bool | None = Field(
        None, description="NSFWモード（未指定時はセッション設定を使用）"
    )
    difficulty: str | None = Field(
        None, description="難易度（未指定時はセッション設定を使用）"
    )
    language: str | None = Field(
        None, description="応答言語（ja/en、未指定時はユーザー設定を使用）"
    )
    # NovelAI精密参照画像
    character_references: list[CharacterReferenceParam] | None = Field(
        None,
        description="精密参照画像パラメータの配列（NovelAIプロバイダー使用時のみ有効）",
    )
    # Seed for image generation
    seed: int | None = Field(
        None,
        description="画像生成seed値（0〜999999999、未指定時はランダム）",
        ge=0,
        le=999999999,
    )
    # Surroundings image generation toggle
    enable_surroundings_image: bool = Field(
        False,
        description="行動後の周囲状況画像生成を有効にする",
    )
    # Surroundings image: include reactive bystanders
    surroundings_include_people: bool = Field(
        False,
        description="周囲状況画像にリアクションする通行人を含める",
    )
    # Clothing color consistency toggle
    clothing_color_consistency: bool = Field(
        False,
        description="服の色の一貫性を保つ実験的機能",
    )
    respect_clothing_layers: bool = Field(
        False,
        description="外衣による下着・身体属性の被覆を画像と心境で考慮する",
    )
    # Multiple people in image generation toggle
    enable_multiple_people: bool = Field(
        False,
        description="複数人表示を有効にする実験的機能",
    )
    # CharacterPanel (session_characters) injection toggle.
    # False の場合、複数人表示の GLM-4.6 ルール緩和はそのまま保ちつつ、
    # session_characters パネルからのプロンプト注入をバイパスする（v0.5.0 以前の旧仕様）。
    use_character_panel: bool = Field(
        True,
        description="登場人物パネルの情報を画像生成プロンプトに注入するか",
    )
    use_memory: bool = Field(
        False,
        description="保存済みメモリテキスト（ユーザーの嗜好傾向）を生成に反映するか",
    )
    use_play_memory: bool = Field(
        False, description="セッション単位のプレイメモを生成に反映するか"
    )
    use_history_lookback: bool | None = Field(
        None,
        description="履歴遡及を利用するか（未指定時は操作種別の既定値を使用）",
    )
    image_only_text_to_image: bool = Field(
        False,
        description=(
            "画像のみモードで前画像を使わず text-to-image で生成する"
            "（image_only 以外の指示タイプでは無視）"
        ),
    )
