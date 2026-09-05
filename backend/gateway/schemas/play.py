"""通常プレイ（着せ替え / 行動 / 画像のみ）のリクエストモデル。"""

from __future__ import annotations

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
