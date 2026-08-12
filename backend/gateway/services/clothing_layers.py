"""衣装レイヤーの可視性ルールと着用インベントリ補助。

露出・確認の可否はキーワード判定せず LLM に任せる。
コード側は次だけを担う:
- WORN_UNDER_LAYERS の分離 / 画像送信用 strip
- 下着着用事実の継続（previous inventory の継承）
- visual に下着が無い覆い状態への negative 付与
"""

from __future__ import annotations

import re

WORN_UNDER_LAYERS_MARKER = "WORN_UNDER_LAYERS:"

CLOTHING_LAYER_COVERED_NEGATIVE = (
    "braless, no bra, no panties, nipples, erect nipples, underboob, "
    "visible bra, bra strap, panties, underwear, lingerie, clothes lift, clothes pull"
)

# 下着系タグ判定（braid/bracelet 等は除外）— inventory 機械処理用
_UNDERGARMENT_HINTS = (
    "sports bra",
    "strapless bra",
    "lace bra",
    "push-up bra",
    "shelf bra",
    "bra",
    "panties",
    "panty",
    "underwear",
    "lingerie",
    "thong",
    "g-string",
    "boyshorts",
    "camisole",
)

_UNDERGARMENT_EXCLUDE = (
    "braid",
    "braided",
    "bracelet",
    "bracer",
    "brass instrument",
)

CLOTHING_LAYER_IMAGE_RULE = """

## CLOTHING LAYER VISIBILITY (HIGHEST PRIORITY)
You decide visibility from the CURRENT user instruction. Do not rely on fixed keyword lists alone—interpret intent.

### Persistent facts
- Every listed garment is a persistent worn fact. Covered does NOT mean removed.
- Layer order (inner → outer): body/anatomy, underwear, inner garments, outer garments.
- Outer-only outfit changes are NOT a full wardrobe wipe. Keep prior underwear unless the user clearly removes it.

### Two channels (required format)
1) Positive visual tags: only what should appear in the image.
2) State inventory line at the end (always keep worn undergarments here when they still exist):
   WORN_UNDER_LAYERS: <comma-separated worn undergarments with colors/types>

### NovelAI / Danbooru constraint
- Tags like `bra`, `panties`, `underwear` make undergarments VISIBLE. Use them in positive tags only when they should be seen.
- When undergarments should stay fully covered: omit them from positive tags; keep them only in WORN_UNDER_LAYERS.

### Default (no reveal intent)
- Outer garments stay properly worn and cover layers beneath.
- Do not open, lift, pull aside, or make clothing transparent just to show underwear.
- Tight clothes: silhouette only; no underwear/genital/pubic-hair detail.
- Never imply braless / no panties under ordinary clothes unless asked.

### Reveal / check / sheer / undress (when user intent says so)
- If the user wants to shift, lift, open, peek, check underwear color/straps, undress, or use sheer/see-through fabric:
  1. Put the relevant undergarments into positive visual tags (preserve colors/types from WORN_UNDER_LAYERS / previous state).
  2. Depict the action so they are actually visible (limited to the requested area).
  3. Do not stubbornly keep full coverage against that intent.
  4. Still keep WORN_UNDER_LAYERS for items that remain worn.
- If intent is ambiguous, prefer covered (inventory only) over accidental exposure.
"""

CLOTHING_LAYER_FEELING_RULE = """

【衣装レイヤーの認識ルール（最優先）】
見え方は現在のユーザー指示の意図から判断する。固定キーワードの有無だけに頼らない。

- 身体属性、下着、内側の服、外衣はすべて実在する状態として保持する。覆われていることは脱いだことを意味しない。
- 直前の状態や WORN_UNDER_LAYERS にあった下着は、指示が脱衣・除去を意味しない限り、今も着用中として扱う。
- 画像用タグに下着が無くても、それは「今は見えていない」だけであり、自動的な脱衣ではない。
- 外衣の指示だけを、下着を含む全身置換と解釈しない。外衣は下着の上に重ね着する。
- 指示が覆いを維持する意図なら: 下着は着用・布越しの感触としてのみ書き、見えている／露出しているとは書かない。
- 指示がずらす・めくる・確認する・透ける・脱ぐなどの意図なら: その範囲では見えた事実・色・感触を書いてよい。頑なに「見えない」と打ち消さない。
- 下着なし直着は、指示がその意図を持つとき以外は禁止する。
- 意図が曖昧なら、不用意な露出描写より覆われた着用状態を優先する。
"""


