import type { TFunction } from "i18next";
import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  HAKONIWA_PLAYER_NAME_MAX,
  type HakoniwaMemoLookGroup,
  type HakoniwaTheme,
} from "../../apis/hakoniwa";
import {
  ADVENTURE_IMAGE_MODEL_CHOICES,
  isV5ImageModel,
} from "../../constants/novelaiImageModels";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import { useSettings } from "../../contexts/SettingsContext";
import { ROUTES } from "../../routes";
import { NovelaiUsageBar } from "../NovelaiUsageBar";
import WebSearchTermsDialog, {
  type WebSearchTermsMode,
} from "../settings/WebSearchTermsDialog";
import ConfirmDialog from "../ui/ConfirmDialog";
import HakoniwaMemoLookDialog, {
  MEMO_LOOK_GENDERS,
} from "./HakoniwaMemoLookDialog";
import HakoniwaPresencePicker from "./HakoniwaPresencePicker";
import {
  LookControls,
  type LookRequest,
  lookConfirmBodyKey,
} from "./HakoniwaRulesTab";
import HakoniwaThemePicker, { normalizeTheme } from "./HakoniwaThemePicker";

const DEFAULT_MODEL = "default";
const MEMO_MAX = 1000;

function modelLabel(model: string): string {
  return (
    ADVENTURE_IMAGE_MODEL_CHOICES.find((choice) => choice.value === model)
      ?.label ?? model
  );
}

