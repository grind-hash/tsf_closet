"""identity_signature(同一性タグ署名)の純関数テスト。"""

import pytest

from gateway.services.identity_signature import (
    PLAYER_TAGS_MAX_LENGTH,
    apply_identity_signature,
    classify_identity_tag,
    complete_age_signature,
    compose_signature,
    cross_identity_negative,
    has_explicit_adult_age,
    signature_from_tags,
)


@pytest.mark.parametrize(
    ("tag", "category"),
    [
        ("1girl", "sex"),
        ("male", "sex"),
        ("mature woman", "age"),
        ("dark elf", "species"),
        ("cat girl", "species"),
        ("old man", "age"),
        ("young adult", "age"),
        ("1.2::young adult man::", "age"),
        ("21-year-old", "age"),
        ("21 years old", "age"),
        ("long legs", "proportions"),
        ("adult proportions", "proportions"),
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
        "old-fashioned dress",
        "year 2025",
        "adult costume",
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


def test_age_and_species_are_completed_independently() -> None:
    assert (
        compose_signature("1boy, elf, slim", "adult, human, black hair, long legs")
        == "1boy, elf, adult, black hair, slim, long legs"
    )


def test_incomplete_signature_preserves_weighted_age_and_proportions() -> None:
    signature = "1boy, black hair, slim"
    tags = "1boy, 1.2::young adult::, black hair, slim, long legs, coat"
    result = apply_identity_signature(tags, signature)
    assert result == "1boy, 1.2::young adult::, black hair, slim, long legs, coat"
    assert apply_identity_signature(result, signature) == result


def test_age_only_signature_does_not_erase_other_traits() -> None:
    assert (
        apply_identity_signature("1boy, black hair, blue eyes, suit", "young adult")
        == "young adult, 1boy, black hair, blue eyes, suit"
    )


def test_age_completion_preserves_current_setting_and_other_tag_order() -> None:
    signature = "1boy, blue eyes, black hair, adult, short legs"
    assert complete_age_signature(signature, "child, long legs") == signature
    assert (
        complete_age_signature("1boy, blue eyes, black hair", "1girl, adult, long legs")
        == "1boy, adult, blue eyes, black hair, long legs"
    )


def test_age_completion_prioritizes_age_within_length_limit() -> None:
    long_signature = "1boy, " + ", ".join(f"black hair {i}" for i in range(30))
    result = complete_age_signature(long_signature, "young adult")
    assert result.startswith("1boy, young adult, ")
    assert len(result) <= 400


@pytest.mark.parametrize("signature", ["1boy, adult", "1boy, child"])
def test_explicit_age_replaces_conflicting_age(signature: str) -> None:
    result = apply_identity_signature("1boy, young adult, child, coat", signature)
    assert result == f"{signature}, coat"


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ("1boy, young adult", True),
        ("1girl, {adult woman}", True),
        ("1.3::21-year-old man::", True),
        ("18 years old", True),
        ("elderly woman", True),
        ("17 years old", False),
        ("1boy, male, slender", False),
        ("1girl, young", False),
        ("adult, child", False),
        ("adult, 12 years old", False),
        ("aged up", False),
        ("adult costume, year 2025", False),
        ("", False),
    ],
)
def test_explicit_adult_age_requires_unambiguous_age(tags: str, expected: bool) -> None:
    assert has_explicit_adult_age(tags) is expected


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
