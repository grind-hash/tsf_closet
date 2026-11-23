import { getCharacterPreset } from "../../apis/characters";
import { fetchGalleryItem, fetchGalleryList } from "../../apis/gallery";
import { fetchPromptExpanderEntry } from "../../apis/promptExpander";
import type { GallerySession } from "../../types";
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

function characterNameFor(
  sessions: GallerySession[],
  sessionId: string,
  fallbackName: string | null,
): string | null {
  return (
    sessions.find((session) => session.session_id === sessionId)
      ?.character_name ?? fallbackName
  );
}

async function resolveSessionSelection(
  target: AdventureRunSetupSessionTarget,
  sessions: GallerySession[],
): Promise<AdventureSourceSelection | null> {
  const { sessionId, historyId, fallbackName } = target;
  if (historyId) {
    // ピッカーで時点を選んだときと同じ形の選択を組む
    const { item } = await fetchGalleryItem(historyId);
    if (item.session_id !== sessionId) return null;
    return {
      sessionId,
      historyId: item.id,
      characterName: characterNameFor(sessions, sessionId, fallbackName),
      thumbnailUrl: item.image_url,
      pointLabel: item.instruction,
      origin: "session",
    };
  }
  const listed = sessions.find((session) => session.session_id === sessionId);
  if (listed) return selectionFromSession(listed);
  // 1ページ目に無いセッションは、その画像1件で存在を確かめて現在の状態として選ぶ
  const { items } = await fetchGalleryList(1, 1, sessionId);
  const latest = items[0];
  if (!latest) return null;
  return {
    sessionId,
    historyId: undefined,
    characterName: fallbackName,
    thumbnailUrl: latest.image_url,
    pointLabel: null,
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
  sessions: GallerySession[],
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
        return await resolveSessionSelection(target, sessions);
      default:
        return null;
    }
  } catch (caught: unknown) {
    console.warn("Failed to resolve copied adventure setup selection:", caught);
    return null;
  }
}
