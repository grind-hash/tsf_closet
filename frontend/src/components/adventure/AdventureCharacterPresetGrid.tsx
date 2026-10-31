import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { listCharacterPresets } from "../../apis/characters";
import { ROUTES } from "../../routes";
import type { CharacterPreset } from "../../types";
import { mediaUrl } from "../../utils/adventureFormat";

interface AdventureCharacterPresetGridProps {
  selectedPresetId: string | null;
  onSelect: (preset: CharacterPreset) => void;
}

/**
 * キャラクターメイクで作ったキャラクターのタイル一覧(TSFシナリオの開始素材・主人公の選択用)。
 * 開始画像に立ち絵の実ファイルが要るため、立ち絵の無いキャラクターは理由を添えて選べなくする。
 */
export default function AdventureCharacterPresetGrid({
  selectedPresetId,
  onSelect,
}: AdventureCharacterPresetGridProps) {
  const { t } = useTranslation();
  const [presets, setPresets] = useState<CharacterPreset[] | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(async () => {
    setFailed(false);
    setPresets(null);
    try {
      setPresets(await listCharacterPresets());
    } catch {
      setFailed(true);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (failed) {
    return (
      <p className="adventure-session-picker__status" role="alert">
        {t("adventure.sourcePicker.charactersLoadFailed")}
        <button type="button" onClick={() => void load()}>
          {t("gallery.retry")}
        </button>
      </p>
    );
  }
  if (presets === null) {
    return (
      <p className="adventure-session-picker__status">{t("gallery.loading")}</p>
    );
  }
  if (presets.length === 0) {
    return (
      <div className="adventure-session-picker__empty">
        <p>{t("adventure.sourcePicker.charactersEmpty")}</p>
        <Link to={ROUTES.CHARACTERS}>
          {t("adventure.sourcePicker.characterCreateLink")}
        </Link>
      </div>
    );
  }
  return (
    <div
      className="adventure-session-picker__grid"
      role="group"
      aria-label={t("adventure.sourcePicker.tabCharacters")}
    >
      {presets.map((preset) => {
        const usable = Boolean(preset.portrait_url);
        const isSelected = preset.id === selectedPresetId;
        const image = preset.portrait_url ?? preset.thumbnail_url;
        return (
          <button
            type="button"
            key={preset.id}
            className={isSelected ? "is-selected" : ""}
            data-selected={isSelected || undefined}
            disabled={!usable}
            onClick={() => onSelect(preset)}
          >
            <span className="adventure-session-picker__thumb adventure-session-picker__thumb--portrait">
              {image ? (
                <img src={mediaUrl(image)} alt="" />
              ) : (
                <span aria-hidden>👤</span>
              )}
            </span>
            <span className="adventure-session-picker__tile-name">
              {preset.name}
            </span>
            <span className="adventure-session-picker__tile-label adventure-session-picker__tile-label--persona">
              {preset.profile?.personality || t("characters.noPersonality")}
            </span>
            {!usable && (
              <small className="adventure-session-picker__tile-note">
                {t("adventure.sourcePicker.characterNoPortrait")}
              </small>
            )}
          </button>
        );
      })}
    </div>
  );
}
