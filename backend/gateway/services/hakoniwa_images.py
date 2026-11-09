"""AI箱庭モードの画像(住民のアバター・ドレス姿・変身の姿)の保存と生成。

画像は世界ごとのフォルダ(data/hakoniwa/{world_id}/)に一意な名前で置き、API から配信する。
アバターは全身の立ち絵で、V5 系の NovelAI ではアルファ透過で生成する。それ以外のモデルや
プロバイダは白背景で生成し、表示側(ブラウザ)で単色の背景を抜く。
"""

from __future__ import annotations

import re
import shutil
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops

from ..consts.hakoniwa import (
    HAKONIWA_IMAGE_MODEL_DEFAULT,
    preset_bundled_avatar_url,
)
from ..consts.novelai_models import (
    NSFW_IMAGE_MODEL_OPTIONS,
    SFW_IMAGE_MODEL_OPTIONS,
    is_v5_image_model,
    resolve_user_image_model,
)
from ..settings.config import settings
from .clothing_layers import merge_negative_prompt
from .cost_tracker import record_cost
from .hakoniwa_logic import HakoniwaError, display_look, own_look
from .hakoniwa_scene import SCENE_EXTRA_NEGATIVE
from .image_generation import image_service
from .portrait_generation import generate_portrait_bytes
from .preset_sessions import portrait_png_bytes
from .prompts import enhance_prompt_for_novelai
from .providers import resolve_image_provider

_FILENAME = re.compile(r"^[a-z0-9_\-]+\.png$")
_WORLD_ID = re.compile(r"^[0-9a-f\-]{8,64}$")


def hakoniwa_root() -> Path:
    return settings.history_images_dir.parent / "hakoniwa"


def world_dir(world_id: str) -> Path:
    if not _WORLD_ID.match(world_id):
        raise HakoniwaError("world_not_found", "世界が見つかりません")
    return hakoniwa_root() / world_id


def image_url(world_id: str, filename: str) -> str:
    """API の配信 URL(/api は付けない。フロントが API_BASE を足す)。"""
    return f"/hakoniwa/worlds/{world_id}/images/{filename}"


def image_path(world_id: str, filename: str) -> Path:
    """配信する画像のパス。ファイル名を検証し、無ければ例外。"""
    name = Path(filename).name
    if name != filename or not _FILENAME.match(name):
        raise HakoniwaError("image_not_found", "画像が見つかりません")
    path = world_dir(world_id) / name
    if not path.is_file():
        raise HakoniwaError("image_not_found", "画像が見つかりません")
    return path


def save_image(world_id: str, prefix: str, data: bytes) -> str:
    """画像を一意な名前で保存し、ファイル名を返す。"""
    safe_prefix = re.sub(r"[^a-z0-9_]", "_", prefix.lower())
    filename = f"{safe_prefix}_{uuid.uuid4().hex[:10]}.png"
    directory = world_dir(world_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / filename).write_bytes(data)
    return filename


def copy_portrait(world_id: str, resident_id: str, source: Path) -> str:
    """キャラクターの立ち絵を世界のフォルダへ写す(元のキャラクターを消しても残る)。"""
    return save_image(world_id, f"avatar_{resident_id}", portrait_png_bytes(source))


def delete_world_images(world_id: str) -> None:
    try:
        directory = world_dir(world_id)
    except HakoniwaError:
        return
    shutil.rmtree(directory, ignore_errors=True)


def look_url(
    world_id: str, resident: dict[str, Any], look: dict[str, Any]
) -> str | None:
    """姿(own_look / display_look の戻り値)を表示用の URL にする。無ければ None。"""
    if look.get("file"):
        return image_url(world_id, str(look["file"]))
    if look.get("bundled") and resident.get("preset_id"):
        return preset_bundled_avatar_url(
            str(resident["preset_id"]), dress=look.get("kind") == "dress"
        )
    return None


def resident_image_urls(
    world_id: str, state: dict[str, Any], resident: dict[str, Any]
) -> dict[str, Any]:
    """住民の表示用の画像 URL 一式(表示中の姿・通常・ドレス)。"""
    by_id = {item["id"]: item for item in state["residents"]}
    look = display_look(state, resident)
    owner = by_id.get(look["owner"], resident)
    base_look = {
        "kind": "base",
        "file": resident.get("avatar_image"),
        "bundled": resident.get("source") == "preset",
    }
    dress_look = {
        "kind": "dress",
        "file": resident.get("dress_image"),
        "bundled": resident.get("source") == "preset"
        and not resident.get("dress_image"),
    }
    own = own_look(state, resident)
    return {
        "display_avatar_url": look_url(world_id, owner, look),
        "display_kind": look["kind"],
        "display_owner_id": look["owner"],
        "own_avatar_url": look_url(world_id, resident, own),
        "avatar_url": look_url(world_id, resident, base_look),
        "dress_avatar_url": look_url(world_id, resident, dress_look),
    }


