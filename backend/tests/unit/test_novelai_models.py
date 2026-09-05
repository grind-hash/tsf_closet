"""NovelAI 画像モデルレジストリと usage パースのユニットテスト。"""

import pytest

from gateway.consts.novelai_models import (
    DEFAULT_NSFW_IMAGE_MODEL,
    DEFAULT_SFW_IMAGE_MODEL,
    NOVELAI_IMAGE_MODELS,
    NSFW_IMAGE_MODEL_OPTIONS,
    SFW_IMAGE_MODEL_OPTIONS,
    NovelAIImageModel,
    NsfwImageModel,
    SfwImageModel,
    get_image_model_info,
    is_v5_image_model,
    resolve_user_image_model,
    supports_character_references,
)
from gateway.services.anlas_service import parse_novelai_usage


class TestRegistry:
    def test_v45_full_maps_to_own_inpainting(self) -> None:
        info = get_image_model_info("nai-diffusion-4-5-full", nsfw_mode=True)
        assert info.inpaint_model == "nai-diffusion-4-5-full-inpainting"
        assert info.sdk_base_model == "nai-diffusion-4-5-full"
        assert not info.is_v5
        assert info.family == "full"

    def test_v5_full_maps_to_v5_inpainting(self) -> None:
        info = get_image_model_info("nai-diffusion-5-full", nsfw_mode=True)
        assert info.inpaint_model == "nai-diffusion-5-full-inpainting"
        assert info.sdk_base_model == "nai-diffusion-4-5-full"
        assert info.is_v5
        assert info.family == "full"

    def test_v5_curated_quirk_maps_to_v45_curated_inpainting(self) -> None:
        # NovelAI 本家 UI の挙動を踏襲した意図的なマッピング
        info = get_image_model_info("nai-diffusion-5-curated", nsfw_mode=False)
        assert info.inpaint_model == "nai-diffusion-4-5-curated-inpainting"
        assert info.sdk_base_model == "nai-diffusion-4-5-curated"
        assert info.is_v5
        assert info.family == "curated"

    @pytest.mark.parametrize("nsfw_mode", [True, False])
    def test_unknown_name_falls_back_to_env_family(self, nsfw_mode: bool) -> None:
        info = get_image_model_info("custom-model", nsfw_mode=nsfw_mode)
        assert not info.is_v5
        assert info.family == ("full" if nsfw_mode else "curated")
        assert info.sdk_base_model == (
            DEFAULT_NSFW_IMAGE_MODEL if nsfw_mode else DEFAULT_SFW_IMAGE_MODEL
        )

    def test_option_tuples_are_v5_aware(self) -> None:
        assert NSFW_IMAGE_MODEL_OPTIONS == (
            "nai-diffusion-4-5-full",
            "nai-diffusion-5-full",
        )
        assert SFW_IMAGE_MODEL_OPTIONS == (
            "nai-diffusion-4-5-curated",
            "nai-diffusion-5-curated",
        )

    def test_is_v5_image_model(self) -> None:
        assert is_v5_image_model("nai-diffusion-5-full")
        assert is_v5_image_model("nai-diffusion-5-curated")
        assert not is_v5_image_model("nai-diffusion-4-5-full")
        assert not is_v5_image_model("unknown")
        assert not is_v5_image_model(None)
        assert not is_v5_image_model("")

    def test_literals_match_registry_and_options(self) -> None:
        assert set(NovelAIImageModel.__args__) == set(NOVELAI_IMAGE_MODELS)
        assert NsfwImageModel.__args__ == NSFW_IMAGE_MODEL_OPTIONS
        assert SfwImageModel.__args__ == SFW_IMAGE_MODEL_OPTIONS

    def test_supports_character_references_is_false_only_for_v5(self) -> None:
        assert not supports_character_references("nai-diffusion-5-full")
        assert not supports_character_references("nai-diffusion-5-curated")
        assert supports_character_references("nai-diffusion-4-5-full")
        assert supports_character_references("nai-diffusion-4-5-curated")
        # 未登録名・未指定は v4.5 相当として扱う
        assert supports_character_references("unknown")
        assert supports_character_references(None)


class TestResolveUserImageModel:
    def test_uses_user_settings_when_present(self) -> None:
        user_settings = {
            "novelai_image_model": "nai-diffusion-5-full",
            "novelai_curated_image_model": "nai-diffusion-5-curated",
        }
        assert resolve_user_image_model(user_settings, True) == "nai-diffusion-5-full"
        assert (
            resolve_user_image_model(user_settings, False) == "nai-diffusion-5-curated"
        )

    def test_missing_keys_fall_back_to_env_defaults(self) -> None:
        assert resolve_user_image_model({}, True) == DEFAULT_NSFW_IMAGE_MODEL
        assert resolve_user_image_model({}, False) == DEFAULT_SFW_IMAGE_MODEL

    def test_empty_values_fall_back_to_env_defaults(self) -> None:
        user_settings = {
            "novelai_image_model": "",
            "novelai_curated_image_model": None,
        }
        assert resolve_user_image_model(user_settings, True) == (
            DEFAULT_NSFW_IMAGE_MODEL
        )
        assert resolve_user_image_model(user_settings, False) == (
            DEFAULT_SFW_IMAGE_MODEL
        )


class TestParseNovelaiUsage:
    def test_parses_valid_usage(self) -> None:
        usage = parse_novelai_usage(
            {
                "usage": {
                    "percent": 99,
                    "isNegative": False,
                    "timeUntilNextPercent": 7888,
                }
            }
        )
        assert usage is not None
        assert usage.percent == 99
        assert usage.is_negative is False
        assert usage.time_until_next_percent == 7888

    def test_missing_usage_returns_none(self) -> None:
        assert parse_novelai_usage({"tier": 3}) is None
        assert parse_novelai_usage({}) is None
        assert parse_novelai_usage(None) is None

    def test_malformed_usage_returns_none(self) -> None:
        assert parse_novelai_usage({"usage": "broken"}) is None
        assert parse_novelai_usage({"usage": {"percent": "high"}}) is None
        assert parse_novelai_usage({"usage": {"isNegative": True}}) is None

    def test_partial_usage_defaults(self) -> None:
        usage = parse_novelai_usage({"usage": {"percent": 0}})
        assert usage is not None
        assert usage.percent == 0
        assert usage.is_negative is False
        assert usage.time_until_next_percent == 0