def append_clothing_layer_image_rule(
    system_prompt: str, respect_clothing_layers: bool
) -> str:
    """有効時だけ画像用の衣装レイヤールールを追加する。"""
    if not respect_clothing_layers:
        return system_prompt
    return system_prompt + CLOTHING_LAYER_IMAGE_RULE


def append_clothing_layer_feeling_rule(
    system_prompt: str, respect_clothing_layers: bool
) -> str:
    """有効時だけ心境用の衣装レイヤールールを追加する。"""
    if not respect_clothing_layers:
        return system_prompt
    return system_prompt + CLOTHING_LAYER_FEELING_RULE


def split_worn_under_layers(text: str) -> tuple[str, str]:
    """プロンプトを visual 部分と WORN_UNDER_LAYERS に分割する。"""
    if not text:
        return "", ""
    marker = WORN_UNDER_LAYERS_MARKER
    pattern = re.compile(
        rf"(?:^|\n)\s*{re.escape(marker)}\s*(.*)$",
        re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return text.strip(), ""
    visual = text[: match.start()].strip()
    inventory = match.group(1).strip()
    inventory = inventory.split("\n\n")[0].strip()
    inventory = " ".join(inventory.splitlines()).strip(" ,")
    return visual, inventory


def append_worn_under_layers(visual_prompt: str, inventory: str) -> str:
    """visual プロンプトに着用インベントリ行を付与する。"""
    visual = (visual_prompt or "").strip()
    inv = (inventory or "").strip(" ,")
    if not inv:
        return visual
    if not visual:
        return f"{WORN_UNDER_LAYERS_MARKER} {inv}"
    return f"{visual}\n\n{WORN_UNDER_LAYERS_MARKER} {inv}"


def strip_worn_under_layers_for_image(text: str) -> str:
    """画像API送信用に WORN_UNDER_LAYERS を除去する。"""
    visual, _inventory = split_worn_under_layers(text or "")
    return visual


def _normalize_tag(tag: str) -> str:
    return re.sub(r"\s+", " ", tag.strip().strip(","))


def _tag_tokens(text: str) -> list[str]:
    if not text:
        return []
    parts = re.split(r",(?![^\(]*\))", text)
    return [_normalize_tag(p) for p in parts if _normalize_tag(p)]


def split_tag_tokens(text: str) -> list[str]:
    """カンマ区切りのプロンプトをタグ単位へ分解する。"""
    return _tag_tokens(text)


def normalize_tag_for_match(tag: str) -> str:
    """重み記法や括弧を外し、語の照合に使える小文字表記へ整える。"""
    t = tag.lower()
    t = re.sub(r"\d+(?:\.\d+)?::", "", t)
    t = t.replace("::", " ")
    t = re.sub(r"[{}\[\]\(\)]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def is_undergarment_tag(tag: str) -> bool:
    """タグが下着・インナー寄りかを判定する。"""
    t = normalize_tag_for_match(tag)
    if not t:
        return False
    for ex in _UNDERGARMENT_EXCLUDE:
        if ex in t:
            return False
    for hint in _UNDERGARMENT_HINTS:
        if re.search(rf"\b{re.escape(hint)}\b", t):
            return True
    return False


def extract_undergarment_tags(text: str) -> str:
    """テキストから下着タグをカンマ区切りで抽出する。"""
    visual, inventory = split_worn_under_layers(text or "")
    found: list[str] = []
    seen: set[str] = set()

    def _add(tag: str) -> None:
        key = tag.lower()
        if key in seen:
            return
        if is_undergarment_tag(tag):
            seen.add(key)
            found.append(tag)

    if inventory:
        for tok in _tag_tokens(inventory):
            _add(tok)
    for tok in _tag_tokens(visual):
        _add(tok)
    return ", ".join(found)


def peel_undergarment_tags(visual_prompt: str) -> tuple[str, str]:
    """visual から下着タグを剥がし、(残り, 下着CSV) を返す。"""
    kept: list[str] = []
    moved: list[str] = []
    for tok in _tag_tokens(visual_prompt):
        if is_undergarment_tag(tok):
            moved.append(tok)
        else:
            kept.append(tok)
    return ", ".join(kept), ", ".join(moved)


def merge_inventory(*parts: str) -> str:
    """複数インベントリを重複なく結合する。"""
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        for tok in _tag_tokens(part or ""):
            key = tok.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(tok)
    return ", ".join(out)


def ensure_worn_under_layers(
    prompt: str,
    previous_prompt: str | None = None,
    *,
    respect_clothing_layers: bool = False,
    instruction: str = "",
) -> str:
    """レイヤーON時、着用インベントリを機械的に整える。

    露出の可否は LLM の visual / inventory 配置に従う。
    コードは状態継続とチャネル整形だけを行う。

    - visual に下着がある → 見せる意図として残す（剥がさない）
    - inventory のみ → 覆われた着用として残す
    - どちらにも無い → previous の inventory を継承（visual には戻さない）
    - visual の下着は inventory にもミラーして次ターンへ渡す

    instruction は互換のため受け取るが、キーワード判定には使わない。
    """
    del instruction  # 露出判定は LLM に委任
    if not respect_clothing_layers:
        return prompt or ""

    visual, inventory = split_worn_under_layers(prompt or "")
    prev_visual, prev_inventory = split_worn_under_layers(previous_prompt or "")
    if not prev_inventory:
        prev_inventory = extract_undergarment_tags(prev_visual or previous_prompt or "")

    visual_under = extract_undergarment_tags(visual)
    inventory = merge_inventory(inventory, visual_under)

    if not inventory and prev_inventory:
        # 状態継続のみ。見せるかどうかは LLM が visual に載せたかで決まる。
        inventory = prev_inventory

    return append_worn_under_layers(visual, inventory)


def clothing_layer_negative_suffix(
    prompt_or_inventory: str,
    *,
    respect_clothing_layers: bool,
    instruction: str = "",
) -> str:
    """visual に下着が無く inventory だけある覆い状態のとき extra negative を返す。

    instruction は互換のため受け取るが、キーワード判定には使わない。
    """
    del instruction
    if not respect_clothing_layers:
        return ""
    visual, inventory = split_worn_under_layers(prompt_or_inventory or "")
    if not inventory.strip():
        return ""
    # LLM が visual に下着を載せた = 見せる意図 → 被覆 negative は付けない
    if extract_undergarment_tags(visual):
        return ""
    return CLOTHING_LAYER_COVERED_NEGATIVE


def merge_negative_prompt(base: str | None, extra: str) -> str | None:
    """negative prompt を結合する。"""
    extra = (extra or "").strip(" ,")
    base_s = (base or "").strip(" ,")
    if not extra:
        return base if base_s else None
    if not base_s:
        return extra
    return f"{base_s}, {extra}"


def strip_characters_worn_under_layers(
    characters: list[dict] | None,
) -> list[dict] | None:
    """V4 characters の各 prompt から inventory を除去する。"""
    if not characters:
        return characters
    stripped: list[dict] = []
    for char in characters:
        item = dict(char)
        if "prompt" in item and isinstance(item["prompt"], str):
            item["prompt"] = strip_worn_under_layers_for_image(item["prompt"])
        stripped.append(item)
    return stripped


def ensure_characters_worn_under_layers(
    characters: list[dict] | None,
    previous_prompt: str | None = None,
    *,
    respect_clothing_layers: bool = False,
    instruction: str = "",
) -> list[dict] | None:
    """V4 characters の各 prompt に ensure を適用する。"""
    if not characters or not respect_clothing_layers:
        return characters
    ensured: list[dict] = []
    for char in characters:
        item = dict(char)
        if "prompt" in item and isinstance(item["prompt"], str):
            item["prompt"] = ensure_worn_under_layers(
                item["prompt"],
                previous_prompt,
                respect_clothing_layers=True,
                instruction=instruction,
            )
        ensured.append(item)
    return ensured


def any_character_inventory(characters: list[dict] | None) -> str:
    """characters から inventory を結合して返す。"""
    if not characters:
        return ""
    parts: list[str] = []
    for char in characters:
        prompt = char.get("prompt")
        if isinstance(prompt, str):
            _v, inv = split_worn_under_layers(prompt)
            if inv:
                parts.append(inv)
    return merge_inventory(*parts)
