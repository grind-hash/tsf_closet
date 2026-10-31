/**
 * 通常プレイの入力文字数の上限（backend/gateway/consts/play_limits.py と揃える）。
 */

/** 着せ替え・現実改変・行動の指示の上限。お気に入りプロンプトの内容上限と同じ */
export const INSTRUCTION_MAX_LENGTH = 4000;

/** 現実改変の指示は、この前置きを付けてセッション属性へ自動追加される */
export const REALITY_ATTRIBUTE_PREFIX = "[現実改変] ";

/** 属性の上限。現実改変で自動追加された属性もそのまま編集できるよう、前置きの分を足す */
export const ATTRIBUTE_TEXT_MAX_LENGTH =
  INSTRUCTION_MAX_LENGTH + REALITY_ATTRIBUTE_PREFIX.length;

/** TSF(性転換・変身)への態度の上限(backend の PROFILE_TSF_ATTITUDE_MAX_LEN と揃える) */
export const TSF_ATTITUDE_MAX_LENGTH = 300;
