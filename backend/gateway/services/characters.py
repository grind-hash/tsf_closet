"""
キャラクター管理

キャラクター定義の読み込みと画像データの取得を行う。
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

from ..models import Character
from ..schemas.characters import CharacterInfo
from ..settings.config import settings


class CharacterManager:
    """キャラクター管理クラス

    キャラクター定義ファイルの読み込みと画像データの取得を行う。
    """

    def __init__(self, characters_dir: Path | None = None) -> None:
        """初期化

        Args:
            characters_dir: キャラクター画像ディレクトリ
        """
        self.characters_dir = characters_dir or settings.characters_dir
        self._characters: list[Character] = []
        self._loaded = False

    def _load_characters(self) -> None:
        """キャラクター定義を読み込む"""
        if self._loaded:
            return

        config_path = self.characters_dir / "characters.json"
        if not config_path.exists():
            self._characters = []
            self._loaded = True
            return

        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)

        self._characters = [
            Character(
                id=item["id"],
                name=item["name"],
                image_path=item["image_path"],
                description=item["description"],
                pronoun=item.get("pronoun", "僕"),
                personality=item.get("personality", ""),
                gender=item.get("gender", "man"),
                base_tags=item.get("base_tags", ""),
            )
            for item in data
        ]
        self._loaded = True

    def get_all(self) -> list[Character]:
        """全キャラクターを取得

        Returns:
            キャラクターのリスト
        """
        self._load_characters()
        return self._characters

    def get_by_id(self, character_id: str) -> Character | None:
        """IDでキャラクターを取得

        Args:
            character_id: キャラクターID

        Returns:
            Character または None
        """
        self._load_characters()
        for char in self._characters:
            if char.id == character_id:
                return char
        return None

    def get_image_bytes(self, character: Character) -> bytes:
        """キャラクター画像のバイナリを取得

        Args:
            character: キャラクター

        Returns:
            画像バイナリ

        Raises:
            FileNotFoundError: 画像が見つからない場合
        """
        # image_pathは相対パス (例: "images/characters/char1.png")
        from ..settings.config import BASE_DIR

        image_path = BASE_DIR / character.image_path
        if not image_path.exists():
            raise FileNotFoundError(f"Character image not found: {image_path}")

        return image_path.read_bytes()

    def get_thumbnail_base64(self, character: Character) -> str:
        """キャラクターのサムネイルをBase64で取得

        Args:
            character: キャラクター

        Returns:
            Base64エンコードされた画像
        """
        try:
            image_bytes = self.get_image_bytes(character)
            return base64.b64encode(image_bytes).decode("utf-8")
        except FileNotFoundError:
            # プレースホルダー画像 (1x1 透明PNG)
            return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

    def to_api_model(self, character: Character) -> CharacterInfo:
        """キャラクターをAPI用モデルに変換

        Args:
            character: キャラクター

        Returns:
            CharacterInfo
        """
        return CharacterInfo(
            id=character.id,
            name=character.name,
            thumbnail=self.get_thumbnail_base64(character),
            description=character.description,
        )

    def get_all_api_models(self) -> list[CharacterInfo]:
        """全キャラクターをAPI用モデルで取得

        Returns:
            CharacterInfoのリスト
        """
        return [self.to_api_model(char) for char in self.get_all()]


# グローバルマネージャーインスタンス
character_manager = CharacterManager()
