import { useEffect, useId, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  type HakoniwaPlayerPresence,
  type HakoniwaRandomResident,
  type HakoniwaTheme,
  type HakoniwaWorldSummary,
  hakoniwaMediaUrl,
} from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import { useSettings } from "../../contexts/SettingsContext";
import { getHakoniwaWorldPath } from "../../routes";
import { mediaUrl } from "../../utils/adventureFormat";
import { readStorageFlag, writeStorageFlag } from "../../utils/storage";
import MainLayout from "../layout/MainLayout";
import ConfirmDialog from "../ui/ConfirmDialog";
import HakoniwaCharacterAdder, {
  type HakoniwaPickedCharacter,
} from "./HakoniwaCharacterAdder";
import HakoniwaErrorBanner from "./HakoniwaErrorBanner";
import type { HakoniwaWorldLocationState } from "./HakoniwaOpening";
import HakoniwaPortrait from "./HakoniwaPortrait";
import HakoniwaPresencePicker from "./HakoniwaPresencePicker";
import HakoniwaRandomRoster from "./HakoniwaRandomRoster";
import HakoniwaThemePicker, { normalizeTheme } from "./HakoniwaThemePicker";
import {
  ALL_WORLDS,
  filterWorlds,
  type HakoniwaWorldFilter,
  worldFacetCounts,
  worldPresence,
} from "./worldFilters";

const PRESENCE_FILTERS: HakoniwaWorldFilter["presence"][] = [
  "all",
  "known",
  "hidden",
];
/** 作成画面の「高度な設定」を開いているか(ブラウザに覚える) */
const ADVANCED_OPEN_KEY = "hakoniwa.createAdvancedOpen";
const WORLD_NAME_MAX = 50;
const MIN_RESIDENTS = 2;
const MAX_RESIDENTS = 10;

