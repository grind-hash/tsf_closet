import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useGame } from "../../contexts/GameContext";
import { useSettings } from "../../contexts/SettingsContext";
import "./PlayMemorySettings.css";

export default function PlayMemorySettings() {
  const { t } = useTranslation();
  const { state: settings } = useSettings();
  const { state, updatePlayMemory, regeneratePlayMemory } = useGame();
  const memory = state.playMemory;
  const [draft, setDraft] = useState(memory.userText ?? "");
  const [busy, setBusy] = useState<"save" | "regenerate" | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => setDraft(memory.userText ?? ""), [memory.userText]);

  const run = async (
    kind: "save" | "regenerate",
    action: () => Promise<void>,
  ) => {
    setBusy(kind);
    setError(null);
    try {
      await action();
    } catch (err) {
      setError(
        err instanceof Error ? err.message : t("settings.playMemory.error"),
      );
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="play-memory">
      <label className="play-memory__toggle">
        <span>{t("settings.playMemory.system")}</span>
        <input
          type="checkbox"
          checked={memory.systemEnabled}
          onChange={(event) =>
            void updatePlayMemory({ system_enabled: event.target.checked })
          }
        />
      </label>
      <textarea
        className="right-panel__textarea play-memory__textarea"
        value={memory.systemText ?? ""}
        readOnly
        rows={5}
        placeholder={t("settings.playMemory.systemPlaceholder")}
      />
      {memory.systemUpdatedAt && (
        <small>
          {t("settings.playMemory.updatedAt", {
            value: new Date(memory.systemUpdatedAt).toLocaleString(),
          })}
        </small>
      )}
      <button
        type="button"
        className="right-panel__btn-primary play-memory__button"
        disabled={!state.sessionId || busy !== null}
        onClick={() =>
          void run("regenerate", () => regeneratePlayMemory(settings.language))
        }
      >
        {busy === "regenerate"
          ? t("settings.playMemory.regenerating")
          : t("settings.playMemory.regenerate")}
      </button>

      <label className="play-memory__toggle">
        <span>{t("settings.playMemory.user")}</span>
        <input
          type="checkbox"
          checked={memory.userEnabled}
          onChange={(event) =>
            void updatePlayMemory({ user_enabled: event.target.checked })
          }
        />
      </label>
      <textarea
        className="right-panel__textarea play-memory__textarea"
        value={draft}
        maxLength={4000}
        rows={5}
        onChange={(event) => setDraft(event.target.value)}
        placeholder={t("settings.playMemory.userPlaceholder")}
      />
      <small>{draft.length} / 4000</small>
      <button
        type="button"
        className="right-panel__btn-primary play-memory__button"
        disabled={
          !state.sessionId || busy !== null || draft === (memory.userText ?? "")
        }
        onClick={() =>
          void run("save", () => updatePlayMemory({ user_text: draft }))
        }
      >
        {busy === "save"
          ? t("settings.playMemory.saving")
          : t("settings.playMemory.save")}
      </button>
      {error && <p className="play-memory__error">{error}</p>}
    </div>
  );
}
