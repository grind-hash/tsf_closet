import { useTranslation } from "react-i18next";
import { useChat } from "../../contexts/ChatContext";
import { useGame } from "../../contexts/GameContext";
import { useSettings } from "../../contexts/SettingsContext";
import MemorySettings from "../settings/MemorySettings";
import PlayMemorySettings from "../settings/PlayMemorySettings";
import AivisEngineSection from "./rightPanel/AivisEngineSection";
import AttributesSection from "./rightPanel/AttributesSection";
import ClothingLayersSection from "./rightPanel/ClothingLayersSection";
import LanguageSection from "./rightPanel/LanguageSection";
import NovelaiSettingsSection from "./rightPanel/NovelaiSettingsSection";
import PromptPreviewSection from "./rightPanel/PromptPreviewSection";
import SettingsSummarySection from "./rightPanel/SettingsSummarySection";
import "./RightPanel.css";

interface RightPanelProps {
  onClose?: () => void;
  onOpenInpaintModal?: () => void;
  onSendWithPromptOverride?: (override: string) => void;
}

/**
 * 通常プレイの右パネル。セクションごとの中身は rightPanel/ 配下に分け、
 * ここでは表示条件と並び順だけを持つ。
 */
export default function RightPanel({
  onClose,
  onOpenInpaintModal,
  onSendWithPromptOverride,
}: RightPanelProps) {
  const { t } = useTranslation();
  const { state: settingsState } = useSettings();
  const { state: gameState } = useGame();
  const { state: chatState } = useChat();
  const isNovelAI = settingsState.imageProvider === "novelai";

  return (
    <div className="right-panel">
      <div className="right-panel__header">
        <h3 className="right-panel__title">{t("rightPanel.title")}</h3>
        <button
          type="button"
          className="right-panel__close-btn"
          onClick={onClose}
          aria-label={t("rightPanel.closePanel")}
        >
          ✕
        </button>
      </div>

      <div className="right-panel__content">
        {/* 音声合成エンジンの起動・停止 */}
        {settingsState.ttsEnabled && <AivisEngineSection />}

        <AttributesSection />

        <ClothingLayersSection />

        {/* NovelAI詳細設定 - NovelAIのみ表示(インペイントトグルはCharacterStatePanelに移動済み) */}
        {isNovelAI && (
          <NovelaiSettingsSection onOpenInpaintModal={onOpenInpaintModal} />
        )}

        {/* プロンプトプレビューセクション */}
        {gameState.stats?.enablePromptPreview &&
          chatState.instructionType !== "conversation" && (
            <PromptPreviewSection
              onSendWithPromptOverride={onSendWithPromptOverride}
            />
          )}

        <LanguageSection />

        {settingsState.playMemoryEnabled && (
          <section className="right-panel__section">
            <h4 className="right-panel__section-title">
              {t("settings.playMemory.sectionTitle")}
            </h4>
            <PlayMemorySettings />
          </section>
        )}

        {/* 好みメモリ機能 */}
        <section className="right-panel__section">
          <h4 className="right-panel__section-title">
            {t("settings.memory.sectionTitle")}
          </h4>
          <MemorySettings />
        </section>

        <SettingsSummarySection />
      </div>
    </div>
  );
}
