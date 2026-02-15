import pytest

from gateway.services.tag_classifier import classify_tags


@pytest.mark.parametrize(
    ("instruction", "expected_category"),
    [
        ("ハイレグのマイクロビキニに変身", "swimsuit"),
        ("school uniform 風のブレザー制服", "uniform"),
        ("クラシカルメイド衣装を着る", "maid"),
        ("gothic lolita ドレスで", "gothic_lolita"),
        ("wedding dress を着る", "dress"),
        ("lingerie とガーターベルト", "underwear"),
        ("サキュバス風コスプレ", "cosplay"),
    ],
)
def test_classify_tags_costume_category_regression(
    instruction: str, expected_category: str
) -> None:
    tags = classify_tags(instruction)
    assert tags.costume_category == expected_category


@pytest.mark.parametrize(
    ("instruction", "expected_exposure"),
    [
        ("シースルーで露出高めの衣装", "high"),
        ("チアリーダー風の衣装", "medium"),
        ("長袖で控えめなローブ", "low"),
    ],
)
def test_classify_tags_exposure_regression(
    instruction: str, expected_exposure: str
) -> None:
    tags = classify_tags(instruction)
    assert tags.exposure_level == expected_exposure


@pytest.mark.parametrize(
    ("instruction", "expected_age"),
    [
        ("ランドセルのキッズ風コーデ", "child"),
        ("女子高生の制服スタイル", "student"),
        ("キャリアウーマン風の秘書コーデ", "adult"),
    ],
)
def test_classify_tags_age_impression_regression(
    instruction: str, expected_age: str
) -> None:
    tags = classify_tags(instruction)
    assert tags.age_impression == expected_age


@pytest.mark.parametrize(
    (
        "instruction",
        "expected_category",
        "expected_exposure",
        "expected_age",
    ),
    [
        # costume_category priority: underwear > swimsuit > maid > gothic_lolita > cosplay > ...
        ("メイド風ランジェリー", "underwear", "medium", "unknown"),
        ("ゴシックロリータ風のメイド服", "maid", "medium", "child"),
        ("チャイナドレス風コスプレ", "cosplay", "low", "unknown"),
        # exposure priority: high > low > medium
        ("露出少なめのミニスカ制服", "uniform", "high", "student"),
        # age_impression priority: child > adult > student
        ("JKでお姉さんっぽい制服", "uniform", "medium", "adult"),
    ],
)
def test_classify_tags_boundary_priority_regression(
    instruction: str,
    expected_category: str,
    expected_exposure: str,
    expected_age: str,
) -> None:
    tags = classify_tags(instruction)
    assert tags.costume_category == expected_category
    assert tags.exposure_level == expected_exposure
    assert tags.age_impression == expected_age
