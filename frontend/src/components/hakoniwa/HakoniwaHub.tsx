import { useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  type HakoniwaRandomResident,
  type HakoniwaTheme,
  type HakoniwaWorldSummary,
  hakoniwaMediaUrl,
} from "../../apis/hakoniwa";
import { useHakoniwa } from "../../contexts/HakoniwaContext";
import { getHakoniwaWorldPath } from "../../routes";
import { mediaUrl } from "../../utils/adventureFormat";
import MainLayout from "../layout/MainLayout";
import ConfirmDialog from "../ui/ConfirmDialog";
import HakoniwaCharacterAdder, {
  type HakoniwaPickedCharacter,
} from "./HakoniwaCharacterAdder";
import HakoniwaErrorBanner from "./HakoniwaErrorBanner";
import HakoniwaPortrait from "./HakoniwaPortrait";
import HakoniwaRandomRoster from "./HakoniwaRandomRoster";
import HakoniwaThemePicker, { normalizeTheme } from "./HakoniwaThemePicker";

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
  const nameId = useId();
  const dissonanceId = useId();
  const [dissonanceEnabled, setDissonanceEnabled] = useState(true);
  const [name, setName] = useState("");
  const [presetIds, setPresetIds] = useState<string[] | null>(null);
  const [characters, setCharacters] = useState<HakoniwaPickedCharacter[]>([]);
  const [randomResidents, setRandomResidents] = useState<
    HakoniwaRandomResident[]
  >([]);
  const [theme, setTheme] = useState<HakoniwaTheme | null>(null);
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
      customResidents: randomResidents,
      theme: normalizeTheme(theme),
    });
    if (created) {
      setName("");
      setCharacters([]);
      setRandomResidents([]);
      setTheme(null);
      navigate(getHakoniwaWorldPath(created.id));
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

        {worlds.length > 0 && (
          <section className="hakoniwa-card">
            <h2>{t("hakoniwa.hub.worldsHeading")}</h2>
            <ul className="hakoniwa-worlds">
              {worlds.map((world) => (
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
          </section>
        )}

        <section className="hakoniwa-card">
          <h2>{t("hakoniwa.hub.createHeading")}</h2>
          {worlds.length === 0 && busy !== "load" && (
            <p className="hakoniwa-note">{t("hakoniwa.hub.empty")}</p>
          )}
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
