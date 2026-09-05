import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import type { AdventureSettingsUpdateRequest } from "../../apis/adventure";
import { useAdventure } from "../../contexts/AdventureContext";
import { useSettings } from "../../contexts/SettingsContext";
import { ROUTES } from "../../routes";
import type { AdventureTurnImageSettings } from "../../utils/adventureTurnTimeEstimate";
import {
  AvatarModelOptions,
  AvatarWardrobeHint,
} from "./AdventureAvatarOptions";
import {
  AdventureImageModelPicker,
  AdventureToggleRow,
  AdventureTurnEstimate,
} from "./AdventureImageOptionRows";

interface AdventureImageSettingsPopoverProps {
  /** 生成時間の見積もりに使う現在の設定 */
  imageSettings: AdventureTurnImageSettings;
  /** run のモデル上書きを含めた実効モデルが V5 か(精密参照は非対応) */
  runIsV5: boolean;
  isCompanion: boolean;
  drawPortraitEveryTurn: boolean;
  onDrawPortraitEveryTurnChange: (next: boolean) => void;
  drawPartnerEveryTurn: boolean;
  onDrawPartnerEveryTurnChange: (next: boolean) => void;
  /** ENABLE_PROMPT_PREVIEW のときだけ出る確認用の入口 */
  onOpenPromptPreview: () => void;
}

/**
 * ステージ右上の ⚙ で開く画像設定。run 単位の設定(サーバへ保存)と
 * ブラウザ単位の好み(立ち絵を毎ターン描くか)を並べる。
 */
