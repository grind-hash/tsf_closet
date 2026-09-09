"""identity_signature(同一性タグ署名)の純関数テスト。"""

import pytest

from gateway.services.identity_signature import (
    PLAYER_TAGS_MAX_LENGTH,
    apply_identity_signature,
    classify_identity_tag,
    compose_signature,
    cross_identity_negative,
    signature_from_tags,
)


@pytest.mark.parametrize(
    ("tag", "category"),
    [
        ("1girl", "sex"),
        ("male", "sex"),
        ("mature woman", "sex"),
        ("dark elf", "species_age"),
        ("cat girl", "species_age"),
        ("old man", "species_age"),
        ("black hair", "hair_color"),
        ("light brown hair", "hair_color"),
        ("long black hair", "hair_color"),
        ("silver-haired", "hair_color"),
        ("long hair", "hair_length"),
        ("very short hair", "hair_length"),
        ("bald", "hair_length"),
        ("ponytail", "hairstyle"),
        ("twintails", "hairstyle"),
        ("hair between eyes", "hairstyle"),
        ("blunt bangs", "hairstyle"),
        ("wavy hair", "hairstyle"),
        ("blue eyes", "eyes"),
        ("{red eyes}", "eyes"),
        ("tareme", "eyes"),
        ("heterochromia", "eyes"),
        ("slit pupils", "eyes"),
        ("pale skin", "skin"),
        ("dark-skinned female", "skin"),
        ("tan", "skin"),
        ("medium breasts", "body"),
        ("petite", "body"),
        ("muscular male", "body"),
        ("tall female", "body"),
        ("mole under eye", "marks"),
        ("freckles", "marks"),
        ("pointy ears", "marks"),
        ("cat ears", "marks"),
        ("fang", "marks"),
        ("thick eyebrows", "face"),
        ("facial hair", "face"),
        ("long eyelashes", "face"),
    ],
)
def test_classify_identity_tag_categories(tag: str, category: str) -> None:
    assert classify_identity_tag(tag) == category


@pytest.mark.parametrize(
    "tag",
    [
        "school uniform",
        "white shirt",
        "standing",
        "looking at viewer",
        "smile",
        "wet hair",
        "messy hair",
        "hair ribbon",
        "hair ornament",
        "closed eyes",
        "one eye closed",
        "tan lines",
        "earrings",
        "glasses",
        "pubic hair",
        "raised eyebrows",
        "tail coat",
        "cowboy shot",
        "playboy bunny",
        "",
        "  ",
        "黒髪の少女",
    ],
)
def test_classify_identity_tag_rejects_non_identity(tag: str) -> None:
    assert classify_identity_tag(tag) is None


def test_ponytail_is_hairstyle_not_tail_and_scarf_is_not_scar() -> None:
    assert classify_identity_tag("ponytail") == "hairstyle"
    assert classify_identity_tag("scarf") is None


def test_signature_from_tags_orders_dedupes_and_keeps_weights() -> None:
    tags = "white shirt, {blue eyes}, 1.2::blonde hair::, long hair, 1girl, Blonde Hair"
    assert (
        signature_from_tags(tags) == "1girl, 1.2::blonde hair::, long hair, {blue eyes}"
    )


def test_signature_from_tags_returns_empty_for_prose_or_blank() -> None:
    assert signature_from_tags("") == ""
    assert signature_from_tags("黒髪ロングの少女、赤い瞳") == ""
    assert signature_from_tags("school uniform, smile, standing") == ""


def test_signature_from_tags_respects_max_length_on_tag_boundary() -> None:
    signature = signature_from_tags(
        "1girl, black hair, long hair, blue eyes, pale skin", max_length=22
    )
    assert signature == "1girl, black hair"


def test_apply_identity_signature_prepends_and_strips_drift() -> None:
    signature = "1girl, blonde hair, long hair, blue eyes"
    tags = "1boy, black hair, short hair, brown eyes, school uniform, smile, standing"
    applied = apply_identity_signature(tags, signature)
    assert applied == (
        "1girl, blonde hair, long hair, blue eyes, school uniform, smile, standing"
    )
    # 2 回適用しても同じ(冪等)
    assert apply_identity_signature(applied, signature) == applied


def test_apply_identity_signature_without_signature_or_tags_is_identity() -> None:
    assert apply_identity_signature("1boy, black hair", "") == "1boy, black hair"
    assert apply_identity_signature("", "1girl, blonde hair") == ""
    assert apply_identity_signature("   ", "1girl") == "   "


def test_apply_identity_signature_respects_player_tags_limit() -> None:
    signature = "1girl, blonde hair"
    filler = ", ".join(f"tag{index}" for index in range(400))
    applied = apply_identity_signature(filler, signature)
    assert applied.startswith("1girl, blonde hair, tag0")
    assert len(applied) <= PLAYER_TAGS_MAX_LENGTH
    assert not applied.endswith(",")


def test_compose_signature_fills_missing_categories_from_later_sources() -> None:
    composed = compose_signature(
        "1girl, silver hair, school uniform",
        "1boy, black hair, blue eyes, pale skin",
    )
    assert composed == "1girl, silver hair, blue eyes, pale skin"


def test_compose_signature_ignores_blank_sources() -> None:
    assert compose_signature("", None, "1boy, black hair") == "1boy, black hair"  # type: ignore[arg-type]
    assert compose_signature("", "") == ""


def test_cross_identity_negative_only_for_differing_categories() -> None:
    own = "1boy, black hair, brown eyes, school uniform"
    others = ["1girl, blonde hair, blue eyes, pale skin, dress"]
    assert cross_identity_negative(own, others) == "blonde hair, blue eyes"


def test_cross_identity_negative_skips_overlapping_words_and_missing_own() -> None:
    assert cross_identity_negative("blue hair", ["light blue hair"]) == ""
    assert cross_identity_negative("dark skin", ["dark-skinned female"]) == ""
    # 自分に髪色・瞳色が無ければ他人の値も出さない
    assert (
        cross_identity_negative("1boy, school uniform", ["blonde hair, blue eyes"])
        == ""
    )
    # 瞳は色タグだけを比べる(形状は対象外)
    assert cross_identity_negative("tareme, brown eyes", ["tsurime, brown eyes"]) == ""
    assert cross_identity_negative("", ["blonde hair"]) == ""


def test_cross_identity_negative_dedupes_across_others() -> None:
    own = "1girl, black hair, long hair"
    others = ["blonde hair, short hair", "Blonde Hair, short hair, blue eyes"]
    assert cross_identity_negative(own, others) == "blonde hair, short hair"