def image_model_options(nsfw_mode: bool) -> tuple[str, ...]:
    return NSFW_IMAGE_MODEL_OPTIONS if nsfw_mode else SFW_IMAGE_MODEL_OPTIONS


def resolve_image_model(state: dict[str, Any], user_settings: dict[str, Any]) -> str:
    """世界の設定とユーザー設定から、アバター生成に使う NovelAI のモデルを決める。

    "default" や今の NSFW 設定で選べないモデルなら、ユーザー設定の画像モデルに従う。
    """
    nsfw_mode = bool(user_settings.get("nsfw_mode"))
    chosen = str(state.get("image_model") or HAKONIWA_IMAGE_MODEL_DEFAULT)
    if chosen in image_model_options(nsfw_mode):
        return chosen
    return resolve_user_image_model(user_settings, nsfw_mode)


def transparency_mode(image_model: str) -> str:
    """生成する画像の透過のしかた: native(V5 のアルファ透過)/ removal(白背景を抜く)。"""
    if str(resolve_image_provider()) == "novelai" and is_v5_image_model(image_model):
        return "native"
    return "removal"


# 1人の全身が正面を向いて立つ構図に寄せる(箱庭の同梱素材の生成で実績のある言い回し)
AVATAR_POSE_TAGS = "single character, head to toe, feet visible, facing viewer"
# 2人並び・比較の絵を避ける語。正のプロンプトに入れると逆に呼び込むため、ネガティブにだけ置く
AVATAR_EXTRA_NEGATIVE = (
    "split screen, side-by-side, comparison, before and after, multiple panels"
)

# 人物とみなす画素: 透過画像はアルファがこれ以上、白背景の画像は背景色との差がこれ以上
_FIGURE_ALPHA_MIN = 32
_FIGURE_COLOR_DIFF_MIN = 24
# 人物の列とみなす割合(列の高さに占める人物の画素)と、2人目とみなす幅の下限(画像幅に対して)
_COLUMN_COVERAGE_MIN = 0.02
_FIGURE_WIDTH_MIN = 0.15
# 2人が触れ合っているかを調べる塊の幅の下限と、谷とみなす深さ(両側の山の低い方に対する割合)
_PAIR_WIDTH_MIN = 0.45
_VALLEY_RATIO = 0.2
# 残す人物の大きさの下限(いちばん大きい人物に対する割合)
_KEEP_MASS_RATIO = 0.6


def _figure_mask(image: Image.Image) -> Image.Image:
    """人物の画素を 255、背景を 0 にしたマスク。透過があればアルファ、無ければ四隅の色との差で見る。"""
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A")
    if alpha.getextrema()[0] < 250:
        return alpha.point(lambda value: 255 if value >= _FIGURE_ALPHA_MIN else 0)
    rgb = rgba.convert("RGB")
    corner = rgb.getpixel((2, 2))
    background = Image.new("RGB", rgb.size, corner)
    diff = ImageChops.difference(rgb, background).convert("L")
    return diff.point(lambda value: 255 if value >= _FIGURE_COLOR_DIFF_MIN else 0)


def _column_profile(mask: Image.Image) -> list[float]:
    """列ごとの人物の画素の割合(0〜1)。"""
    width = mask.size[0]
    columns = mask.resize((width, 1), Image.BOX)
    return [columns.getpixel((x, 0)) / 255 for x in range(width)]


def _occupied_runs(profile: list[float]) -> list[tuple[int, int]]:
    """人物のいる列の連なり [(開始, 終了)] を左から返す。"""
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for x, coverage in enumerate(profile):
        occupied = coverage > _COLUMN_COVERAGE_MIN
        if occupied and start is None:
            start = x
        elif not occupied and start is not None:
            runs.append((start, x))
            start = None
    if start is not None:
        runs.append((start, len(profile)))
    return runs