/** 世界の一覧と、新しい世界の作成(住民の顔ぶれを選ぶ) */
export default function HakoniwaHub() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const {
    catalog,
    worlds,
    busy,
    loadCatalog,
    loadWorlds,
    createWorld,
    deleteWorld,
  } = useHakoniwa();
  const { state: settingsState } = useSettings();
  // 設定画面「AI箱庭」の新しい世界の既定(住民とあなた・違和感は、ここで変えられる)
  const defaults = settingsState.hakoniwaPreferences;
  const nameId = useId();
  const dissonanceId = useId();
  const advancedId = useId();
  const [advancedOpen, setAdvancedOpen] = useState(() =>
    readStorageFlag("local", ADVANCED_OPEN_KEY),
  );
  const toggleAdvanced = () => {
    const next = !advancedOpen;
    setAdvancedOpen(next);
    writeStorageFlag("local", ADVANCED_OPEN_KEY, next);
  };
  const [dissonanceEnabled, setDissonanceEnabled] = useState(
    defaults.dissonanceEnabled,
  );
  const [playerPresence, setPlayerPresence] = useState<HakoniwaPlayerPresence>(
    defaults.playerPresence,
  );
  const [name, setName] = useState("");
  const [presetIds, setPresetIds] = useState<string[] | null>(null);
  const [characters, setCharacters] = useState<HakoniwaPickedCharacter[]>([]);
  const [randomResidents, setRandomResidents] = useState<
    HakoniwaRandomResident[]
  >([]);
  const [theme, setTheme] = useState<HakoniwaTheme | null>(null);
  const [worldFilter, setWorldFilter] =
    useState<HakoniwaWorldFilter>(ALL_WORLDS);
  const shownWorlds = useMemo(
    () => filterWorlds(worlds, worldFilter),
    [worlds, worldFilter],
  );
  const facets = useMemo(
    () => worldFacetCounts(worlds, worldFilter),
    [worlds, worldFilter],
  );
  const [deleteTarget, setDeleteTarget] = useState<HakoniwaWorldSummary | null>(
    null,
  );

  useEffect(() => {
    void loadCatalog();
    void loadWorlds();
  }, [loadCatalog, loadWorlds]);

  const presets = catalog?.presets ?? [];
  const chosenPresets = presetIds ?? presets.map((preset) => preset.id);
  const fixedCount = chosenPresets.length + characters.length;
  const count = fixedCount + randomResidents.length;
  // 高度な設定を閉じているときに見出しへ出す、選んでいる内容
  const chosenTheme = normalizeTheme(theme);
  const advancedSummary = [
    randomResidents.length > 0
      ? t("hakoniwa.hub.advancedRandom", { count: randomResidents.length })
      : null,
    chosenTheme
      ? t("hakoniwa.hub.advancedTheme", {
          name:
            chosenTheme.text || !chosenTheme.preset_id
              ? t("hakoniwa.theme.custom")
              : t(`hakoniwa.theme.presets.${chosenTheme.preset_id}.name`),
        })
      : null,
  ]
    .filter(Boolean)
    .join(t("hakoniwa.panel.listJoin"));
  // おまかせの住民と名前を重ねない(選んだプリセットとキャラクター)
  const takenNames = [
    ...presets
      .filter((preset) => chosenPresets.includes(preset.id))
      .map((preset) => preset.name),
    ...characters.map((item) => item.name),
  ];
  const canCreate =
    count >= MIN_RESIDENTS && count <= MAX_RESIDENTS && busy === null;

  const togglePreset = (id: string) => {
    setPresetIds(
      chosenPresets.includes(id)
        ? chosenPresets.filter((item) => item !== id)
        : [...chosenPresets, id],
    );
  };

  const handleCreate = async () => {
    const created = await createWorld({
      name: name.trim() || t("hakoniwa.hub.defaultName"),
      presetIds: presets
        .map((preset) => preset.id)
        .filter((id) => chosenPresets.includes(id)),
      characters: characters.map((item) => ({
        character_preset_id: item.character_preset_id,
        gender: item.gender,
      })),
      dissonanceEnabled,
      playerPresence,
      playerName: defaults.playerName,
      webSearchEnabled: defaults.webSearchEnabled,
      customResidents: randomResidents,
      theme: normalizeTheme(theme),
    });
    if (created) {
      setName("");
      setCharacters([]);
      setRandomResidents([]);
      setTheme(null);
      // 作った直後だけ開幕を流す(再読み込みや「戻る」では流さない)
      navigate(getHakoniwaWorldPath(created.id), {
        state: { opening: true } satisfies HakoniwaWorldLocationState,
      });
    }
  };

  return (
    <MainLayout>
      <div className="hakoniwa-page">
        <header className="hakoniwa-page__header">
          <p className="hakoniwa-eyebrow">{t("hakoniwa.eyebrow")}</p>
          <h1>{t("hakoniwa.title")}</h1>
          <p className="hakoniwa-page__lead">{t("hakoniwa.lead")}</p>
        </header>

        <HakoniwaErrorBanner />

        <section className="hakoniwa-card">
          <h2>{t("hakoniwa.hub.createHeading")}</h2>
          <label className="hakoniwa-field" htmlFor={nameId}>
            <span>{t("hakoniwa.hub.nameLabel")}</span>
            <input
              id={nameId}
              type="text"
              value={name}
              maxLength={WORLD_NAME_MAX}
              placeholder={t("hakoniwa.hub.namePlaceholder")}
              onChange={(event) => setName(event.target.value)}
            />
          </label>

          <h3>{t("hakoniwa.hub.presetsHeading")}</h3>
          <p className="hakoniwa-note">{t("hakoniwa.hub.presetsNote")}</p>
          <ul className="hakoniwa-roster">
            {presets.map((preset) => {
              const chosen = chosenPresets.includes(preset.id);
              return (
                <li key={preset.id}>
                  <button
                    type="button"
                    className={`hakoniwa-roster__item${chosen ? " is-chosen" : ""}`}
                    aria-pressed={chosen}
                    onClick={() => togglePreset(preset.id)}
                  >
                    <HakoniwaPortrait
                      src={hakoniwaMediaUrl(preset.avatar_url)}
                      alt=""
                      className="hakoniwa-roster__portrait"
                    />
                    <span className="hakoniwa-roster__name">{preset.name}</span>
                    <span className="hakoniwa-roster__meta">{preset.job}</span>
                    <span className="hakoniwa-roster__desc">
                      {preset.personality}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>

          <h3>{t("hakoniwa.hub.charactersHeading")}</h3>
          <p className="hakoniwa-note">{t("hakoniwa.hub.charactersNote")}</p>
          {characters.length > 0 && (
            <ul className="hakoniwa-chips">
              {characters.map((item) => (
                <li key={item.character_preset_id} className="hakoniwa-chip">
                  {item.portrait_url && (
                    <HakoniwaPortrait
                      src={mediaUrl(item.portrait_url)}
                      alt=""
                      className="hakoniwa-chip__face"
                    />
                  )}
                  <span>{item.name}</span>
                  <span className="hakoniwa-chip__meta">
                    {t(`hakoniwa.gender.${item.gender}`)}
                  </span>
                  <button
                    type="button"
                    className="hakoniwa-chip__remove"
                    onClick={() =>
                      setCharacters((current) =>
                        current.filter(
                          (entry) =>
                            entry.character_preset_id !==
                            item.character_preset_id,
                        ),
                      )
                    }
                  >
                    {t("hakoniwa.hub.removeCharacter")}
                  </button>
                </li>
              ))}
            </ul>
          )}
          <HakoniwaCharacterAdder
            excludeIds={characters.map((item) => item.character_preset_id)}
            onAdd={(picked) => setCharacters((current) => [...current, picked])}
            disabled={count >= MAX_RESIDENTS}
          />

          <div className="hakoniwa-create__option">
            <HakoniwaPresencePicker
              value={playerPresence}
              onChange={setPlayerPresence}
              dissonanceEnabled={dissonanceEnabled}
            />
          </div>

          <div className="hakoniwa-create__option">
            <label className="hakoniwa-toggle" htmlFor={dissonanceId}>
              <span>{t("hakoniwa.hub.dissonanceLabel")}</span>
              <input
                id={dissonanceId}
                type="checkbox"
                className="hakoniwa-toggle__input"
                checked={dissonanceEnabled}
                onChange={(event) => setDissonanceEnabled(event.target.checked)}
              />
              <span className="hakoniwa-toggle__switch" aria-hidden />
            </label>
            <p className="hakoniwa-note">{t("hakoniwa.hub.dissonanceNote")}</p>
          </div>

          {/* 高度な設定: おまかせの住民と実験テーマ。開閉はブラウザに覚え、閉じていても選んだ内容は見出しに出す */}
          <section className="hakoniwa-advanced">
            <button
              type="button"
              className="hakoniwa-advanced__header"
              aria-expanded={advancedOpen}
              aria-controls={advancedId}
              onClick={toggleAdvanced}
            >
              <span className="hakoniwa-advanced__chevron" aria-hidden>
                {advancedOpen ? "▾" : "▸"}
              </span>
              <span className="hakoniwa-advanced__title">
                {t("hakoniwa.hub.advancedHeading")}
              </span>
              {!advancedOpen && advancedSummary && (
                <span className="hakoniwa-advanced__summary">
                  {advancedSummary}
                </span>
              )}
            </button>
            {/* 閉じても中身は残す(組んだ住民・選んだテーマ・人数の選択を失わない) */}
            <div
              id={advancedId}
              className="hakoniwa-advanced__body"
              hidden={!advancedOpen}
            >
              <h3>{t("hakoniwa.random.heading")}</h3>
              <p className="hakoniwa-note">{t("hakoniwa.random.lead")}</p>
              <HakoniwaRandomRoster
                residents={randomResidents}
                onChange={setRandomResidents}
                excludeNames={takenNames}
                available={MAX_RESIDENTS - fixedCount}
              />

              <div className="hakoniwa-create__option">
                <HakoniwaThemePicker value={theme} onChange={setTheme} />
              </div>
            </div>
          </section>

          <div className="hakoniwa-create">
            <span
              className={`hakoniwa-create__count${
                count < MIN_RESIDENTS || count > MAX_RESIDENTS
                  ? " is-invalid"
                  : ""
              }`}
            >
              {t("hakoniwa.hub.rosterCount", { count })}
            </span>
            <button
              type="button"
              className="hakoniwa-button hakoniwa-button--primary"
              onClick={() => void handleCreate()}
              disabled={!canCreate}
            >
              {busy === "create" ? (
                <>
                  <span className="hakoniwa-spinner" aria-hidden />
                  {t("hakoniwa.hub.creating")}
                </>
              ) : (
                t("hakoniwa.hub.create")
              )}
            </button>
          </div>
        </section>

        {/* つくった世界(新しい世界をつくる、の下)。世界が増えても探せるよう絞り込める */}
        <section className="hakoniwa-card">
          <div className="hakoniwa-worlds-header">
            <h2>{t("hakoniwa.hub.worldsHeading")}</h2>
            <span className="hakoniwa-worlds-header__count">
              {t("hakoniwa.hub.worldsCount", { count: worlds.length })}
            </span>
          </div>
          {worlds.length > 0 && (
            <div className="hakoniwa-filters">
              <div
                className="hakoniwa-filters__row"
                role="group"
                aria-label={t("hakoniwa.hub.filterPresence")}
              >
                <span className="hakoniwa-filters__label">
                  {t("hakoniwa.hub.filterPresence")}
                </span>
                {PRESENCE_FILTERS.map((value) => (
                  <button
                    type="button"
                    key={value}
                    className={`hakoniwa-filters__chip${
                      worldFilter.presence === value ? " is-active" : ""
                    }`}
                    aria-pressed={worldFilter.presence === value}
                    // 0件でも選択中なら押せるままにし、抜け出せない状態を作らない
                    disabled={
                      facets.presence[value] === 0 &&
                      worldFilter.presence !== value
                    }
                    onClick={() =>
                      setWorldFilter((current) => ({
                        ...current,
                        presence: value,
                      }))
                    }
                  >
                    {value === "all"
                      ? t("hakoniwa.hub.filterAll")
                      : t(`hakoniwa.presence.options.${value}`)}
                    <span className="hakoniwa-filters__count">
                      {facets.presence[value]}
                    </span>
                  </button>
                ))}
              </div>
              <div
                className="hakoniwa-filters__row"
                role="group"
                aria-label={t("hakoniwa.hub.filterResident")}
              >
                <span className="hakoniwa-filters__label">
                  {t("hakoniwa.hub.filterResident")}
                </span>
                <button
                  type="button"
                  className={`hakoniwa-filters__chip${
                    worldFilter.resident === null ? " is-active" : ""
                  }`}
                  aria-pressed={worldFilter.resident === null}
                  onClick={() =>
                    setWorldFilter((current) => ({
                      ...current,
                      resident: null,
                    }))
                  }
                >
                  {t("hakoniwa.hub.filterAll")}
                </button>
                {facets.residents.map((item) => (
                  <button
                    type="button"
                    key={item.name}
                    className={`hakoniwa-filters__chip${
                      worldFilter.resident === item.name ? " is-active" : ""
                    }`}
                    aria-pressed={worldFilter.resident === item.name}
                    onClick={() =>
                      setWorldFilter((current) => ({
                        ...current,
                        resident:
                          current.resident === item.name ? null : item.name,
                      }))
                    }
                  >
                    {item.name}
                    <span className="hakoniwa-filters__count">
                      {item.count}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}
          {worlds.length === 0 ? (
            busy !== "load" && (
              <p className="hakoniwa-note">{t("hakoniwa.hub.empty")}</p>
            )
          ) : shownWorlds.length === 0 ? (
            <p className="hakoniwa-note">
              {t("hakoniwa.hub.noWorldsForFilter")}
            </p>
          ) : (
            <ul className="hakoniwa-worlds">
              {shownWorlds.map((world) => (
                <li key={world.id} className="hakoniwa-worlds__item">
                  <div className="hakoniwa-worlds__faces" aria-hidden>
                    {world.residents.map((resident) =>
                      resident.avatar_url ? (
                        <HakoniwaPortrait
                          key={resident.id}
                          src={hakoniwaMediaUrl(resident.avatar_url)}
                          alt=""
                          className="hakoniwa-worlds__face"
                        />
                      ) : (
                        <span
                          key={resident.id}
                          className="hakoniwa-worlds__face hakoniwa-worlds__face--empty"
                        >
                          {Array.from(resident.name)[0] ?? "?"}
                        </span>
                      ),
                    )}
                  </div>
                  <div className="hakoniwa-worlds__text">
                    <strong>{world.name}</strong>
                    <span>
                      {t("hakoniwa.hub.dayAndResidents", {
                        day: world.day,
                        count: world.resident_count,
                        presence: t(
                          `hakoniwa.presence.options.${worldPresence(world)}`,
                        ),
                      })}
                    </span>
                  </div>
                  <div className="hakoniwa-worlds__actions">
                    <button
                      type="button"
                      className="hakoniwa-button hakoniwa-button--primary"
                      onClick={() => navigate(getHakoniwaWorldPath(world.id))}
                    >
                      {t("hakoniwa.hub.open")}
                    </button>
                    <button
                      type="button"
                      className="hakoniwa-button hakoniwa-button--ghost"
                      onClick={() => setDeleteTarget(world)}
                    >
                      {t("hakoniwa.hub.delete")}
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <ConfirmDialog
        open={deleteTarget !== null}
        title={t("hakoniwa.hub.deleteTitle")}
        confirmLabel={t("hakoniwa.hub.deleteConfirm")}
        cancelLabel={t("hakoniwa.residentForm.cancel")}
        busy={busy === "delete"}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (!deleteTarget) return;
          void deleteWorld(deleteTarget.id).then(() => setDeleteTarget(null));
        }}
      >
        <p>
          {t("hakoniwa.hub.deleteBody", { name: deleteTarget?.name ?? "" })}
        </p>
      </ConfirmDialog>
    </MainLayout>
  );
}
