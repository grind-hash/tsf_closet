"""game_service.py refactoring characterization tests.

Refactoring target functions:
- _enhance_novelai_prompt (Step 3: NovelAI quality tag + NSFW)
- settings.is_novelai_opus_mode (Step 4: Opus mode property)
- _resolve_image_path (Step 2: image path resolution)
- _stream_feeling (Step 1: feeling stream common helper)
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import pytest

# ---------------------------------------------------------------------------
# Step 3: NovelAI quality tag + NSFW keyword
# ---------------------------------------------------------------------------
# Before refactoring: this logic is inlined in 2 places.
# After refactoring:  GameService._enhance_novelai_prompt static method.
# These tests validate the combined behaviour (enhance + nsfw append).


class TestEnhanceNovelaiPrompt:
    """Test the NovelAI prompt enhancement + NSFW keyword logic."""

    def _enhance(self, prompt: str, nsfw_mode: bool) -> str:
        """Simulate the inline logic before refactoring."""
        from gateway.services.prompts import enhance_prompt_for_novelai

        result = enhance_prompt_for_novelai(prompt)
        if nsfw_mode and "nsfw" not in result.lower():
            result = result + ", nsfw"
        return result

    def test_adds_quality_tags_when_missing(self):
        result = self._enhance("1girl, solo, red dress", False)
        assert "very aesthetic" in result
        assert "best quality" in result

    def test_skips_quality_tags_when_present(self):
        prompt = "1girl, solo, very aesthetic, best quality"
        result = self._enhance(prompt, False)
        assert result == prompt

    def test_nsfw_appends_keyword(self):
        result = self._enhance("1girl, solo", True)
        assert result.endswith(", nsfw")

    def test_nsfw_skips_when_already_present(self):
        result = self._enhance("1girl, nsfw, solo", True)
        assert result.count("nsfw") == 1

    def test_empty_prompt(self):
        result = self._enhance("", False)
        assert "very aesthetic" in result

    def test_nsfw_case_insensitive(self):
        result = self._enhance("1girl, NSFW, solo", True)
        assert result.count("nsfw") + result.count("NSFW") == 1


class TestEnhanceNovelaiPromptRefactored:
    """Test the refactored static method directly."""

    def test_static_method_exists(self):
        from gateway.services.game_service import GameService

        assert hasattr(GameService, "_enhance_novelai_prompt")

    def test_adds_quality_and_nsfw(self):
        from gateway.services.game_service import GameService

        result = GameService._enhance_novelai_prompt("1girl, solo", True)
        assert "very aesthetic" in result
        assert "best quality" in result
        assert result.endswith(", nsfw")

    def test_no_nsfw_when_disabled(self):
        from gateway.services.game_service import GameService

        result = GameService._enhance_novelai_prompt("1girl, solo", False)
        assert "nsfw" not in result.lower()


# ---------------------------------------------------------------------------
# Step 4: NovelAI Opus mode property
# ---------------------------------------------------------------------------


class TestIsNovelaiOpusMode:
    """Test the NovelAI Opus mode condition."""

    def _check(self, image_provider: str, image_desc_provider: str) -> bool:
        """Simulate the inline condition before refactoring."""
        return image_provider == "novelai" and image_desc_provider == "novelai"

    def test_both_novelai_returns_true(self):
        assert self._check("novelai", "novelai") is True

    def test_image_provider_selfhost_returns_false(self):
        assert self._check("selfhost", "novelai") is False

    def test_description_provider_selfhost_returns_false(self):
        assert self._check("novelai", "selfhost") is False

    def test_both_selfhost_returns_false(self):
        assert self._check("selfhost", "selfhost") is False

    def test_openrouter_returns_false(self):
        assert self._check("openrouter", "openrouter") is False


# ---------------------------------------------------------------------------
# Step 2: Image path resolution
# ---------------------------------------------------------------------------


class TestResolveImagePath:
    """Test the 2-stage image path resolution logic.

    The logic tries:
      1. settings.history_images_dir.parent / path  (data-relative)
      2. BASE_DIR / path                            (base-dir-relative)
    Returns the resolved Path or None.
    """

    def _resolve(self, image_path: str, data_dir: Path, base_dir: Path) -> Path | None:
        """Simulate the inline resolution logic before refactoring."""
        p = data_dir / image_path
        if p.exists():
            return p
        p = base_dir / image_path
        if p.exists():
            return p
        return None

    def test_data_relative_found(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        img = data_dir / "history_images" / "test.png"
        img.parent.mkdir(parents=True)
        img.write_bytes(b"PNG_DATA")

        result = self._resolve("history_images/test.png", data_dir, tmp_path / "base")
        assert result is not None
        assert result.read_bytes() == b"PNG_DATA"

    def test_base_dir_fallback(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        img = base_dir / "images" / "characters" / "char1.png"
        img.parent.mkdir(parents=True)
        img.write_bytes(b"CHAR_IMG")

        result = self._resolve("images/characters/char1.png", data_dir, base_dir)
        assert result is not None
        assert result.read_bytes() == b"CHAR_IMG"

    def test_not_found_returns_none(self, tmp_path: Path):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        base_dir = tmp_path / "base"
        base_dir.mkdir()

        result = self._resolve("nonexistent/file.png", data_dir, base_dir)
        assert result is None

    def test_data_relative_takes_priority(self, tmp_path: Path):
        """If file exists in both locations, data-relative wins."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        (data_dir / "img.png").write_bytes(b"DATA_VER")

        base_dir = tmp_path / "base"
        base_dir.mkdir()
        (base_dir / "img.png").write_bytes(b"BASE_VER")

        result = self._resolve("img.png", data_dir, base_dir)
        assert result is not None
        assert result.read_bytes() == b"DATA_VER"


