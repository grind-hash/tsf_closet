"""DB に保存された画像パス文字列を実ファイルへ解決する共通処理。

セッション・履歴・Adventure の開始素材はいずれも「data ディレクトリからの相対パス」
（history_images/... など）か「backend ディレクトリからの相対パス」
（images/characters/... など）で保存されている。旧データには絶対パスや
ファイル名だけのものも混じるため、候補を順に試して最初に存在したものを返す。
"""

from __future__ import annotations

from pathlib import Path

from ..settings import config as _config


def resolve_stored_image_path(
    raw_path: str | None,
    *,
    history_images_dir: Path | None = None,
) -> Path | None:
    """保存された画像パス文字列から存在するファイルを探す。

    候補の順序:
    1. data ディレクトリ相対（history_images 等）
    2. BASE_DIR（backend/）相対（キャラクター画像等）
    3. 文字列どおり（絶対パス・作業ディレクトリ相対）
    4. 履歴画像ディレクトリ直下の同名ファイル

    Args:
        raw_path: DB に保存されたパス文字列。空や None なら None を返す。
        history_images_dir: 履歴画像ディレクトリ。省略時は設定値。

    Returns:
        見つかったファイルの Path。見つからなければ None。
    """
    if not raw_path:
        return None
    settings = _config.settings
    images_dir = history_images_dir or settings.history_images_dir
    raw = Path(raw_path)
    candidates = (
        settings.history_images_dir.parent / raw,
        _config.BASE_DIR / raw,
        raw,
        images_dir / raw.name,
    )
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None
