"""成人向けの場面（サロンの体験の場面）で、未成年を思わせる姿を描かないための判定。

小柄・低身長・控えめな胸・ツインテールなど成人にもある見た目の特徴は対象にせず、
年齢・子ども向けの品・小中高を明示する目印だけで判定する。目印があれば場面ごと描かない。
描くときは、画像に成人のタグと、子どもを示す語のネガティブを付ける。
"""

from __future__ import annotations

import re
import unicodedata

# 語として現れたら目印とみなす英語（小文字・空白区切り。タグの _ は空白にそろえる）
_MARKER_WORDS: tuple[str, ...] = (
    "child",
    "children",
    "childlike",
    "kid",
    "kids",
    "toddler",
    "infant",
    "preschooler",
    "kindergarten",
    "kindergartener",
    "loli",
    "lolicon",
    "shota",
    "shotacon",
    "teen",
    "teens",
    "teenage",
    "teenager",
    "teenagers",
    "preteen",
    "pre-teen",
    "tween",
    "minor",
    "minors",
    "underage",
    "under-age",
    "aged down",
    "young girl",
    "young boy",
    "little girl",
    "little boy",
    "schoolgirl",
    "schoolboy",
    "schoolchild",
    "schoolkid",
    "student",
    "students",
    "elementary school",
    "elementary schooler",
    "primary school",
    "middle school",
    "middle schooler",
    "junior high",
    "high school",
    "highschool",
    "high schooler",
    "classroom",
    "school uniform",
    "school bag",
    "schoolbag",
    "school swimsuit",
    "serafuku",
    "gakuran",
    "randoseru",
    "training bra",
)

# 成人の学生など、上の語を含んでも目印にしない言い回し（判定の前に取り除く）
_ADULT_PHRASES: tuple[str, ...] = (
    "college student",
    "college students",
    "university student",
    "university students",
    "graduate student",
    "graduate students",
)

# タグとして単独で現れたときだけ目印とみなす略語（女子高生・女子中学生・女子小学生）
_MARKER_TOKENS: frozenset[str] = frozenset({"jk", "jc", "js"})

# 日本語の目印（部分一致）。ロリータ服はファッションなので除く
_MARKER_JA = re.compile(
    "|".join(
        [
            "子供",
            "子ども",
            "こども",
            "幼女",
            "幼児",
            "幼稚園",
            "園児",
            "児童",
            "小学生",
            "中学生",
            "高校生",
            "女子高生",
            "男子高生",
            "小学校",
            "中学校",
            "高校",
            "未成年",
            "ランドセル",
            "スクール水着",
            "スク水",
            "セーラー服",
            "学ラン",
            "学生服",
            "ロリ(?!ータ)",
            "ショタ",
        ]
    )
)

# 18 歳未満の年齢の書き方（17 yo、15 years old、16歳 など）
_UNDERAGE_NUMBER = re.compile(
    r"(?<![0-9])(?:[1-9]|1[0-7])\s*(?:yo\b|y/o|years?[\s-]*old|year-old|歳|才)"
)

_MARKER_WORD_PATTERN = re.compile(
    r"(?<![a-z])(?:"
    + "|".join(
        re.escape(word).replace(r"\ ", r"\s+")
        for word in sorted(_MARKER_WORDS, key=len, reverse=True)
    )
    + r")(?![a-z])"
)

# 体験の場面の画像に付けるタグと、ネガティブに足す語
ADULT_IMAGE_TAG = "adult"
ADULT_IMAGE_SENTENCE = "Everyone in the image is an adult."
MINOR_NEGATIVE_TAGS = (
    "child, loli, shota, toddler, teenager, aged down, "
    "school uniform, randoseru, training bra"
)


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("_", " ")
    for phrase in _ADULT_PHRASES:
        text = re.sub(re.escape(phrase).replace(r"\ ", r"\s+"), " ", text)
    return text


def find_minor_markers(*texts: str | None) -> list[str]:
    """未成年を思わせる目印を、見つけた順に重複なく返す。"""
    found: list[str] = []
    for raw in texts:
        if not raw:
            continue
        text = _normalize(raw)
        hits = [m.group(0) for m in _MARKER_WORD_PATTERN.finditer(text)]
        hits += [m.group(0) for m in _MARKER_JA.finditer(text)]
        hits += [m.group(0) for m in _UNDERAGE_NUMBER.finditer(text)]
        tokens = (token.strip(" {}[]()") for token in re.split(r"[,\n]", text))
        hits += [token for token in tokens if token in _MARKER_TOKENS]
        for hit in hits:
            hit = " ".join(hit.split())
            if hit not in found:
                found.append(hit)
    return found


def has_minor_markers(*texts: str | None) -> bool:
    """未成年を思わせる目印が1つでもあるか。"""
    return bool(find_minor_markers(*texts))


class MinorMarkerError(Exception):
    """成人向けの場面を、未成年を思わせる姿で描こうとした。"""
