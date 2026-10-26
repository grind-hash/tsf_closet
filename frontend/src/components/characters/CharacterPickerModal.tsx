import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { listCharacterPresets } from "../../apis/characters";
import { ROUTES } from "../../routes";
import type { CharacterPreset } from "../../types";
import { mediaUrl } from "../../utils/adventureFormat";
import "./CharactersScreen.css";

interface CharacterPickerModalProps {
  title: string;
  onSelect: (preset: CharacterPreset) => void;
  onClose: () => void;
}

/** 作ったキャラクターを 1 人選ぶモーダル(キャラチャットの一覧と右パネルで使う) */
export default function CharacterPickerModal({
  title,
  onSelect,
  onClose,
}: CharacterPickerModalProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [presets, setPresets] = useState<CharacterPreset[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    listCharacterPresets()
      .then((items) => {
        if (!cancelled) setPresets(items);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return (
    <div
      className="character-picker"
      onMouseDown={(event) => {
        if (event.currentTarget === event.target) onClose();
      }}
    >
      <section
        className="character-picker__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="character-picker-title"
      >
        <header>
          <h2 id="character-picker-title">{title}</h2>
          <button
            type="button"
            className="character-picker__close"
            aria-label={t("characterChat.room.close")}
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="character-picker__body">
          {failed ? (
            <p className="character-chat__empty" role="alert">
              {t("characterChat.hub.characterPickerFailed")}
            </p>
          ) : presets === null ? (
            <div className="character-chat__progress" role="status">
              <span />
              {t("characterChat.hub.characterPickerLoading")}
            </div>
          ) : presets.length === 0 ? (
            <p className="character-chat__empty">
              {t("characterChat.hub.characterPickerEmpty")}
            </p>
          ) : (
            <ul className="character-picker__list">
              {presets.map((preset) => (
                <li key={preset.id}>
                  <button
                    type="button"
                    className="character-picker__item"
                    onClick={() => onSelect(preset)}
                  >
                    <span className="characters__thumb">
                      {preset.thumbnail_url ? (
                        <img src={mediaUrl(preset.thumbnail_url)} alt="" />
                      ) : (
                        <span aria-hidden>👤</span>
                      )}
                    </span>
                    <span className="characters__card-text">
                      <strong>{preset.name}</strong>
                      <span className="characters__card-personality">
                        {preset.profile?.personality ||
                          t("characters.noPersonality")}
                      </span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
        <footer className="character-picker__footer">
          <button
            type="button"
            className="character-chat__secondary"
            onClick={() => navigate(ROUTES.CHARACTERS)}
          >
            {t("characterChat.hub.characterPickerCreate")}
          </button>
        </footer>
      </section>
    </div>
  );
}