def _split_at_valley(
    profile: list[float], run: tuple[int, int], width: int
) -> list[tuple[int, int]]:
    """手が触れて列が途切れない2人を、中ほどの深い谷で分ける。谷が無ければ run のまま。"""
    left, right = run
    span = right - left
    if span < width * _PAIR_WIDTH_MIN:
        return [run]
    window = max(1, width // 100)
    smoothed = [
        sum(profile[max(0, x - window) : x + window + 1])
        / len(profile[max(0, x - window) : x + window + 1])
        for x in range(left, right)
    ]
    middle = range(span // 4, span - span // 4)
    valley = min(middle, key=lambda index: smoothed[index])
    peak_left = max(smoothed[:valley] or [0.0])
    peak_right = max(smoothed[valley + 1 :] or [0.0])
    if smoothed[valley] > _VALLEY_RATIO * min(peak_left, peak_right):
        return [run]
    pieces = [(left, left + valley), (left + valley, right)]
    if any(end - begin < width * _FIGURE_WIDTH_MIN for begin, end in pieces):
        return [run]
    return pieces


def isolate_single_figure(data: bytes) -> bytes:
    """左右に並んだ複数の人物が描かれていたら、1人だけを中央に置き直す。

    V5 の全身・透過の生成では、同じ人物(や着衣・脱衣の比較)が横に2人並ぶことがある。
    人物の列が離れた塊、または中ほどの深い谷で分かれる塊が2つ以上(それぞれ画像幅の
    15% 以上)あるときだけ処理し、それ以外(1人・小物が離れているだけ)はそのまま返す。
    残すのは、十分な大きさ(最大の 60% 以上)がある中でいちばん左の人物
    (比較の絵では基本の姿が左に置かれやすい)。
    """
    with Image.open(BytesIO(data)) as source:
        image = source.convert("RGBA")
    mask = _figure_mask(image)
    width, height = image.size
    profile = _column_profile(mask)
    figures: list[tuple[int, int]] = []
    for run in _occupied_runs(profile):
        figures.extend(_split_at_valley(profile, run, width))
    figures = [run for run in figures if run[1] - run[0] >= width * _FIGURE_WIDTH_MIN]
    if len(figures) < 2:
        return data
    masses = [sum(profile[begin:end]) for begin, end in figures]
    largest = max(masses)
    left, right = next(
        run
        for run, mass in zip(figures, masses, strict=True)
        if mass >= largest * _KEEP_MASS_RATIO
    )
    margin = max(4, width // 100)
    left, right = max(0, left - margin), min(width, right + margin)
    figure = image.crop((left, 0, right, height))
    has_alpha = image.getchannel("A").getextrema()[0] < 250
    fill = (0, 0, 0, 0) if has_alpha else image.getpixel((2, 2))
    canvas = Image.new("RGBA", image.size, fill)
    canvas.paste(figure, ((width - figure.width) // 2, 0))
    output = BytesIO()
    canvas.save(output, format="PNG")
    return output.getvalue()


async def generate_avatar_bytes(
    tags: str, *, image_model: str, nsfw_mode: bool
) -> bytes:
    """全身の立ち絵を1枚生成する(V5 はアルファ透過、それ以外は白背景)。

    NovelAI にはタグだけを送る(raw_prompt)。共通の接尾辞の「no before/after panels,
    no side-by-side comparison, no twins」のような英文は、タグのモデルでは否定が効かず
    その語に引っ張られて、同じ人物が横に2人並ぶ絵になりやすいため。重複を避ける語は
    ネガティブ側にだけ置く。それでも2人並んだときは、1人だけを中央に置き直す。
    """
    data = await generate_portrait_bytes(
        tags=f"{tags.rstrip(', ')}, {AVATAR_POSE_TAGS}",
        nsfw_mode=nsfw_mode,
        provider=resolve_image_provider(),
        image_model=image_model,
        reference_bytes=None,
        extra_negative=AVATAR_EXTRA_NEGATIVE,
        transparent_background=True,
        raw_prompt=True,
    )
    return isolate_single_figure(data)


async def generate_scene_bytes(
    request: dict[str, Any], *, image_model: str, nsfw_mode: bool
) -> bytes:
    """場面絵(横長)を1枚生成する。NovelAI はキャラクター枠つき、それ以外は1行のプロンプト。

    request は hakoniwa_scene.scene_request の戻り値。料金は cost_tracker に記録する。
    """
    provider = str(resolve_image_provider())
    if provider == "novelai":
        negative = merge_negative_prompt(
            settings.novelai_negative_prompt, SCENE_EXTRA_NEGATIVE
        )
        result = await image_service.generate_image(
            enhance_prompt_for_novelai(request["prompt"], nsfw_mode=nsfw_mode),
            image_bytes=None,
            provider_override="novelai",
            negative_prompt=negative,
            nsfw_mode=nsfw_mode,
            characters=request["characters"],
            size_override="landscape",
            novelai_model_override=image_model,
            raw_prompt=True,
        )
    else:
        result = await image_service.generate_image(
            request["flat_prompt"],
            image_bytes=None,
            provider_override=provider,  # type: ignore[arg-type]
            nsfw_mode=nsfw_mode,
            size_override="landscape",
        )
    record_cost(result.cost_usd)
    if not result.images:
        raise HakoniwaError("image_generation_failed", "画像の生成に失敗しました")
    return result.images[0]
