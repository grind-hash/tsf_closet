"""同梱のテンプレートキャラクター(images/characters/characters.json)の整合性。"""

from __future__ import annotations

from gateway.services.characters import CharacterManager
from gateway.settings.config import BASE_DIR

CHARACTERS_DIR = BASE_DIR / "images" / "characters"


def test_bundled_characters_have_images_and_tsf_attitude() -> None:
    characters = CharacterManager(CHARACTERS_DIR).get_all()
    ids = [character.id for character in characters]
    assert len(ids) == len(set(ids))
    assert {"char1", "char2", "char3", "char4"} <= set(ids)
    for character in characters:
        # 選択画面と開始画像に使う立ち絵が同梱されていること
        assert (BASE_DIR / character.image_path).is_file(), character.id
        assert character.gender in {"man", "woman"}
        assert character.pronoun
        # 依頼モードの依頼文と、頼んでいない体の変化への反応に使う
        assert character.tsf_attitude.strip(), character.id


def test_character_api_model_exposes_profile_for_welcome_screen() -> None:
    manager = CharacterManager(CHARACTERS_DIR)
    models = {model.id: model for model in manager.get_all_api_models()}
    kazuya = models["char3"]
    assert kazuya.pronoun == "俺"
    assert kazuya.personality
    assert kazuya.gender == "man"
    assert kazuya.tsf_attitude
