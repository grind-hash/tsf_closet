"""過激施術(サロンの成人向けの依頼)で、お客様が願う行為のテーマ。

来店ごとに Python が向きの違う候補を数個選び、依頼の生成に渡す。LLM はその中から
お客様の TSF への態度と性格に合う1つを選び、本人の言葉にする。例をなぞって毎回同じ
願いになるのを防ぎ、ハグやキスのような穏当な願いに逃げないようにするため、行為はここで決める。

body は願う姿の体(female / male)。お客様の元の性別と違えば TSF、同じなら同性のまま理想の体。
partner は相手(man / woman / none)。男性の体と男性の相手の組み合わせは置かない
(TSF Closet に男性同士は含めない。元が男性で女性の体になったお客様の相手が男性なのはよい)。
act は LLM に渡す行為の説明(英語)。look_hint は、伏せた好みか願いに入れさせる姿の条件。
"""

from __future__ import annotations

from dataclasses import dataclass

# 動機を「意中の相手の好みに合わせたい」にする来店の割合(残りは自分の憧れ・好奇心)
SENSITIVE_CRUSH_MOTIVE_RATE: float = 0.3
# 生成に渡す候補の数(向きの違う体から少なくとも1つずつ)
SENSITIVE_DESIRE_CANDIDATES: int = 3


@dataclass(frozen=True)
class SensitiveDesire:
    id: str
    body: str
    partner: str
    act: str
    look_hint: str = ""

    @property
    def solo(self) -> bool:
        """相手のいない行為(体験の場面に他の人物を出さない)。"""
        return self.partner == "none"


SENSITIVE_DESIRES: tuple[SensitiveDesire, ...] = (
    # 女性の体で、男性と
    SensitiveDesire(
        "fellatio",
        "female",
        "man",
        "giving a man a blowjob (fellatio) until he comes",
        "glossy lips or a hairstyle that stays out of the face",
    ),
    SensitiveDesire(
        "paizuri",
        "female",
        "man",
        "giving a man a titjob (paizuri) with her breasts",
        "large breasts",
    ),
    SensitiveDesire(
        "creampie",
        "female",
        "man",
        "having sex with a man in the missionary position and letting him come inside her",
        "lingerie she wants to be seen in",
    ),
    SensitiveDesire(
        "cowgirl",
        "female",
        "man",
        "riding a man in the cowgirl position, moving her own hips",
        "a body line that shows when she moves",
    ),
    SensitiveDesire(
        "doggystyle",
        "female",
        "man",
        "being taken hard from behind (doggystyle) by a man",
        "a shapely rear or underwear that shows it off",
    ),
    SensitiveDesire(
        "first_time",
        "female",
        "man",
        "losing her virginity as a woman to a man",
        "innocent white lingerie",
    ),
    SensitiveDesire(
        "cunnilingus",
        "female",
        "man",
        "being licked (cunnilingus) by a man until she climaxes",
        "lingerie or a skirt that is easy to take off",
    ),
    SensitiveDesire(
        "seduction",
        "female",
        "man",
        "seducing a man in lingerie and being pushed down and had sex with",
        "seductive lingerie",
    ),
    # 女性の体で、女性と(百合)
    SensitiveDesire(
        "yuri_breasts",
        "female",
        "woman",
        "making out with a woman, kissing deeply and fondling each other's breasts",
        "large breasts",
    ),
    SensitiveDesire(
        "yuri_sixty_nine",
        "female",
        "woman",
        "licking a woman's pussy while she licks hers in return (69)",
        "lingerie that is easy to take off",
    ),
    SensitiveDesire(
        "yuri_scissoring",
        "female",
        "woman",
        "grinding against a woman (scissoring) until they both climax",
        "a body line that shows when she moves",
    ),
    SensitiveDesire(
        "yuri_fingering",
        "female",
        "woman",
        "being fingered by a woman until she climaxes",
        "pretty lingerie",
    ),
    # 女性の体で、ひとり
    SensitiveDesire(
        "female_masturbation",
        "female",
        "none",
        "masturbating alone to find out what a woman's orgasm feels like",
        "a body she cannot stop touching, such as large breasts",
    ),
    # 男性の体で、女性と
    SensitiveDesire(
        "penetrate",
        "male",
        "woman",
        "having sex with a woman and penetrating her",
        "a muscular body",
    ),
    SensitiveDesire(
        "receive_fellatio",
        "male",
        "woman",
        "getting a blowjob (fellatio) from a woman",
        "a body or outfit that makes him feel manly",
    ),
    SensitiveDesire(
        "receive_paizuri",
        "male",
        "woman",
        "getting a titjob (paizuri) from a busty woman",
        "a tall, broad-shouldered body",
    ),
    SensitiveDesire(
        "male_doggystyle",
        "male",
        "woman",
        "taking a woman from behind (doggystyle)",
        "a muscular body",
    ),
    # 男性の体で、ひとり
    SensitiveDesire(
        "male_masturbation",
        "male",
        "none",
        "masturbating alone to find out what a man's climax feels like",
        "a male body he is curious about",
    ),
)
