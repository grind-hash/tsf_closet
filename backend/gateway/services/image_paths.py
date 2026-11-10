"""DB に保存された画像パス文字列を実ファイルへ解決する共通処理。

セッション・履歴・Adventure の開始素材はいずれも「data ディレクトリからの相対パス」
（history_images/... など）か「backend ディレクトリからの相対パス」
（images/characters/... など）で保存されている。旧データには絶対パスや
ファイル名だけのものも混じるため、候補を順に試して最初に存在したものを返す。

履歴画像を削除するときもこの解決を通す。保存されたパス文字列をそのまま Path に
すると作業ディレクトリ基準になり、data 相対のパスを見つけられない。
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..settings import config as _config

logger = logging.getLogger(__name__)

# 絶対パスで保存している data 配下のディレクトリ。配置先が変わったとき
# （ポータブル版を別フォルダの新バージョンへ移した等）に付け替える対象。
_RELOCATABLE_DATA_DIRS = ("adventure_images",)


def _relocated_data_path(raw: Path, data_dir: Path) -> Path | None:
    """別の data ディレクトリを指す絶対パスを、現在の data ディレクトリ配下へ付け替える。

    Adventure は画像パスを絶対パスで保存するため、旧バージョンのフォルダから
    data を引き継ぐと保存値が旧フォルダを指したままになる。パス中の
    既知のディレクトリ名（最後の出現）以降を現在の data ディレクトリへつなぐ。
    """
    parts = raw.parts
    for index in range(len(parts) - 2, -1, -1):
        if parts[index] in _RELOCATABLE_DATA_DIRS:
            return data_dir.joinpath(*parts[index:])
    return None


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
    4. 旧配置の絶対パスを現在の data ディレクトリへ付け替えたもの
       （adventure_images/<run_id>/... など）
    5. 履歴画像ディレクトリ直下の同名ファイル

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
    candidates = [
        settings.history_images_dir.parent / raw,
        _config.BASE_DIR / raw,
        raw,
    ]
    relocated = _relocated_data_path(raw, settings.history_images_dir.parent)
    if relocated is not None:
        candidates.append(relocated)
    candidates.append(images_dir / raw.name)
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def remove_history_image(raw_path: str | None) -> bool:
    """履歴画像ディレクトリ直下にある保存済み画像を削除する。

    履歴画像と周囲状況画像は常に履歴画像ディレクトリ直下に保存される。解決先が
    それ以外の場所（images/characters の同梱画像、custom/ の再利用キャラクター
    など）なら削除しない。

    Args:
        raw_path: DB に保存されたパス文字列。空や None なら何もしない。

    Returns:
        ファイルを削除したら True。見つからない・対象外・削除失敗なら False。
    """
    path = resolve_stored_image_path(raw_path)
    if path is None:
        return False
    history_dir = _config.settings.history_images_dir.resolve()
    if path.resolve().parent != history_dir:
        logger.warning("Skipped deleting image outside history dir: %s", path)
        return False
    try:
        path.unlink()
    except OSError as exc:
        logger.warning(
            "Failed to delete image %s: %s: %s", path, type(exc).__name__, exc
        )
        return False
    return True