/** 設定タブ: 画像モデル、Web検索、あなたの名前、世界のメモ、世界の違和感、世界の削除 */
export default function HakoniwaSettingsTab() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { state: settingsState } = useSettings();
  const {
    world,
    busy,
    setImageModel,
    setDissonanceEnabled,
    setPlayerPresence,
    setWebSearchEnabled,
    setWorldMemo,
    setPlayerName,
    setExperimentTheme,
    deleteWorld,
    lookTarget,
    lookProgress,
    generateLook,
    applyMemoLook,
    playbackQueue,
    openOpening,
  } = useHakoniwa();
  // Web 検索を ON にするときは、設定画面と同じ利用条件への同意を確かめる
  const [termsMode, setTermsMode] = useState<WebSearchTermsMode | null>(null);
  const [confirmMemoLook, setConfirmMemoLook] = useState<LookRequest | null>(
    null,
  );
  const modelId = useId();
  const dissonanceId = useId();
  const webSearchId = useId();
  const memoId = useId();
  const playerNameId = useId();
  const savedMemo = world?.world_memo ?? "";
  const [memo, setMemo] = useState(savedMemo);
  const savedPlayerName = world?.player_name ?? "";
  const [playerName, setPlayerNameDraft] = useState(savedPlayerName);

  const savedTheme = world?.experiment_theme ?? null;
  const savedThemeKey = JSON.stringify(savedTheme);
  const [themeDraft, setThemeDraft] = useState<HakoniwaTheme | null>(
    savedTheme,
  );

  // 別の世界を開いたり保存したりしたら、欄を保存済みの内容にそろえる
  useEffect(() => {
    setMemo(savedMemo);
  }, [savedMemo]);
  useEffect(() => {
    setPlayerNameDraft(savedPlayerName);
  }, [savedPlayerName]);
  useEffect(() => {
    setThemeDraft(JSON.parse(savedThemeKey) as HakoniwaTheme | null);
  }, [savedThemeKey]);
  const themeChanged =
    JSON.stringify(normalizeTheme(themeDraft)) !== savedThemeKey;
  const [confirmDelete, setConfirmDelete] = useState(false);

  if (!world) return null;
  const usage = settingsState.anlasBalance?.usage;
  const showUsage =
    settingsState.imageProvider === "novelai" &&
    isV5ImageModel(world.image_model_effective) &&
    usage != null;

  return (
    <div className="hakoniwa-settings">
      <section className="hakoniwa-settings__section">
        <label className="hakoniwa-field" htmlFor={modelId}>
          <span>{t("hakoniwa.settings.imageModelHeading")}</span>
          <select
            id={modelId}
            value={world.image_model}
            disabled={busy !== null}
            onChange={(event) => void setImageModel(event.target.value)}
          >
            <option value={DEFAULT_MODEL}>
              {t("hakoniwa.settings.imageModelDefault", {
                model: modelLabel(world.image_model_default),
              })}
            </option>
            {world.image_model_options.map((model) => (
              <option key={model} value={model}>
                {modelLabel(model)}
              </option>
            ))}
          </select>
        </label>
        <p className="hakoniwa-note">
          {world.transparency === "native"
            ? t("hakoniwa.settings.transparencyNative")
            : t("hakoniwa.settings.transparencyRemoval")}
        </p>
        <p className="hakoniwa-note">{t("hakoniwa.settings.providerNote")}</p>
      </section>

      <section className="hakoniwa-settings__section">
        <label className="hakoniwa-toggle" htmlFor={webSearchId}>
          <span>{t("hakoniwa.settings.webSearchToggle")}</span>
          <input
            id={webSearchId}
            type="checkbox"
            className="hakoniwa-toggle__input"
            checked={world.web_search_enabled ?? false}
            disabled={busy !== null}
            onChange={(event) => {
              if (event.target.checked) setTermsMode("consent");
              else void setWebSearchEnabled(false);
            }}
          />
          <span className="hakoniwa-toggle__switch" aria-hidden />
        </label>
        <p className="hakoniwa-note">{t("hakoniwa.settings.webSearchNote")}</p>
        <button
          type="button"
          className="hakoniwa-link-button"
          onClick={() => setTermsMode("read")}
        >
          {t("hakoniwa.settings.webSearchTerms")}
        </button>
        {!world.web_search_configured && (
          <p className="hakoniwa-note">
            {t("hakoniwa.settings.webSearchUnavailable")}
          </p>
        )}
      </section>

      <section className="hakoniwa-settings__section">
        <label className="hakoniwa-field" htmlFor={playerNameId}>
          <span>{t("hakoniwa.settings.playerNameHeading")}</span>
          <input
            id={playerNameId}
            type="text"
            value={playerName}
            maxLength={HAKONIWA_PLAYER_NAME_MAX}
            placeholder={t("hakoniwa.settings.playerNamePlaceholder")}
            onChange={(event) => setPlayerNameDraft(event.target.value)}
          />
        </label>
        <div className="hakoniwa-settings__memo-actions">
          <span className="hakoniwa-note">
            {savedPlayerName
              ? t("hakoniwa.settings.playerNameSet", { name: savedPlayerName })
              : t("hakoniwa.settings.playerNameUnset")}
          </span>
          <button
            type="button"
            className="hakoniwa-button"
            disabled={busy !== null || playerName.trim() === savedPlayerName}
            onClick={() => void setPlayerName(playerName.trim())}
          >
            {t("hakoniwa.settings.playerNameSave")}
          </button>
        </div>
        <p className="hakoniwa-note">{t("hakoniwa.settings.playerNameNote")}</p>
      </section>

      <section className="hakoniwa-settings__section">
        <label className="hakoniwa-field" htmlFor={memoId}>
          <span>{t("hakoniwa.settings.memoHeading")}</span>
          <textarea
            id={memoId}
            rows={5}
            value={memo}
            maxLength={MEMO_MAX}
            placeholder={t("hakoniwa.settings.memoPlaceholder")}
            onChange={(event) => setMemo(event.target.value)}
          />
        </label>
        <div className="hakoniwa-settings__memo-actions">
          <span className="hakoniwa-note">
            {t("hakoniwa.settings.memoCount", {
              count: memo.length,
              max: MEMO_MAX,
            })}
          </span>
          <button
            type="button"
            className="hakoniwa-button"
            disabled={busy !== null || memo.trim() === savedMemo}
            onClick={() => void setWorldMemo(memo.trim())}
          >
            {t("hakoniwa.settings.memoSave")}
          </button>
        </div>
        <p className="hakoniwa-note">{t("hakoniwa.settings.memoNote")}</p>
        {savedMemo && (
          <MemoLookStatus
            planning={
              lookTarget === "memo" && lookProgress === null && busy === "look"
            }
            locked={busy !== null || playbackQueue.length > 0}
            onCheck={() => void applyMemoLook(world.id)}
            onRequest={(request) => setConfirmMemoLook(request)}
          />
        )}
      </section>

      <section className="hakoniwa-settings__section">
        <HakoniwaThemePicker
          key={savedThemeKey}
          value={savedTheme}
          onChange={setThemeDraft}
          disabled={busy !== null}
        />
        <div className="hakoniwa-settings__memo-actions">
          <span />
          <button
            type="button"
            className="hakoniwa-button"
            disabled={busy !== null || !themeChanged}
            onClick={() => void setExperimentTheme(normalizeTheme(themeDraft))}
          >
            {t("hakoniwa.theme.save")}
          </button>
        </div>
      </section>

      <section className="hakoniwa-settings__section">
        <HakoniwaPresencePicker
          value={world.player_presence ?? "known"}
          onChange={(presence) => void setPlayerPresence(presence)}
          dissonanceEnabled={world.dissonance.enabled}
          disabled={busy !== null}
          extraNote={t("hakoniwa.presence.switchNote")}
        />
      </section>

      <section className="hakoniwa-settings__section">
        <label className="hakoniwa-toggle" htmlFor={dissonanceId}>
          <span>{t("hakoniwa.settings.dissonanceToggle")}</span>
          <input
            id={dissonanceId}
            type="checkbox"
            className="hakoniwa-toggle__input"
            checked={world.dissonance.enabled}
            disabled={busy !== null}
            onChange={(event) =>
              void setDissonanceEnabled(event.target.checked)
            }
          />
          <span className="hakoniwa-toggle__switch" aria-hidden />
        </label>
        <p className="hakoniwa-note">{t("hakoniwa.settings.dissonanceNote")}</p>
      </section>

      {showUsage && usage && (
        <section className="hakoniwa-settings__section">
          <strong>{t("hakoniwa.settings.usageHeading")}</strong>
          <NovelaiUsageBar usage={usage} compact />
        </section>
      )}

      <section className="hakoniwa-settings__section">
        <button
          type="button"
          className="hakoniwa-button hakoniwa-button--ghost"
          onClick={() => openOpening(true)}
          disabled={playbackQueue.length > 0}
        >
          {t("hakoniwa.opening.replay")}
        </button>
      </section>

      <section className="hakoniwa-settings__section">
        <strong>{t("hakoniwa.settings.deleteHeading")}</strong>
        <button
          type="button"
          className="hakoniwa-button hakoniwa-button--ghost"
          onClick={() => setConfirmDelete(true)}
          disabled={busy !== null}
        >
          {t("hakoniwa.settings.deleteWorld")}
        </button>
      </section>

      <WebSearchTermsDialog
        mode={termsMode}
        variant="hakoniwa"
        onAccept={() => void setWebSearchEnabled(true)}
        onClose={() => setTermsMode(null)}
        testId="hakoniwa-world-web-search-terms"
      />
      <ConfirmDialog
        open={confirmMemoLook !== null}
        title={t("hakoniwa.rules.lookConfirmTitle")}
        confirmLabel={t("hakoniwa.rules.lookConfirm", {
          count: confirmMemoLook?.count ?? 0,
        })}
        cancelLabel={t("hakoniwa.residentForm.cancel")}
        onCancel={() => setConfirmMemoLook(null)}
        onConfirm={() => {
          if (confirmMemoLook) {
            generateLook(
              confirmMemoLook.target,
              confirmMemoLook.regenerate,
              confirmMemoLook.residentIds,
            );
          }
          setConfirmMemoLook(null);
        }}
      >
        <p>
          {t(lookConfirmBodyKey(confirmMemoLook), {
            label: confirmMemoLook?.label ?? "",
            count: confirmMemoLook?.count ?? 0,
          })}
        </p>
      </ConfirmDialog>
      <ConfirmDialog
        open={confirmDelete}
        title={t("hakoniwa.hub.deleteTitle")}
        confirmLabel={t("hakoniwa.hub.deleteConfirm")}
        cancelLabel={t("hakoniwa.residentForm.cancel")}
        busy={busy === "delete"}
        onCancel={() => setConfirmDelete(false)}
        onConfirm={() => {
          void deleteWorld(world.id).then(() => {
            setConfirmDelete(false);
            navigate(ROUTES.HAKONIWA);
          });
        }}
      >
        <p>{t("hakoniwa.hub.deleteBody", { name: world.name })}</p>
      </ConfirmDialog>
    </div>
  );
}

