import { useEffect, useId } from "react";
import { useTranslation } from "react-i18next";
import { useGame } from "../../contexts/GameContext";
import { useSettings } from "../../contexts/SettingsContext";
import { isAdultSalonTurn } from "../../utils/salonView";
import {
  NovelaiImageModelFields,
  NovelaiPromptFields,
  NovelaiTextModelField,
} from "../layout/rightPanel/NovelaiGenerationFields";

interface SalonGenerationSettingsProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * 接客画面の上端バーの ⚙ で開く生成の設定。施術は通常プレイと同じ手番で描くため、
 * 通常プレイの右パネルと同じ値(SettingsContext)をそのまま編集する。
 */
export default function SalonGenerationSettings({
  open,
  onOpenChange,
}: SalonGenerationSettingsProps) {
  const { t } = useTranslation();
  const { state: settingsState } = useSettings();
  const { state: game } = useGame();
  const panelId = useId();
  const isNovelAI = settingsState.imageProvider === "novelai";
  const adult = isAdultSalonTurn(game.request, settingsState.nsfwMode);

  useEffect(() => {
    if (!open) return;
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onOpenChange(false);
    };
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [open, onOpenChange]);

  return (
    <div className="salon-bgm">
      <button
        type="button"
        className="salon-bgm__button"
        aria-label={t("salon.generation.settings")}
        title={t("salon.generation.settings")}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => onOpenChange(!open)}
      >
        ⚙
      </button>
      {open && (
        <div
          id={panelId}
          className="salon-bgm__panel salon-generation__panel"
          role="dialog"
          aria-label={t("salon.generation.settings")}
        >
          <p className="salon-generation__note">
            {t("salon.generation.sharedNote")}
          </p>
          {!isNovelAI && (
            <p className="salon-generation__note salon-generation__note--warn">
              {t("salon.generation.otherProviderNote")}
            </p>
          )}
          <NovelaiPromptFields />
          <NovelaiImageModelFields />
          <p className="salon-generation__note">
            {adult
              ? t("salon.generation.modelNsfwInUse", {
                  label: t("settings.novelaiImageModelNsfw"),
                })
              : t("salon.generation.modelSfwInUse", {
                  label: t("settings.novelaiImageModelSfw"),
                })}
          </p>
          {settingsState.novelaiTier === 3 && (
            <>
              <NovelaiTextModelField />
              <p className="salon-generation__note">
                {t("salon.generation.textModelHint")}
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}
