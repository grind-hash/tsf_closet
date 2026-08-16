import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  type AdventurePromptPreview,
  previewAdventurePrompts,
} from "../../apis/adventure";
import { useAdventure } from "../../contexts/AdventureContext";

interface AdventurePromptPreviewModalProps {
  isOpen: boolean;
  onClose: () => void;
}

type PreviewStage = "narrative" | "resolution" | "visual" | "image";

const STAGES: PreviewStage[] = ["narrative", "resolution", "visual", "image"];

/** JSONなら読みやすく整形する。送信されるのは整形前の文字列 */
function prettyIfJson(value: string): string {
  try {
    return JSON.stringify(JSON.parse(value), null, 2);
  } catch {
    return value;
  }
}

/**
 * 1手番で送られるプロンプトの確認用モーダル（ENABLE_PROMPT_PREVIEW 時のみ）。
 *
 * Adventure は1手番で物語・判定・ビジュアルの3回LLMを呼ぶため、画像タグだけを
 * 見せる「場面画像のプロンプト」編集では、付与した属性などの入力側が見えない。
 * ここではその3回分の system / user と、画像生成へ渡る最終文字列を表示する。
 */
export default function AdventurePromptPreviewModal({
  isOpen,
  onClose,
}: AdventurePromptPreviewModalProps) {
  const { t } = useTranslation();
  const { activeRun } = useAdventure();
  const [input, setInput] = useState("");
  const [stage, setStage] = useState<PreviewStage>("narrative");
  const [preview, setPreview] = useState<AdventurePromptPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const selectedChipRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(
    async (value: string) => {
      if (!activeRun) return;
      setLoading(true);
      setError(null);
      try {
        setPreview(
          await previewAdventurePrompts(activeRun.id, {
            user_input: value,
            input_kind: "free_text",
          }),
        );
      } catch (caught) {
        setError(caught instanceof Error ? caught.message : String(caught));
        setPreview(null);
      } finally {
        setLoading(false);
      }
    },
    [activeRun],
  );

  // 開いた時点の内容をそのまま見たいので、最初の選択肢を仮の入力にして自動取得する
  // biome-ignore lint/correctness/useExhaustiveDependencies: 開いた瞬間だけ初期化する
  useEffect(() => {
    if (!isOpen) return;
    const seed = activeRun?.choices?.[0]?.label ?? "";
    setInput(seed);
    setStage("narrative");
    setError(null);
    void load(seed);
  }, [isOpen]);

  // タブ的なチップ列なので、開いた時点で選択中のチップへフォーカスを移す
  useEffect(() => {
    if (isOpen) selectedChipRef.current?.focus();
  }, [isOpen]);

  if (!isOpen) return null;

  const pair = preview && stage !== "image" ? preview[stage] : null;
  const image = preview?.image ?? null;

  return (
    <div
      className="adventure-prompt-modal"
      role="dialog"
      aria-modal="true"
      aria-label={t("adventure.promptPreview.title")}
    >
      <button
        type="button"
        className="adventure-prompt-modal__backdrop"
        aria-label={t("adventure.promptPreview.close")}
        onClick={onClose}
      />
      <div className="adventure-prompt-modal__panel">
        <h2>{t("adventure.promptPreview.title")}</h2>
        <p className="adventure-prompt-modal__hint">
          {t("adventure.promptPreview.hint")}
        </p>

        <label htmlFor="adventure-preview-input">
          {t("adventure.promptPreview.inputLabel")}
        </label>
        <textarea
          id="adventure-preview-input"
          rows={2}
          maxLength={2000}
          value={input}
          disabled={loading}
          onChange={(event) => setInput(event.target.value)}
          placeholder={t("adventure.promptPreview.inputPlaceholder")}
        />
        <button
          type="button"
          className="adventure-hud__panel-action"
          disabled={loading}
          onClick={() => void load(input)}
        >
          {loading
            ? t("adventure.promptPreview.loading")
            : t("adventure.promptPreview.reload")}
        </button>

        {error && <p className="adventure-prompt-modal__error">{error}</p>}

        <div
          className="adventure-preview-stages"
          role="tablist"
          aria-label={t("adventure.promptPreview.stages")}
        >
          {STAGES.map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              ref={stage === key ? selectedChipRef : undefined}
              aria-selected={stage === key}
              className={`adventure-hud__chip${stage === key ? " is-open" : ""}`}
              disabled={key === "image" && !image}
              onClick={() => setStage(key)}
            >
              <span>{t(`adventure.promptPreview.stage.${key}`)}</span>
            </button>
          ))}
        </div>

        {stage === "image"
          ? image && (
              <>
                <p className="adventure-prompt-modal__hint">
                  {t("adventure.promptPreview.imageNote", {
                    nsfw: String(image.nsfw_mode),
                    precise: String(image.use_precise_reference),
                  })}
                </p>
                <label htmlFor="adventure-preview-image-scene">
                  {t("adventure.promptPreview.scenePrompt")}
                </label>
                <textarea
                  id="adventure-preview-image-scene"
                  rows={4}
                  readOnly
                  value={image.scene_prompt}
                />
                <label htmlFor="adventure-preview-image-player">
                  {t("adventure.promptPreview.playerPrompt")}
                </label>
                <textarea
                  id="adventure-preview-image-player"
                  rows={3}
                  readOnly
                  value={image.player_prompt}
                />
                <label htmlFor="adventure-preview-image-portrait">
                  {t("adventure.promptPreview.portraitPrompt")}
                </label>
                <textarea
                  id="adventure-preview-image-portrait"
                  rows={3}
                  readOnly
                  value={image.portrait_prompt}
                />
                {image.npc_prompts.length > 0 && (
                  <>
                    <label htmlFor="adventure-preview-image-npc">
                      {t("adventure.promptPreview.npcPrompts")}
                    </label>
                    <textarea
                      id="adventure-preview-image-npc"
                      rows={3}
                      readOnly
                      value={image.npc_prompts.join("\n\n")}
                    />
                  </>
                )}
                <label htmlFor="adventure-preview-image-negative">
                  {t("adventure.promptPreview.negativePrompt")}
                </label>
                <textarea
                  id="adventure-preview-image-negative"
                  rows={3}
                  readOnly
                  value={image.negative_prompt}
                />
              </>
            )
          : pair && (
              <>
                {pair.narrative_is_placeholder && (
                  <p className="adventure-prompt-modal__hint">
                    {t("adventure.promptPreview.narrativePlaceholder")}
                  </p>
                )}
                <label htmlFor="adventure-preview-system">
                  {t("adventure.promptPreview.systemPrompt")}
                </label>
                <textarea
                  id="adventure-preview-system"
                  rows={8}
                  readOnly
                  value={pair.system}
                />
                <label htmlFor="adventure-preview-user">
                  {t("adventure.promptPreview.userPrompt")}
                </label>
                <textarea
                  id="adventure-preview-user"
                  rows={12}
                  readOnly
                  value={prettyIfJson(pair.user)}
                />
              </>
            )}

        <div className="adventure-prompt-modal__actions">
          <button type="button" onClick={onClose}>
            {t("adventure.promptPreview.close")}
          </button>
        </div>
      </div>
    </div>
  );
}