# ---------------------------------------------------------------------------
# Step 1: Feeling stream common helper
# ---------------------------------------------------------------------------


class TestStreamFeeling:
    """Test the common feeling stream pattern.

    The pattern is:
    1. Append language rules to system_prompt
    2. Iterate llm_service.generate_feeling_stream
    3. On error, yield fallback text based on language
    """

    @pytest.fixture(autouse=True)
    def _mock_memory_text(self, monkeypatch):
        # use_memory 既定 True の経路が settings_service 経由で DB へ到達するため、
        # 未初期化 DB でも動くようメモリテキスト取得をモックする
        monkeypatch.setattr(
            "gateway.services.game_service.settings_service.get_memory_text",
            AsyncMock(return_value=""),
        )

    @pytest.mark.asyncio
    async def test_yields_chunks_from_llm(self, monkeypatch):
        """Normal path: chunks from LLM are yielded."""
        chunks_sent = ["Hello", " world"]

        async def fake_stream(system_prompt, user_prompt, **_kwargs):
            for c in chunks_sent:
                yield c

        monkeypatch.setattr(
            "gateway.services.game_service.llm_service.generate_feeling_stream",
            fake_stream,
        )

        from gateway.services.game_service import GameService

        svc = GameService()
        collected = []
        async for chunk in svc._generate_feeling_stream(
            before_desc="before",
            after_desc="after",
            instruction="test",
            pronoun="僕",
            language="ja",
        ):
            collected.append(chunk)

        assert collected == chunks_sent

    @pytest.mark.asyncio
    async def test_language_rules_appended(self, monkeypatch):
        """system_prompt passed to LLM includes language rules."""
        captured_system = []

        async def fake_stream(system_prompt, user_prompt, **_kwargs):
            captured_system.append(system_prompt)
            return
            yield  # make it a generator

        monkeypatch.setattr(
            "gateway.services.game_service.llm_service.generate_feeling_stream",
            fake_stream,
        )

        from gateway.services.game_service import GameService

        svc = GameService()
        async for _ in svc._generate_feeling_stream(
            before_desc="b",
            after_desc="a",
            instruction="i",
            pronoun="僕",
            language="en",
        ):
            pass

        assert len(captured_system) == 1
        # English language rules should be appended
        assert (
            "English" in captured_system[0] or "english" in captured_system[0].lower()
        )

    @pytest.mark.asyncio
    async def test_error_fallback_ja(self, monkeypatch):
        """On LLM error with ja, yield Japanese fallback."""
        from gateway.services.llm_service import LLMServiceError

        async def fake_stream(system_prompt, user_prompt, **_kwargs):
            raise LLMServiceError("test error")
            yield  # make it a generator

        monkeypatch.setattr(
            "gateway.services.game_service.llm_service.generate_feeling_stream",
            fake_stream,
        )

        from gateway.services.game_service import GameService

        svc = GameService()
        collected = []
        async for chunk in svc._generate_feeling_stream(
            before_desc="b",
            after_desc="a",
            instruction="i",
            pronoun="僕",
            language="ja",
        ):
            collected.append(chunk)

        assert collected == ["(心境生成に失敗しました)"]


