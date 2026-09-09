"""Adventure の同一性タグ署名(identity signature)。

立ち絵と合成シーンのキャラクター枠へ、同じ同一性タグ(性別・髪・瞳・肌・体型・
特徴)を同じ順序で先頭注入し、精密参照(Anlas 消費)無しで同一人物性を保つ。
NovelAI 公式の "Creating Consistent Characters"(同一性タグを固定し構図だけ変える)
と "Multi-Character Prompting"(枠ごとの undesired content で属性の混入を防ぐ)を
機械化したもの。純関数だけで構成し、state の読み書きは adventure_service が行う。

署名は不変ではない。現実改変・変身・手編集で姿が変わった手番は adventure_service
が作り直す。この module はタグの分類・並べ替え・注入だけを担当する。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from .clothing_layers import normalize_tag_for_match, split_tag_tokens
from .source_snapshot import CLOTHING_TAG_PATTERN, SCENE_OR_ACTION_TAG_PATTERN

# 署名の上限(AdventureImagePromptOutput.identity_tags の max_length と一致)
SIGNATURE_MAX_LENGTH = 400
# 注入後の player_tags / npc_tags の上限(AdventureImagePromptOutput.player_tags)
PLAYER_TAGS_MAX_LENGTH = 1200

# 署名内の並び順(NovelAI 公式チュートリアルの「上から下へ」に合わせる)
CATEGORY_ORDER = (
    "sex",
    "species_age",
    "hair_color",
    "hair_length",
    "hairstyle",
    "eyes",
    "skin",
    "body",
    "marks",
    "face",
)

# 枠別 negative に使うカテゴリ(他キャラの値が混入すると目立つもの)
_NEGATIVE_CATEGORIES = ("hair_color", "hair_length", "eyes", "skin")

# --- 同一性にしないタグ(guard) -------------------------------------------------
# 一時的な髪の状態、髪飾り・装身具・化粧、表情としての目、肌の状態、体毛など。
# 署名に入れると全ての絵へ強制されるため、場面ごとの LLM 出力に任せる
_GUARD_WHOLE = frozenset(
    {
        "wet hair",
        "messy hair",
        "disheveled hair",
        "tousled hair",
        "windblown hair",
        "floating hair",
        "hair spread out",
        "hair down",
        "hair up",
        "hair over shoulder",
        "hair flip",
        "hair pull",
        "hair grab",
        "pubic hair",
        "stray pubic hair",
        "armpit hair",
        "chest hair",
        "arm hair",
        "leg hair",
        "body hair",
        "raised eyebrows",
        "furrowed brow",
        "furrowed eyebrows",
        "eye contact",
        "crying",
        "squinting",
    }
)
_GUARD_WORDS = re.compile(
    r"\b(?:ornaments?|ribbons?|bows?|headband|hairband|hairpins?|hairclips?|"
    r"hair clip|hair tie|hair tubes|hair stick|flowers?|scrunchie|bells?|"
    r"earrings?|piercings?|eyepatch|glasses|sunglasses|monocle|makeup|lipstick|"
    r"eyeshadow|eyeliner|mascara|blush|tan ?lines|shiny skin|sweaty skin|"
    r"skin ?tight|skindentation|goosebumps)\b"
)
_EYE_WORD = re.compile(r"\b(?:eyes?|pupils?|eyelids?)\b")
_EYE_STATE = re.compile(
    r"\b(?:closed|half-closed|narrowed|empty|hollow|rolling|teary|glowing|"
    r"sparkling|blank|covered|wide|shaded|hidden|heart-shaped|x-shaped|spiral|"
    r"dilated|constricted|averted|looking|one eye)\b"
)

# --- カテゴリ判定 ----------------------------------------------------------------
_SPECIES = re.compile(
    r"\b(?:elf|elves|dark elf|high elf|half-elf|demon|succubus|incubus|vampire|"
    r"catgirl|cat girl|foxgirl|fox girl|wolf girl|dog girl|kemonomimi|"
    r"monster girl|angel|fairy|mermaid|android|robot|cyborg|ghost|oni|kitsune|"
    r"dragon girl|lamia|slime girl|goblin|orc|dwarf|giantess|werewolf|zombie)\b"
)
# 年齢はタグ全体一致だけ(old-fashioned 等の誤検出を避ける)
_AGE_WHOLE = frozenset(
    {
        "mature",
        "milf",
        "elderly",
        "old",
        "old woman",
        "old man",
        "young",
        "teenage",
        "adult",
        "middle-aged",
        "aged up",
        "aged down",
        "mature female",
        "mature male",
    }
)
_FACE = re.compile(
    r"\b(?:eyebrows|eyelashes|beard|mustache|moustache|goatee|stubble|"
    r"facial hair|sideburns|dimples|thick lips|full lips|thin lips|big nose|"
    r"small nose|pointy nose|round face|square jaw|strong jaw|high cheekbones)\b"
)
_HAIR_WORD = re.compile(r"\bhair\b")
_HAIRED = re.compile(r"\b[a-z]+-haired\b")
_COLOR = re.compile(
    r"\b(?:black|brown|blonde|blond|red|orange|blue|purple|violet|pink|green|"
    r"white|silver|grey|gray|aqua|teal|cyan|lavender|platinum|auburn|ginger|"
    r"golden|gold|crimson|navy|ash|chestnut|honey|copper|dark|light|"
    r"multicolored|two-tone|gradient|streaked|rainbow|amber|hazel|yellow|"
    r"colored inner)\b"
)
_HAIR_LENGTH = re.compile(
    r"\b(?:very short|short|medium|long|very long|absurdly long|"
    r"shoulder-length|waist-length|hip-length|knee-length|floor-length|"
    r"chin-length|neck-length)\b"
)
_HAIR_LENGTH_WHOLE = frozenset({"bald", "shaved head"})
_HAIRSTYLE = re.compile(
    r"\b(?:ponytail|twintails|twin tails|braids?|buns?|drills?|bob cut|bob|"
    r"pixie cut|hime cut|undercut|mohawk|dreadlocks|afro|sidelocks?|ahoge|"
    r"antenna hair|bangs|fringe|updo|topknot|chignon|ringlets|one side up|"
    r"two side up|half up|side up|crew cut|buzz cut|slicked back|slicked-back|"
    r"pompadour|curly|wavy)\b"
)
_EYES_SHAPE = re.compile(
    r"\b(?:tareme|tsurime|jitome|sanpaku|heterochromia|slit pupils|"
    r"symbol-shaped pupils|bright pupils|ringed eyes|droopy eyes|sharp eyes|"
    r"upturned eyes)\b"
)
_SKIN = re.compile(r"\bskin\b|\bskinned\b")
_SKIN_WHOLE = frozenset({"tan", "tanned", "albino", "pale"})
_BODY = re.compile(
    r"\b(?:flat chest|small breasts|medium breasts|large breasts|huge breasts|"
    r"gigantic breasts|petite|slim|slender|skinny|thin|curvy|chubby|plump|fat|"
    r"muscular|toned|athletic|abs|tall|short stature|wide hips|narrow waist|"
    r"thick thighs|hourglass figure|broad shoulders|feminine body|"
    r"masculine body|androgynous body|voluptuous|lean|stocky|large pectorals|"
    r"muscular arms|thick arms)\b"
)
_MARKS = re.compile(
    r"\b(?:moles?|freckles|scars?|fangs?|pointy ears|elf ears|animal ears|"
    r"cat ears|fox ears|wolf ears|dog ears|rabbit ears|bunny ears|horse ears|"
    r"cow ears|mouse ears|bear ears|horns?|tails?|wings|halo|tattoos?|birthmark|"
    r"facial mark|forehead mark|third eye|vitiligo|prosthetic|mechanical arm|"
    r"mechanical legs?)\b"
)
_SEX = re.compile(
    r"\b(?:1girl|1boy|1other|female|male|girl|boy|woman|man|androgynous|"
    r"futanari|otoko no ko)\b"
)
# 枠別 negative のキーワード比較で無視する語(色・長さだけを比べる)
_CATEGORY_NOISE = re.compile(r"\b(?:hair|haired|eyes?|pupils?|skin|skinned)\b")


def _is_guarded(norm: str) -> bool:
    if norm in _GUARD_WHOLE:
        return True
    if CLOTHING_TAG_PATTERN.search(norm) or SCENE_OR_ACTION_TAG_PATTERN.search(norm):
        return True
    if _GUARD_WORDS.search(norm):
        return True
    return bool(_EYE_WORD.search(norm) and _EYE_STATE.search(norm))


def classify_identity_tag(tag: str) -> str | None:
    """タグの同一性カテゴリ(CATEGORY_ORDER の値)を返す。同一性でなければ None。

    照合は重み記法や括弧を外した小文字表記で行う。服装・情景・動作・表情・
    装身具は None(場面ごとに変わってよいタグ)。
    """
    norm = normalize_tag_for_match(tag)
    if not norm or _is_guarded(norm):
        return None
    if norm in _AGE_WHOLE or _SPECIES.search(norm):
        return "species_age"
    if _FACE.search(norm):
        return "face"
    has_hair = bool(_HAIR_WORD.search(norm))
    if _HAIRED.search(norm) or (has_hair and _COLOR.search(norm)):
        return "hair_color"
    if norm in _HAIR_LENGTH_WHOLE or (has_hair and _HAIR_LENGTH.search(norm)):
        return "hair_length"
    if has_hair or _HAIRSTYLE.search(norm):
        return "hairstyle"
    # 特徴(mole under eye 等)は目より先に判定する
    if _MARKS.search(norm):
        return "marks"
    if _EYE_WORD.search(norm) or _EYES_SHAPE.search(norm):
        return "eyes"
    if norm in _SKIN_WHOLE or _SKIN.search(norm):
        return "skin"
    if _BODY.search(norm):
        return "body"
    if _SEX.search(norm):
        return "sex"
    return None


def _bucketize(tags: str) -> dict[str, list[str]]:
    """タグ列をカテゴリごとに分ける(元の表記を保ち、正規化キーで重複排除)。"""
    buckets: dict[str, list[str]] = {}
    seen: set[str] = set()
    for token in split_tag_tokens(str(tags or "")):
        category = classify_identity_tag(token)
        if category is None:
            continue
        norm = normalize_tag_for_match(token)
        if norm in seen:
            continue
        seen.add(norm)
        buckets.setdefault(category, []).append(token)
    return buckets


def _join_within(tokens: Iterable[str], max_length: int) -> str:
    """タグ境界を守って max_length 以内に連結する。"""
    parts: list[str] = []
    length = 0
    for token in tokens:
        extra = len(token) + (2 if parts else 0)
        if length + extra > max_length:
            break
        parts.append(token)
        length += extra
    return ", ".join(parts)


def signature_from_tags(tags: str, *, max_length: int = SIGNATURE_MAX_LENGTH) -> str:
    """タグ列から同一性タグだけを CATEGORY_ORDER 順に並べた署名を作る。

    日本語の記述文や空文字は "" になる(タグとして解釈できる部分が無いため)。
    """
    buckets = _bucketize(tags)
    ordered = [tag for category in CATEGORY_ORDER for tag in buckets.get(category, [])]
    return _join_within(ordered, max_length)


def compose_signature(*sources: str, max_length: int = SIGNATURE_MAX_LENGTH) -> str:
    """複数のタグ列から署名を合成する。カテゴリごとに先頭の source を優先する。

    先頭の source にそのカテゴリのタグが無いときだけ後続の source から補う
    (性別は primary、瞳色は secondary から、といった補完)。
    """
    buckets = [_bucketize(source or "") for source in sources]
    ordered: list[str] = []
    seen: set[str] = set()
    for category in CATEGORY_ORDER:
        for bucket in buckets:
            entries = bucket.get(category)
            if not entries:
                continue
            for tag in entries:
                norm = normalize_tag_for_match(tag)
                if norm not in seen:
                    seen.add(norm)
                    ordered.append(tag)
            break
    return _join_within(ordered, max_length)


def apply_identity_signature(
    tags: str, signature: str, *, max_length: int = PLAYER_TAGS_MAX_LENGTH
) -> str:
    """タグ列の同一性タグを署名で置き換え、署名を先頭に置く。

    入力から同一性カテゴリのタグを全て除き(服装・ポーズ・表情・情景は残す)、
    「署名, 残り」を返す。2 回適用しても同じ結果になる(冪等)。署名または
    入力が空なら入力をそのまま返す。
    """
    base = str(tags or "")
    signature_tokens = split_tag_tokens(str(signature or ""))
    if not signature_tokens or not base.strip():
        return base
    merged: list[str] = []
    seen: set[str] = set()
    for token in signature_tokens:
        norm = normalize_tag_for_match(token)
        if norm and norm not in seen:
            seen.add(norm)
            merged.append(token)
    for token in split_tag_tokens(base):
        norm = normalize_tag_for_match(token)
        if not norm or norm in seen or classify_identity_tag(token) is not None:
            continue
        seen.add(norm)
        merged.append(token)
    return _join_within(merged, max_length)


def _category_words(norm: str) -> set[str]:
    stripped = _CATEGORY_NOISE.sub(" ", norm)
    return {word for word in re.split(r"[^a-z0-9]+", stripped) if word}


def cross_identity_negative(own_tags: str, other_tags: Iterable[str]) -> str:
    """他キャラの髪色・髪の長さ・瞳色・肌色のうち、自分と異なるものを negative 用に集める。

    自分にそのカテゴリのタグがあるときだけ対象にし(瞳は色タグに限る)、語が
    重なるもの(blue hair と light blue hair 等)は除く。無ければ ""。
    """
    own_buckets = _bucketize(own_tags)
    own_words: dict[str, set[str]] = {}
    for category in _NEGATIVE_CATEGORIES:
        entries = own_buckets.get(category, [])
        if category == "eyes":
            entries = [
                tag for tag in entries if _COLOR.search(normalize_tag_for_match(tag))
            ]
        if entries:
            own_words[category] = set().union(
                *(_category_words(normalize_tag_for_match(tag)) for tag in entries)
            )
    if not own_words:
        return ""
    result: list[str] = []
    seen: set[str] = set()
    for other in other_tags:
        other_buckets = _bucketize(other)
        for category, words in own_words.items():
            for tag in other_buckets.get(category, []):
                norm = normalize_tag_for_match(tag)
                if category == "eyes" and not _COLOR.search(norm):
                    continue
                if norm in seen or words & _category_words(norm):
                    continue
                seen.add(norm)
                result.append(tag)
    return ", ".join(result)
