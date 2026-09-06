import { usePersistedState } from "./usePersistedState";

export const CHARACTER_CHAT_GENERATE_PORTRAIT_KEY =
  "character_chat_generate_portrait";

/**
 * セッションの画像を姿にするとき、そのまま使う(OFF)か外見タグから立ち絵を
 * 描く(ON)か。Hub の「セッションから作る」と Room の「姿を変更」で共有する
 * ブラウザ単位の好み。既定 OFF(画像生成を伴うため)。
 */
export function useCharacterChatPortraitPreference() {
  return usePersistedState<boolean>(
    CHARACTER_CHAT_GENERATE_PORTRAIT_KEY,
    false,
  );
}