# ── Step 1 post-refactoring: GameService._stream_feeling ──


class TestStreamFeelingRefactored:
    """Verify the extracted _stream_feeling helper method."""

    @pytest.mark.asyncio
    async def test_yields_chunks(self, monkeypatch):
        chunks = ["Hello", " World"]

        async def fake_stream(system_prompt, user_prompt, **_kwargs):
            for c in chunks:
                yield c

        monkeypatch.setattr(
            "gateway.services.game_service.llm_service.generate_feeling_stream",
            fake_stream,
        )

        from gateway.services.game_service import GameService

        svc = GameService()
        collected = []
        async for chunk in svc._stream_feeling(
            system_prompt="sys",
            user_prompt="usr",
            language="ja",
        ):
            collected.append(chunk)

        assert collected == chunks

    @pytest.mark.asyncio
    async def test_error_fallback_ja(self, monkeypatch):
        from gateway.services.llm_service import LLMServiceError

        async def fake_stream(system_prompt, user_prompt, **_kwargs):
            raise LLMServiceError("fail")
            yield

        monkeypatch.setattr(
            "gateway.services.game_service.llm_service.generate_feeling_stream",
            fake_stream,
        )

        from gateway.services.game_service import GameService

        svc = GameService()
        collected = []
        async for chunk in svc._stream_feeling(
            system_prompt="sys",
            user_prompt="usr",
            language="ja",
        ):
            collected.append(chunk)

        assert collected == ["(心境生成に失敗しました)"]

    @pytest.mark.asyncio
    async def test_error_fallback_en(self, monkeypatch):
        from gateway.services.llm_service import LLMServiceError

        async def fake_stream(system_prompt, user_prompt, **_kwargs):
            raise LLMServiceError("fail")
            yield

        monkeypatch.setattr(
            "gateway.services.game_service.llm_service.generate_feeling_stream",
            fake_stream,
        )

        from gateway.services.game_service import GameService

        svc = GameService()
        collected = []
        async for chunk in svc._stream_feeling(
            system_prompt="sys",
            user_prompt="usr",
            language="en",
        ):
            collected.append(chunk)

        assert collected == ["(Failed to generate inner monologue)"]


# ── Step 2 post-refactoring: GameService._resolve_image_path ──