/** 本来の性別が同じ住民たちへのメモの姿を1行の文にする */
function memoGroupText(
  t: TFunction,
  group: HakoniwaMemoLookGroup | null,
): string {
  if (!group) return t("hakoniwa.settings.memoLookUnchanged");
  const body = group.body_gender
    ? t("hakoniwa.settings.memoLookBody", {
        gender: t(`hakoniwa.gender.${group.body_gender}`),
      })
    : t("hakoniwa.settings.memoLookBodyKeep");
  if (!group.tags) return body;
  return t("hakoniwa.settings.memoLookLine", {
    look: t("hakoniwa.settings.memoLookTags", { tags: group.tags }),
    body,
  });
}

/**
 * 世界のメモが住民に与える姿の状態。姿に関わるかを確かめている間はスピナー、関わるなら
 * 本来の性別ごとの見た目と生成状況、関わらないならその旨を出す。どの状態でも、姿を手で
 * 直すことと、メモから決め直すことができる
 */
function MemoLookStatus({
  planning,
  locked,
  onCheck,
  onRequest,
}: {
  planning: boolean;
  locked: boolean;
  onCheck: () => void;
  onRequest: (request: LookRequest) => void;
}) {
  const { t } = useTranslation();
  const { world, applyMemoLook } = useHakoniwa();
  const [editing, setEditing] = useState(false);
  const [confirmRecheck, setConfirmRecheck] = useState(false);
  if (!world) return null;
  const memoLook = world.memo_look ?? null;
  if (planning) {
    return (
      <div className="hakoniwa-progress" role="status">
        <span className="hakoniwa-spinner" aria-hidden />
        {t("hakoniwa.settings.memoLookPlanning")}
      </div>
    );
  }
  const recheck = () => void applyMemoLook(world.id, true);
  const actions = (
    <div className="hakoniwa-settings__memo-look-actions">
      <button
        type="button"
        className="hakoniwa-button hakoniwa-button--ghost"
        onClick={() => setEditing(true)}
        disabled={locked}
      >
        {t("hakoniwa.settings.memoLookEdit")}
      </button>
      {(memoLook || world.memo_look_planned) && (
        <button
          type="button"
          className="hakoniwa-button hakoniwa-button--ghost"
          // 手で直した姿は LLM の判断に置き換わるので、先に確かめる
          onClick={() =>
            memoLook?.edited ? setConfirmRecheck(true) : recheck()
          }
          disabled={locked}
        >
          {t("hakoniwa.settings.memoLookRecheck")}
        </button>
      )}
    </div>
  );
  const dialogs = (
    <>
      {editing && <HakoniwaMemoLookDialog onClose={() => setEditing(false)} />}
      <ConfirmDialog
        open={confirmRecheck}
        title={t("hakoniwa.settings.memoLookRecheckTitle")}
        confirmLabel={t("hakoniwa.settings.memoLookRecheck")}
        cancelLabel={t("hakoniwa.residentForm.cancel")}
        onCancel={() => setConfirmRecheck(false)}
        onConfirm={() => {
          setConfirmRecheck(false);
          recheck();
        }}
      >
        <p>{t("hakoniwa.settings.memoLookRecheckBody")}</p>
      </ConfirmDialog>
    </>
  );
  if (memoLook) {
    return (
      <div className="hakoniwa-settings__memo-look">
        <div className="hakoniwa-settings__memo-look-head">
          <strong>{t("hakoniwa.settings.memoLookHeading")}</strong>
          {actions}
        </div>
        <ul className="hakoniwa-settings__memo-look-groups">
          {MEMO_LOOK_GENDERS.map((gender) => (
            <li key={gender}>
              <span className="hakoniwa-settings__memo-look-group">
                {t(`hakoniwa.settings.memoLookGroup.${gender}`)}
              </span>
              <span>{memoGroupText(t, memoLook.groups[gender])}</span>
            </li>
          ))}
        </ul>
        {memoLook.edited && (
          <p className="hakoniwa-note">
            {t("hakoniwa.settings.memoLookEdited")}
          </p>
        )}
        <LookControls
          status={memoLook}
          target="memo"
          label={t("hakoniwa.settings.memoLookLabel")}
          disabled={locked}
          onRequest={onRequest}
        />
        {dialogs}
      </div>
    );
  }
  if (world.memo_look_planned) {
    return (
      <div className="hakoniwa-settings__memo-look">
        <div className="hakoniwa-settings__memo-look-head">
          <p className="hakoniwa-note">{t("hakoniwa.settings.memoLookNone")}</p>
          {actions}
        </div>
        {dialogs}
      </div>
    );
  }
  return (
    <div className="hakoniwa-settings__memo-look">
      <p className="hakoniwa-note">
        {t("hakoniwa.settings.memoLookUnchecked")}
      </p>
      <div className="hakoniwa-settings__memo-look-actions">
        <button
          type="button"
          className="hakoniwa-button hakoniwa-button--ghost"
          onClick={onCheck}
          disabled={locked}
        >
          {t("hakoniwa.settings.memoLookCheck")}
        </button>
        <button
          type="button"
          className="hakoniwa-button hakoniwa-button--ghost"
          onClick={() => setEditing(true)}
          disabled={locked}
        >
          {t("hakoniwa.settings.memoLookEdit")}
        </button>
      </div>
      {dialogs}
    </div>
  );
}
