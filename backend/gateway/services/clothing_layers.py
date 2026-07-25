"""衣装レイヤーの可視性ルールをプロンプトへ追加する。"""

CLOTHING_LAYER_IMAGE_RULE = """

## CLOTHING LAYER VISIBILITY (HIGHEST PRIORITY)
- Treat body attributes and every listed garment as persistent facts, but render only elements that are physically visible.
- Apply this order from inner to outer: body/anatomy, underwear, inner garments, outer garments.
- Outer garments that are described as worn must stay in their normal worn position and visually cover the layers beneath them.
- Do NOT open, lift, pull aside, displace, remove, or make clothing accidentally transparent merely to reveal underwear, genitals, pubic hair, or other covered attributes.
- Tight clothing may show only the natural body silhouette. It must not reveal underwear details, genital details, or pubic-hair details.
- Omit covered underwear and covered anatomy from positive visual tags and visible descriptions without deleting those facts from the character state.
- Allow visibility only when the CURRENT user instruction explicitly requests sheer, transparent, see-through, or chiffon fabric, or explicitly requests opening, lifting, pulling aside, removing, or undressing clothing. Limit visibility to the requested garment and body area.
- For an action or location change, if the current instruction does not explicitly continue exposure, depict the outer garments in their normal properly worn state.
"""

CLOTHING_LAYER_FEELING_RULE = """

【衣装レイヤーの認識ルール（最優先）】
- 身体属性、下着、内側の服、外衣はすべて実在する状態として保持する。
- 外衣で覆われた下着や身体属性は、着用している事実、布越しの感触、圧迫感や素材感としてのみ心境へ反映してよい。
- 覆われた要素を「見えている」「露出している」「他人から確認できる」と描写してはいけない。
- タイトな服では身体のシルエットやフィット感までに留め、下着、陰部、陰毛の詳細が見えるとは描写しない。
- 現在のユーザー指示に、透ける素材、シフォン、服を開ける・めくる・ずらす・脱ぐなどの明示がある場合のみ、その指定範囲の見え方を心境へ反映してよい。
- 行動や外出の指示で露出継続が明示されていない場合、外衣は通常どおり適切に着用され、下層は覆われているものとして扱う。
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
