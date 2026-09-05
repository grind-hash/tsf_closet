import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import type { AdventureInputKind } from "../../apis/adventure";
import {
  useAdventure,
  useAdventureStreamingNarrative,
} from "../../contexts/AdventureContext";
import {
  type AdventureStageFrame,
  partnerPortraitReasonKey,
} from "../../utils/adventureFrames";
import type { AdventureSceneView } from "../../utils/adventureSceneView";
import AdventureFreeInput, {
  type AdventureFreeInputSpeech,
} from "./AdventureFreeInput";
import AdventureScriptText from "./AdventureScriptText";
import AdventureTalkThread from "./AdventureTalkThread";

export type AdventureActionMode = "act" | "talk";

export interface AdventureVoiceReplay {
  canSpeak: boolean;
  /** 再読み上げの対象テキスト。空ならボタンを無効化 */
  text: string;
  /** いま再生中(押すと停止) */
  active: boolean;
  onToggle: () => void;
}

interface AdventureMessageBoxProps {
  scene: AdventureSceneView;
  hidden: boolean;
  onHide: () => void;
  onOpenLog: () => void;
  /** romance のみ表示する 🔊 */
  voiceReplay: AdventureVoiceReplay;
  /** 攻略対象の立ち絵を据え置いた手番の案内(無ければ null) */
  partnerPortraitNote: AdventureStageFrame | null;
  isStageLoading: boolean;
  /** 3D モデル表示中はステージを覆わず、本文にカーソルだけ出す */
  quietStage: boolean;
  /** 判定・画像工程の進捗を行動パネルに出す(quietStage のみ) */
  controlsProgressVisible: boolean;
  phaseLabel: string;
  viewingPast: boolean;
  /** 進行中に加え、終了後でもエピローグ移行済みなら操作パネルを出す */
  canAct: boolean;
  actionMode: AdventureActionMode;
  onActionModeChange: (mode: AdventureActionMode) => void;
  input: string;
  onInputChange: (value: string) => void;
  /** 手番を消費する送信(選択肢・自由入力・romance の行動) */
  onSubmit: (value: string, kind: AdventureInputKind) => void;
  /** トークモードの送信(手番を消費しない) */
  onSubmitTalk: (value: string) => void;
  speech: AdventureFreeInputSpeech;
  onOpenGiftShop: () => void;
  onOpenAttributes: () => void;
}