export default function AdventureImageSettingsPopover({
  imageSettings,
  runIsV5,
  isCompanion,
  drawPortraitEveryTurn,
  onDrawPortraitEveryTurnChange,
  drawPartnerEveryTurn,
  onDrawPartnerEveryTurnChange,
  onOpenPromptPreview,
}: AdventureImageSettingsPopoverProps) {
  const { t } = useTranslation();
  const { activeRun, streaming, updateSettings, avatarModels } = useAdventure();
  const { state: settingsState } = useSettings();
  const [saving, setSaving] = useState(false);
  if (!activeRun) return null;

  // 各 run 設定の更新は精密参照・合成の現在値を必ず同送する(API の必須項目)
  const saveRunSettings = (patch: Partial<AdventureSettingsUpdateRequest>) => {
    setSaving(true);
    void updateSettings({
      use_precise_reference: activeRun.use_precise_reference,
      enable_composite_scene: activeRun.enable_composite_scene,
      ...patch,
    })
      .catch(() => undefined)
      .finally(() => setSaving(false));
  };
  const busy = streaming || saving;

  return (
    <div className="adventure-image-settings-popover">
      <AdventureTurnEstimate settings={imageSettings} />
      {/* この run 専用のNovelAI画像モデル。次の画像生成から反映される */}
      <AdventureImageModelPicker
        value={activeRun.image_model_override ?? "default"}
        hint={t(
          settingsState.imageProvider === "novelai"
            ? "adventure.imageModelPlayHint"
            : "adventure.imageModelOtherProviderHint",
        )}
        disabled={busy}
        onChange={(next) => saveRunSettings({ image_model: next })}
      />
      {/* 持ち物システム(全プリセット)。作品シナリオは対象外。次の手番から反映 */}
      {!activeRun.scenario_template_id && (
        <AdventureToggleRow
          className="adventure-inventory-toggle"
          label={t("adventure.inventoryEnable")}
          hint={t("adventure.inventoryPlayHint")}
          checked={activeRun.inventory_enabled}
          disabled={busy}
          onChange={(next) => saveRunSettings({ inventory_enabled: next })}
        />
      )}
      {/* 対面会話モード(romance 専用)。次の手番から反映 */}
      {activeRun.preset === "romance" && (
        <AdventureToggleRow
          className="adventure-companion-toggle"
          label={t("adventure.companionMode")}
          hint={t("adventure.companionModePlayHint")}
          checked={isCompanion}
          disabled={busy}
          onChange={(next) => saveRunSettings({ companion_mode: next })}
        />
      )}
      {/* 3D モデル(VRM)。対面会話モード OFF でも隠さず、文言で説明する */}
      {activeRun.preset === "romance" && (
        <label className="adventure-setup-turns adventure-setup-avatar">
          <span className="adventure-setup-turns__label">
            {t("adventure.avatar.selectLabel")}
          </span>
          <select
            value={activeRun.companion_avatar_id ?? ""}
            disabled={busy}
            onChange={(event) =>
              saveRunSettings({
                companion_avatar_id: event.target.value || "none",
              })
            }
          >
            <option value="">{t("adventure.avatar.none")}</option>
            {activeRun.companion_avatar_id &&
              !avatarModels.some(
                (model) => model.id === activeRun.companion_avatar_id,
              ) && (
                <option value={activeRun.companion_avatar_id} disabled>
                  {t("adventure.avatar.deletedModel")}
                </option>
              )}
            <AvatarModelOptions models={avatarModels} />
          </select>
          <span className="adventure-setup-turns__hint">
            {avatarModels.length === 0 ? (
              <>
                {t("adventure.avatar.noModelsHint")}{" "}
                <Link to={ROUTES.SETTINGS}>
                  {t("adventure.avatar.registerLink")}
                </Link>
              </>
            ) : isCompanion ? (
              t("adventure.avatar.playHint")
            ) : (
              t("adventure.avatar.companionOffHint")
            )}
          </span>
          <AvatarWardrobeHint
            models={avatarModels}
            selectedId={activeRun.companion_avatar_id}
          />
        </label>
      )}
      {/* NovelAI以外では効果もAnlas消費もない旨、V5では非対応の旨を明示する */}
      <AdventureToggleRow
        label={t("adventure.preciseReference")}
        hint={t(
          runIsV5
            ? "adventure.preciseReferenceV5Hint"
            : settingsState.imageProvider === "novelai"
              ? "adventure.preciseReferencePlayHint"
              : "adventure.preciseReferenceOtherProviderHint",
        )}
        checked={activeRun.use_precise_reference && !runIsV5}
        disabled={busy || runIsV5}
        onChange={(next) => saveRunSettings({ use_precise_reference: next })}
      />
      <AdventureToggleRow
        label={t("adventure.enableCompositeScene")}
        hint={t(
          isCompanion
            ? "adventure.enableCompositeSceneCompanionHint"
            : "adventure.enableCompositeScenePlayHint",
        )}
        checked={activeRun.enable_composite_scene}
        disabled={busy}
        onChange={(next) => saveRunSettings({ enable_composite_scene: next })}
      />
      {/* 立ち絵の毎ターン描画は合成・精密参照の設定に関わらず効くため常に表示する */}
      <AdventureToggleRow
        label={t("adventure.drawPortraitEveryTurn")}
        hint={t(
          isCompanion
            ? "adventure.drawPortraitEveryTurnCompanionHint"
            : "adventure.drawPortraitEveryTurnHint",
        )}
        checked={drawPortraitEveryTurn}
        disabled={streaming}
        onChange={onDrawPortraitEveryTurnChange}
      />
      {activeRun.preset === "romance" && (
        <AdventureToggleRow
          label={t("adventure.drawPartnerEveryTurn")}
          hint={t("adventure.drawPartnerEveryTurnHint")}
          checked={drawPartnerEveryTurn}
          disabled={streaming}
          onChange={onDrawPartnerEveryTurnChange}
        />
      )}
      {activeRun.enable_prompt_preview && (
        <button
          type="button"
          className="adventure-hud__panel-action"
          onClick={onOpenPromptPreview}
        >
          {t("adventure.promptPreview.open")}
        </button>
      )}
    </div>
  );
}