class TestResolveImagePathRefactored:
    """Verify the extracted _resolve_image_path static method."""

    def test_data_relative_found(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        img = data_dir / "history_images" / "test.png"
        img.parent.mkdir(parents=True)
        img.write_bytes(b"PNG_DATA")

        from gateway.settings.config import settings

        monkeypatch.setattr(settings, "history_images_dir", data_dir / "history_images")

        from gateway.services.game_service import GameService

        result = GameService._resolve_image_path("history_images/test.png")
        assert result is not None
        assert result.read_bytes() == b"PNG_DATA"

    def test_base_dir_fallback(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        base_dir = tmp_path / "base"
        base_dir.mkdir()
        img = base_dir / "images" / "characters" / "char1.png"
        img.parent.mkdir(parents=True)
        img.write_bytes(b"CHAR_IMG")

        from gateway.settings.config import settings

        monkeypatch.setattr(settings, "history_images_dir", data_dir / "history_images")
        import gateway.settings.config as cfg_mod

        monkeypatch.setattr(cfg_mod, "BASE_DIR", base_dir)

        from gateway.services.game_service import GameService

        result = GameService._resolve_image_path("images/characters/char1.png")
        assert result is not None
        assert result.read_bytes() == b"CHAR_IMG"

    def test_not_found_returns_none(self, tmp_path, monkeypatch):
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        base_dir = tmp_path / "base"
        base_dir.mkdir()

        from gateway.settings.config import settings

        monkeypatch.setattr(settings, "history_images_dir", data_dir / "history_images")
        import gateway.settings.config as cfg_mod

        monkeypatch.setattr(cfg_mod, "BASE_DIR", base_dir)

        from gateway.services.game_service import GameService

        result = GameService._resolve_image_path("nonexistent/file.png")
        assert result is None


# ── Step 4 post-refactoring: Settings.is_novelai_opus_mode property ──


class TestIsNovelaiOpusModeRefactored:
    """Verify the actual property on Settings."""

    def test_both_novelai_returns_true(self, monkeypatch):
        from gateway.settings.config import settings

        monkeypatch.setattr(settings, "image_provider", "novelai")
        monkeypatch.setattr(settings, "image_description_provider", "novelai")
        assert settings.is_novelai_opus_mode is True

    def test_image_not_novelai_returns_false(self, monkeypatch):
        from gateway.settings.config import settings

        monkeypatch.setattr(settings, "image_provider", "comfyui")
        monkeypatch.setattr(settings, "image_description_provider", "novelai")
        assert settings.is_novelai_opus_mode is False

    def test_desc_not_novelai_returns_false(self, monkeypatch):
        from gateway.settings.config import settings

        monkeypatch.setattr(settings, "image_provider", "novelai")
        monkeypatch.setattr(settings, "image_description_provider", "openai")
        assert settings.is_novelai_opus_mode is False


class TestStreamFeelingErrorFallback:
    """Remaining feeling stream error/mode tests."""

    @pytest.fixture(autouse=True)
    def _mock_memory_text(self, monkeypatch):
        # use_memory 既定 True の経路が settings_service 経由で DB へ到達するため、
        # 未初期化 DB でも動くようメモリテキスト取得をモックする
        monkeypatch.setattr(
            "gateway.services.game_service.settings_service.get_memory_text",
            AsyncMock(return_value=""),
        )

    @pytest.mark.asyncio
    async def test_error_fallback_en(self, monkeypatch):
        """On LLM error with en, yield English fallback."""
        from gateway.services.llm_service import LLMServiceError

        async def fake_stream(system_prompt, user_prompt, **_kwargs):
            raise LLMServiceError("test error")
            yield

        monkeypatch.setattr(
            "gateway.services.game_service.llm_service.generate_feeling_stream",
            fake_stream,
        )

        from gateway.services.game_service import GameService

        svc = GameService()
        collected = []
        async for chunk in svc._generate_feeling_stream(
            before_desc="b",
            after_desc="a",
            instruction="i",
            pronoun="僕",
            language="en",
        ):
            collected.append(chunk)

        assert collected == ["(Failed to generate inner monologue)"]

    @pytest.mark.asyncio
    async def test_self_mode_yields_chunks(self, monkeypatch):
        """Self-mode stream yields chunks correctly."""
        chunks_sent = ["Self", " chunk"]

        async def fake_stream(system_prompt, user_prompt, **_kwargs):
            for c in chunks_sent:
                yield c

        monkeypatch.setattr(
            "gateway.services.game_service.llm_service.generate_feeling_stream",
            fake_stream,
        )

        from gateway.services.game_service import GameService

        svc = GameService()
        collected = []
        async for chunk in svc._generate_self_mode_feeling_stream(
            before_desc="before",
            after_desc="after",
            instruction="test",
            self_profile={"personality": "shy", "pronoun": "僕"},
            language="ja",
        ):
            collected.append(chunk)

        assert collected == chunks_sent

    @pytest.mark.asyncio
    async def test_reality_mode_error_fallback_ja(self, monkeypatch):
        """Reality mode error yields Japanese fallback."""
        from gateway.services.llm_service import LLMServiceError

        async def fake_stream(system_prompt, user_prompt, **_kwargs):
            raise LLMServiceError("test error")
            yield

        monkeypatch.setattr(
            "gateway.services.game_service.llm_service.generate_feeling_stream",
            fake_stream,
        )

        from gateway.services.game_service import GameService

        svc = GameService()
        collected = []
        async for chunk in svc._generate_reality_feeling_stream(
            before_desc="b",
            after_desc="a",
            instruction="i",
            pronoun="僕",
            language="ja",
        ):
            collected.append(chunk)

        assert collected == ["(心境生成に失敗しました)"]
