import { parseDialogueSegments } from "../../utils/adventureDialogue";

/**
 * 台本形式(名前「セリフ」)の本文を、話者ラベル付きの行と地の文に分けて描く。
 * 名前付き行が無ければ本文全体が1つの地の文になる
 */
export default function AdventureScriptText({
  text,
  speakers,
}: {
  text: string;
  speakers: string[];
}) {
  const segments = parseDialogueSegments(text, speakers);
  return (
    <>
      {segments.map((segment, index) =>
        segment.kind === "dialogue" ? (
          <p
            // biome-ignore lint/suspicious/noArrayIndexKey: 本文の行は順序固定で識別子を持たない
            key={index}
            className="adventure-messagebox__line adventure-messagebox__line--dialogue"
          >
            <span className="adventure-messagebox__speaker">
              {segment.speaker}
            </span>
            <span>「{segment.text}」</span>
          </p>
        ) : (
          <p
            // biome-ignore lint/suspicious/noArrayIndexKey: 本文の行は順序固定で識別子を持たない
            key={index}
            className="adventure-messagebox__line adventure-messagebox__line--narration"
          >
            {segment.text}
          </p>
        ),
      )}
    </>
  );
}