/** 画面下部のメッセージ窓。メタ行・本文・行動パネル(またはエンディング) */
export default function AdventureMessageBox({
  scene,
  hidden,
  onHide,
  onOpenLog,
  voiceReplay,
  partnerPortraitNote,
  isStageLoading,
  quietStage,
  controlsProgressVisible,
  phaseLabel,
  viewingPast,
  canAct,
  actionMode,
  onActionModeChange,
  input,
  onInputChange,
  onSubmit,
  onSubmitTalk,
  speech,
  onOpenGiftShop,
  onOpenAttributes,
}: AdventureMessageBoxProps) {
  const { t } = useTranslation();
  const {
    activeRun,
    streaming,
    talking,
    phase,
    narrativeSettled,
    regenerateChoices,
    startEpilogue,
  } = useAdventure();
  const streamingNarrative = useAdventureStreamingNarrative();
  const messageTextRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!streamingNarrative) return;
    const node = messageTextRef.current;
    if (node) node.scrollTop = node.scrollHeight;
  }, [streamingNarrative]);
  if (!activeRun) return null;
  const {
    sim,
    activeAction,
    activeNarrative,
    isStreamingNarrative,
    availableChoices,
    partnerName,
    playerDisplayName,
    talkMode,
    currentTalkEntries,
    inventoryNote,
  } = scene;

  return (
    <section
      className={`adventure-messagebox${
        sim ? " adventure-messagebox--romance" : ""
      }${hidden ? " is-hidden" : ""}`}
      aria-live="polite"
      inert={hidden}
    >
      <div className="adventure-messagebox__meta">
        {sim && (
          <button
            type="button"
            className="adventure-messagebox__voice-button"
            disabled={!voiceReplay.canSpeak || !voiceReplay.text}
            aria-pressed={voiceReplay.active}
            aria-label={t("adventure.voice.replay")}
            title={t(
              voiceReplay.canSpeak
                ? "adventure.voice.replayHint"
                : "adventure.voice.disabledHint",
            )}
            onClick={voiceReplay.onToggle}
          >
            🔊
          </button>
        )}
        {partnerPortraitNote && (
          // section 自体が aria-live なので role="status" は付けない
          <span className="adventure-messagebox__portrait-note">
            <span aria-hidden>🖼</span>
            {t("adventure.partnerPortrait.note", {
              reason: t(
                `adventure.partnerPortrait.reason.${partnerPortraitReasonKey(
                  partnerPortraitNote.partnerStatus,
                )}`,
              ),
            })}
          </span>
        )}
        {inventoryNote && (
          <span className="adventure-messagebox__inventory-note">
            <span aria-hidden>🎒</span>
            {inventoryNote}
          </span>
        )}
        <button
          type="button"
          className="adventure-messagebox__log-button"
          onClick={onOpenLog}
          title={t("adventure.log.openHint")}
        >
          {t("adventure.log.open")}
        </button>
        <button
          type="button"
          className="adventure-messagebox__hide-button"
          onClick={onHide}
          title={t("adventure.window.hideHint")}
          aria-label={t("adventure.window.hide")}
          tabIndex={hidden ? -1 : undefined}
        >
          ✕
        </button>
      </div>

      {activeAction && (
        <p className="adventure-messagebox__action">
          <span>{t("adventure.yourAction")}</span>
          {activeAction}
        </p>
      )}

      <div className="adventure-messagebox__text" ref={messageTextRef}>
        {sim ? (
          // romance は台本形式(名前「セリフ」)の行を話者付きで描く。
          // 名前付き行が無い本文はそのまま1段落になる
          <div className="adventure-messagebox__narrative">
            <AdventureScriptText
              text={activeNarrative}
              speakers={[partnerName, playerDisplayName]}
            />
            {isStreamingNarrative && !narrativeSettled && (
              <span className="adventure-transcript__caret" />
            )}
          </div>
        ) : (
          <p className="adventure-messagebox__narrative">
            {activeNarrative}
            {isStreamingNarrative && !narrativeSettled && (
              <span className="adventure-transcript__caret" />
            )}
          </p>
        )}
        {streaming && !isStageLoading && !quietStage && (
          <div className="adventure-progress">
            <span />
            {phaseLabel}
          </div>
        )}
      </div>

      {canAct ? (
        <div className="adventure-controls">
          {viewingPast ? (
            // 過去の場面では行動UIを出さない。最新へ戻る導線はステージの過去バナーにある
            <p className="adventure-controls__past-hint">
              {t("adventure.viewingPastControlsHint")}
            </p>
          ) : (
            <>
              <div className="adventure-controls__header">
                {sim ? (
                  // romance: 行動(手番を消費) / トーク(消費しない会話)の切替
                  <div
                    className="adventure-segments adventure-segments--pair"
                    role="group"
                    aria-label={t("adventure.actionPanel.title")}
                  >
                    <button
                      type="button"
                      className={actionMode === "act" ? "is-active" : ""}
                      aria-pressed={actionMode === "act"}
                      onClick={() => onActionModeChange("act")}
                    >
                      {t("adventure.actionPanel.act")}
                    </button>
                    <button
                      type="button"
                      className={actionMode === "talk" ? "is-active" : ""}
                      aria-pressed={actionMode === "talk"}
                      title={t("adventure.actionPanel.talkHint")}
                      onClick={() => onActionModeChange("talk")}
                    >
                      {t("adventure.actionPanel.talk")}
                    </button>
                  </div>
                ) : (
                  <span className="adventure-controls__title">
                    {t("adventure.actionPanel.title")}
                  </span>
                )}
                {!talkMode && (
                  <button
                    type="button"
                    className="adventure-choices__regenerate"
                    onClick={() => void regenerateChoices()}
                    disabled={streaming || talking}
                    title={t("adventure.regenerateChoices")}
                  >
                    {streaming &&
                    phase === "clue_check" &&
                    !controlsProgressVisible
                      ? t("adventure.regeneratingChoices")
                      : t("adventure.regenerateChoices")}
                  </button>
                )}
              </div>

              {/* 3D モデル表示中はステージを覆わず、判定の進捗をここに出す */}
              {controlsProgressVisible && !talkMode && (
                <div
                  className="adventure-progress adventure-controls__progress"
                  role="status"
                >
                  <span />
                  {phaseLabel}
                </div>
              )}

              {/* 生成中は前ターンの選択肢が残留するため、無効化ではなく非表示にする */}
              {!streaming && !talkMode && (
                <div className="adventure-choices">
                  {availableChoices.map((choice, index) => (
                    <button
                      type="button"
                      key={choice.id}
                      title={choice.label}
                      onClick={() => onSubmit(choice.label, "choice")}
                    >
                      <span className="adventure-choices__key">
                        {index + 1}
                      </span>
                      {choice.label}
                    </button>
                  ))}
                </div>
              )}
              {!streaming && !talkMode && availableChoices.length === 0 && (
                <p className="adventure-choices__empty">
                  {t("adventure.emptyChoices")}
                </p>
              )}

              {/* romance 専用の行動ボタン行。どの行動も1スロット消費する。
              選択肢と同様、生成中は非表示にする */}
              {!streaming && sim && !talkMode && (
                <div className="adventure-romance-actions">
                  <button
                    type="button"
                    title={t("adventure.romance.workHint", {
                      job: sim.job.name,
                      wage: sim.job.wage.toLocaleString(),
                    })}
                    onClick={() =>
                      onSubmit(
                        t("adventure.romance.workAction", {
                          job: sim.job.name,
                        }),
                        "work",
                      )
                    }
                  >
                    {t("adventure.romance.workButton")}
                  </button>
                  <button
                    type="button"
                    title={t("adventure.romance.giftHint")}
                    onClick={onOpenGiftShop}
                  >
                    {t("adventure.romance.giftButton")}
                  </button>
                  <button
                    type="button"
                    title={t("adventure.romance.attributeHint")}
                    onClick={onOpenAttributes}
                  >
                    {t("adventure.romance.attributeButton")}
                  </button>
                  {sim.confession_available && (
                    <button
                      type="button"
                      className="is-confess"
                      title={t("adventure.romance.confessHint")}
                      onClick={() =>
                        onSubmit(
                          t("adventure.romance.confessAction", {
                            name: sim.partner_name,
                          }),
                          "confess",
                        )
                      }
                    >
                      {t("adventure.romance.confessButton")}
                    </button>
                  )}
                </div>
              )}

              {talkMode && (
                <AdventureTalkThread
                  entries={currentTalkEntries}
                  partnerName={partnerName}
                  playerDisplayName={playerDisplayName}
                />
              )}
              <AdventureFreeInput
                value={input}
                onChange={onInputChange}
                onSubmit={() => {
                  if (talkMode) {
                    onSubmitTalk(input);
                    return;
                  }
                  onSubmit(input, "free_text");
                }}
                talkMode={talkMode}
                partnerName={partnerName}
                busy={streaming || talking}
                speech={speech}
              />
            </>
          )}
        </div>
      ) : (
        <div className={`adventure-ending is-${activeRun.status}`}>
          <span>{t(`adventure.status.${activeRun.status}`)}</span>
          <h2>{activeRun.ending_title}</h2>
          <p>{activeRun.ending_summary}</p>
          {/* リザルトを閉じた後・再入場時の継続導線 */}
          <button
            type="button"
            className="adventure-ending__continue"
            disabled={streaming}
            onClick={() => void startEpilogue()}
          >
            {t("adventure.result.continueEpilogue")}
          </button>
        </div>
      )}
    </section>
  );
}
