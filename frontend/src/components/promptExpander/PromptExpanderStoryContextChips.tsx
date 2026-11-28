/**
 * これまでの話（漫画で続きのページを作るときに LLM へ渡す前のページ）のチップ列。
 * 生成した順に番号と縮小画像を付けて並べ、押すと生成履歴のそのカードへ移る。選ぶのは履歴カードのボタンで行う。
 * 「生成履歴から選ぶ」は、まだ選んでいない一番新しいページのカードへ移り、そのボタンを目立たせる
 */
import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { promptExpanderImageUrl } from "../../apis/promptExpander";
import { PROMPT_EXPANDER_STORY_CONTEXT_MAX } from "../../constants/promptExpander";
import { usePromptExpander } from "../../contexts/PromptExpanderContext";
import {
  findStoryPickTarget,
  storyContextEntryLabel,
} from "../../utils/promptExpanderStoryContext";

export default function PromptExpanderStoryContextChips() {
  const { t } = useTranslation();
  const {
    entries,
    storyContextEntries,
    storyContextEntryIds,
    removeStoryContextEntry,
    clearStoryContext,
    requestEntryReveal,
  } = usePromptExpander();
  const count = storyContextEntries.length;
  // 選べるページが無いときは、押しても移る先が無いのでボタンを出さず、案内文で知らせる
  const pickTarget = useMemo(
    () =>
      findStoryPickTarget(
        entries,
        storyContextEntryIds,
        PROMPT_EXPANDER_STORY_CONTEXT_MAX,
      ),
    [entries, storyContextEntryIds],
  );

  return (
    <div
      className="prompt-expander__story-context"
      role="group"
      aria-label={t("promptExpander.composer.storyContextLabel")}
    >
      <div className="prompt-expander__story-context-head">
        <span className="prompt-expander__cast-chips-label">
          {t("promptExpander.composer.storyContextLabel")}
        </span>
        <span className="prompt-expander__story-context-count">
          {t("promptExpander.composer.storyContextCount", {
            count,
            max: PROMPT_EXPANDER_STORY_CONTEXT_MAX,
          })}
        </span>
        {pickTarget && (
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={() => requestEntryReveal(pickTarget.id, "story")}
          >
            {t("promptExpander.composer.storyContextPick")}
          </button>
        )}
        {count > 0 && (
          <button
            type="button"
            className="prompt-expander__btn prompt-expander__btn--sm"
            onClick={clearStoryContext}
          >
            {t("promptExpander.composer.storyContextClear")}
          </button>
        )}
      </div>
      {count > 0 ? (
        <>
          <ol className="prompt-expander__story-context-list">
            {storyContextEntries.map((entry, index) => {
              const label =
                storyContextEntryLabel(entry) ||
                t("promptExpander.entry.uploadedNoText");
              return (
                <li key={entry.id} className="prompt-expander__story-chip">
                  <button
                    type="button"
                    className="prompt-expander__story-chip-main"
                    onClick={() => requestEntryReveal(entry.id)}
                    title={t("promptExpander.composer.storyChipTitle", {
                      page: index + 1,
                    })}
                  >
                    <span className="prompt-expander__story-chip-number">
                      {index + 1}
                    </span>
                    {/* ラベル（あらすじ）とカードの本文（ネーム）は違うことがあるので、絵でも見分けられるようにする */}
                    <img
                      className="prompt-expander__story-chip-thumb"
                      src={promptExpanderImageUrl(entry)}
                      alt=""
                      loading="lazy"
                    />
                    <span className="prompt-expander__story-chip-label">
                      {label}
                    </span>
                  </button>
                  <button
                    type="button"
                    className="prompt-expander__story-chip-remove"
                    onClick={() => removeStoryContextEntry(entry.id)}
                    aria-label={t("promptExpander.composer.storyChipRemove", {
                      page: index + 1,
                    })}
                  >
                    ×
                  </button>
                </li>
              );
            })}
          </ol>
          <p className="prompt-expander__hint">
            {t("promptExpander.composer.storyContextActiveHint")}
          </p>
        </>
      ) : (
        <p className="prompt-expander__hint">
          {pickTarget
            ? t("promptExpander.composer.storyContextEmptyHint")
            : t("promptExpander.composer.storyContextNoPagesHint")}
        </p>
      )}
    </div>
  );
}
