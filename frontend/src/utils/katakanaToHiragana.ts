/**
 * カタカナ→ひらがな変換ユーティリティ
 *
 * NovelAI suggest-tags API用に、カタカナをひらがなに変換する。
 * 日本語（カタカナ）入力の場合、「ひらがな+カタカナ」形式で送信し、
 * 検索ヒット率を向上させる。
 *
 * @module utils/katakanaToHiragana
 * @see specs/006-novelai-prompt-enhancement/research.md
 */

/**
 * カタカナ文字をひらがなに変換する
 *
 * Unicode範囲:
 * - カタカナ: U+30A0 - U+30FF (12448 - 12543)
 * - ひらがな: U+3040 - U+309F (12352 - 12447)
 * - オフセット: 0x60 (96)
 *
 * @param char - 変換する文字
 * @returns 変換後の文字（カタカナでなければそのまま返す）
 */
function katakanaCharToHiragana(char: string): string {
  const code = char.charCodeAt(0);
  // カタカナ範囲（ァ-ン、ヴ、ヵ、ヶ）
  if (code >= 0x30a1 && code <= 0x30f6) {
    return String.fromCharCode(code - 0x60);
  }
  // 長音記号（ー）はそのまま
  return char;
}

/**
 * 文字列内のカタカナをすべてひらがなに変換する
 *
 * @param str - 変換する文字列
 * @returns ひらがなに変換された文字列
 *
 * @example
 * katakanaToHiragana("ティファ") // => "てぃふぁ"
 * katakanaToHiragana("red") // => "red"
 * katakanaToHiragana("テスト123") // => "てすと123"
 */
export function katakanaToHiragana(str: string): string {
  return [...str].map(katakanaCharToHiragana).join("");
}

/**
 * 文字列にカタカナが含まれているかチェックする
 *
 * @param str - チェックする文字列
 * @returns カタカナが含まれていればtrue
 */
export function containsKatakana(str: string): boolean {
  // カタカナ文字の正規表現（ァ-ヶー）
  return /[\u30A1-\u30F6\u30FC]/.test(str);
}

/**
 * 文字列がアルファベット（ASCII）のみかチェックする
 *
 * @param str - チェックする文字列
 * @returns アルファベットと数字、一般的な記号のみであればtrue
 */
export function isAsciiOnly(str: string): boolean {
  // ASCII印字可能文字範囲（0x20-0x7E）+ 改行・タブ
  return /^[\u0020-\u007E\t\n\r]*$/.test(str);
}

/**
 * NovelAI suggest-tags API用のクエリを準備する
 *
 * - カタカナが含まれる場合: 「ひらがな+元の文字列」を返す
 * - ASCII（アルファベット）のみの場合: そのまま返す
 * - 混在の場合: カタカナ部分のみ変換し、「変換後+元の文字列」を返す
 *
 * @param input - ユーザー入力文字列
 * @returns NovelAI API用に整形されたクエリ文字列
 *
 * @example
 * prepareTagSearchQuery("ティファ") // => "てぃふぁティファ"
 * prepareTagSearchQuery("red") // => "red"
 * prepareTagSearchQuery("ティファred") // => "てぃふぁredティファred"
 */
export function prepareTagSearchQuery(input: string): string {
  // 空文字チェック
  if (!input || input.trim() === "") {
    return "";
  }

  // ASCII文字のみの場合は変換不要
  if (isAsciiOnly(input)) {
    return input;
  }

  // カタカナが含まれる場合、ひらがな変換を適用
  if (containsKatakana(input)) {
    const hiraganaVersion = katakanaToHiragana(input);
    // ひらがな版と元の文字列を結合（重複排除）
    if (hiraganaVersion !== input) {
      return `${hiraganaVersion}${input}`;
    }
  }

  // ひらがなのみ、または変換しても同じ場合はそのまま
  return input;
}
