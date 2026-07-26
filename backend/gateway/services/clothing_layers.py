"""衣装レイヤーの可視性ルールをプロンプトへ追加する。"""

CLOTHING_LAYER_IMAGE_RULE = """

## CLOTHING LAYER VISIBILITY (HIGHEST PRIORITY)
- Every listed garment is a persistent worn fact. Covered does NOT mean removed.
- Apply this order from inner to outer: body/anatomy, underwear, inner garments, outer garments.
- When adding or changing outer garments, KEEP existing underwear and underlayers unless the CURRENT user instruction explicitly removes them (e.g. take off bra, no bra, braless, remove panties, undress).
- Outer-only instructions replace/update outer garments only. Do NOT treat them as a full wardrobe replacement that deletes underwear.
- For NovelAI-style tag prompts: UPDATE outer/main garments to match the instruction, but KEEP undergarment tags from the previous prompt/state unless explicitly removed. Preserve undergarment colors and types when kept.
- Outer garments that are described as worn must stay in their normal worn position and visually cover the layers beneath them.
- Do NOT open, lift, pull aside, displace, remove, or make clothing accidentally transparent merely to reveal underwear, genitals, pubic hair, or other covered attributes.
- Tight clothing may show only the natural body silhouette. It must not reveal underwear details, genital details, or pubic-hair details.
- Undergarment tags may remain in the outfit inventory / character clothing tags as worn items; do not depict them as visibly exposed when covered.
- Never imply braless, no bra, no panties, bare breasts under clothing, or nipples through ordinary tops/bottoms unless explicitly requested.
- Allow visibility or removal only when the CURRENT user instruction explicitly requests sheer, transparent, see-through, or chiffon fabric, or explicitly requests opening, lifting, pulling aside, removing, or undressing clothing. Limit visibility/removal to the requested garment and body area.
- For an action or location change, if the current instruction does not explicitly continue exposure, depict the outer garments in their normal properly worn state with underlayers still worn and covered.
"""

CLOTHING_LAYER_FEELING_RULE = """

【衣装レイヤーの認識ルール（最優先）】
- 身体属性、下着、内側の服、外衣はすべて実在する状態として保持する。覆われていることは脱いだことを意味しない。
- 直前の状態にあった下着は、現在のユーザー指示が脱ぐ・外す・ノーブラなどと明示しない限り、今も着用中として扱う。
- 外衣や上着・スカートなどの指示だけを、下着を含む全身の着替え置換と解釈してはいけない。外衣は下着の上に重ね着する。
- 外衣で覆われた下着や身体属性は、着用している事実、布越しの感触、圧迫感や素材感としてのみ心境へ反映してよい。
- 覆われた要素を「見えている」「露出している」「他人から確認できる」と描写してはいけない。
- 「下着を消して直接着た」「ノーブラでトップスを着た」など、下着なし直着の描写は、現在の指示にその明示がない限り禁止する。
- タイトな服では身体のシルエットやフィット感までに留め、下着、陰部、陰毛の詳細が見えるとは描写しない。
- 現在のユーザー指示に、透ける素材、シフォン、服を開ける・めくる・ずらす・脱ぐなどの明示がある場合のみ、その指定範囲の見え方を心境へ反映してよい。
- 行動や外出の指示で露出継続が明示されていない場合、外衣は通常どおり適切に着用され、下層は覆われつつ着用されたままとして扱う。
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
