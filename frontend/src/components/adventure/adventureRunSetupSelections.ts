import { getCharacterPreset } from "../../apis/characters";
import { fetchGalleryItem, fetchGallerySession } from "../../apis/gallery";
import { fetchPromptExpanderEntry } from "../../apis/promptExpander";
import type {
  AdventureRunSetupPlayer,
  AdventureRunSetupSessionTarget,
  AdventureRunSetupSource,
} from "../../utils/adventureRunSetup";
import {
  type AdventureSourceSelection,
  selectionFromCharacterPreset,
  selectionFromPromptExpanderEntry,
  selectionFromSession,
} from "./AdventureSessionPickerModal";

type SelectionTarget =
  | Exclude<AdventureRunSetupSource, null>
  | Exclude<AdventureRunSetupPlayer, null>;

async function resolveSessionSelection(
  target: AdventureRunSetupSessionTarget,
): Promise<AdventureSourceSelection | null> {
  const { sessionId, historyId } = target;
  // 一覧の何ページ目にあっても、セッションの名前と最新画像を ID で引く
  const session = await fetchGallerySession(sessionId);
  if (!session) return null;
  if (!historyId) return selectionFromSession(session);
  // ピッカーで時点を選んだときと同じ形の選択を組む
  const { item } = await fetchGalleryItem(historyId);
  if (item.session_id !== sessionId) return null;
  return {
    sessionId,
    historyId: item.id,
    characterName: session.character_name,
    thumbnailUrl: item.image_url,
    pointLabel: item.instruction,
    origin: "session",
  };
}

/**
 * 遊んだ run の開始素材・主人公を、作成フォームの選択オブジェクトへ取り直す。
 * 削除済み・立ち絵の無いキャラクターなど取り直せないときは null を返し、
 * 別の候補へは倒さない(呼び出し側で利用者へ案内する)。
 */
export async function resolveRunSetupSelection(
  target: SelectionTarget,
): Promise<AdventureSourceSelection | null> {
  try {
    switch (target.kind) {
      case "character": {
        const preset = await getCharacterPreset(target.characterPresetId);
        return preset.portrait_url
          ? selectionFromCharacterPreset(preset)
          : null;
      }
      case "promptExpander": {
        const entry = await fetchPromptExpanderEntry(
          target.promptExpanderEntryId,
        );
        return selectionFromPromptExpanderEntry(entry);
      }
      case "session":
        return await resolveSessionSelection(target);
      default:
        return null;
    }
  } catch (caught: unknown) {
    console.warn("Failed to resolve copied adventure setup selection:", caught);
    return null;
  }
}
