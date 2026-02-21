/**
 * WelcomeScreen - ウェルカム画面とキャラクター選択UI
 * 007-chat-interactive-ux
 *
 * チャットエリア内に表示されるウェルカム画面。
 * キャラクター選択を行い、ゲームセッションを開始する。
 */

import { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import type { Character } from "../../types";
import { useGame } from "../../contexts/GameContext";
import { useSettings } from "../../contexts/SettingsContext";
import { API_BASE } from "../../utils/api";
import {
  getImageDimensions,
  isWithinNovelAIFreeSize,
} from "../../utils/imageSizeValidator";
import CustomImageSizeWarningModal from "../CustomImageSizeWarningModal";
import "./WelcomeScreen.css";

interface WelcomeScreenProps {
  onSessionStart?: () => void;
}

interface CustomCharacter {
  id: string;
  thumbnail: string;
  name: string;
  description: string;
  pronoun: string;
  personality: string;
  gender: string;
}

export default function WelcomeScreen({ onSessionStart }: WelcomeScreenProps) {
  const { t } = useTranslation();
  const {
    startSession,
    setLoading,
    setError,
    state: gameState,
    setSelfMode,
  } = useGame();

  // キャラクター一覧
  const [characters, setCharacters] = useState<Character[]>([]);
  const [isLoadingCharacters, setIsLoadingCharacters] = useState(true);

  // 選択状態
  const [selectedCharacterId, setSelectedCharacterId] = useState<string | null>(
    null,
  );
  const [isStarting, setIsStarting] = useState(false);

  // カスタム画像
  const [customImage, setCustomImage] = useState<string | null>(null);
  const [selectedCustomCharacterId, setSelectedCustomCharacterId] = useState<
    string | null
  >(null);
  const [customCharacters, setCustomCharacters] = useState<CustomCharacter[]>(
    [],
  );
  const [showCustomCharacters, setShowCustomCharacters] = useState(false);
  const [customName, setCustomName] = useState("");
  const [customDescription, setCustomDescription] = useState("");
  const [customPronoun, setCustomPronoun] = useState(
    t("chat.welcome.defaultPronoun"),
  );
  const [customPersonality, setCustomPersonality] = useState("");
  const [customGender, setCustomGender] = useState("other");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // 009: カスタム画像サイズ警告用state
  const [showSizeWarning, setShowSizeWarning] = useState(false);
  const [pendingImage, setPendingImage] = useState<string | null>(null);
  const [pendingImageDimensions, setPendingImageDimensions] = useState<{
    width: number;
    height: number;
  } | null>(null);

  // SettingsContextからimageProviderを取得
  const { state: settingsState } = useSettings();

  // キャラクター一覧を取得
  useEffect(() => {
    const fetchCharacters = async () => {
      try {
        setIsLoadingCharacters(true);
        const response = await fetch(`${API_BASE}/game/characters`);
        if (!response.ok)
          throw new Error(t("chat.welcome.fetchCharactersError"));
        const data = await response.json();
        setCharacters(data.characters);
        const customResponse = await fetch(
          `${API_BASE}/game/custom-characters`,
        );
        if (customResponse.ok) {
          const customData = await customResponse.json();
          setCustomCharacters(customData.characters || []);
        }
      } catch (err) {
        console.error("Failed to fetch characters:", err);
        setError(
          err instanceof Error ? err.message : t("chat.welcome.genericError"),
        );
      } finally {
        setIsLoadingCharacters(false);
      }
    };
    fetchCharacters();
  }, [setError, t]);

  // ファイル選択ハンドラ
  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      // 画像サイズを取得
      const dimensions = await getImageDimensions(file);

      // base64に変換
      const reader = new FileReader();
      reader.onload = (event) => {
        const base64 = event.target?.result as string;

        // NovelAIモードかつ規定サイズ外の場合は警告を表示
        if (
          settingsState.imageProvider === "novelai" &&
          !isWithinNovelAIFreeSize(dimensions.width, dimensions.height)
        ) {
          setPendingImage(base64);
          setPendingImageDimensions(dimensions);
          setShowSizeWarning(true);
        } else {
          // 警告不要の場合は直接設定
          setCustomImage(base64);
          setSelectedCharacterId(null);
          setSelectedCustomCharacterId(null);
        }
      };
      reader.readAsDataURL(file);
    } catch (err) {
      console.error("Failed to read image:", err);
      setError(
        err instanceof Error ? err.message : t("chat.welcome.imageLoadError"),
      );
    }
  };

  // 009: サイズ警告で続行を選択
  const handleSizeWarningContinue = () => {
    if (pendingImage) {
      setCustomImage(pendingImage);
      setSelectedCharacterId(null);
      setSelectedCustomCharacterId(null);
    }
    setShowSizeWarning(false);
    setPendingImage(null);
    setPendingImageDimensions(null);
  };

  // 009: サイズ警告でキャンセルを選択
  const handleSizeWarningCancel = () => {
    setShowSizeWarning(false);
    setPendingImage(null);
    setPendingImageDimensions(null);
    // ファイル入力をリセット
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  // キャラクター選択ハンドラ
  const handleCharacterSelect = (characterId: string) => {
    setSelectedCharacterId(characterId);
    setCustomImage(null); // キャラクター選択時はカスタム画像をクリア
    setSelectedCustomCharacterId(null);
  };

  const handleCustomCharacterSelect = (character: CustomCharacter) => {
    setCustomImage(`data:image/png;base64,${character.thumbnail}`);
    setSelectedCustomCharacterId(character.id);
    setSelectedCharacterId(null);
    setCustomName(character.name);
    setCustomDescription(character.description);
    setCustomPronoun(character.pronoun || t("chat.welcome.defaultPronoun"));
    setCustomPersonality(character.personality);
    setCustomGender(character.gender || "other");
  };

  // ゲーム開始ハンドラ
  const handleStartGame = async () => {
    if (!selectedCharacterId && !customImage) return;

    try {
      setIsStarting(true);
      setLoading(true);

      let sessionData: { session_id: string; image_path: string } | null = null;

      if (customImage) {
        // カスタム画像でセッション開始
        const base64Data = customImage.split(",")[1] || customImage;
        const response = await fetch(`${API_BASE}/game/start-custom`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            image: selectedCustomCharacterId ? null : base64Data,
            custom_character_id: selectedCustomCharacterId,
            difficulty: "normal",
            nsfw_mode: false,
            self_mode: gameState.selfMode,
            name: customName || t("chat.welcome.customCharacterDefaultName"),
            description: customDescription,
            pronoun: customPronoun || t("chat.welcome.defaultPronoun"),
            personality: customPersonality,
            gender: customGender || "other",
          }),
        });
        if (!response.ok) throw new Error(t("chat.welcome.startSessionError"));
        sessionData = await response.json();
      } else if (selectedCharacterId) {
        // 選択したキャラクターでセッション開始
        const response = await fetch(`${API_BASE}/game/start`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            character_id: selectedCharacterId,
            difficulty: "normal",
            nsfw_mode: false,
            self_mode: gameState.selfMode,
          }),
        });
        if (!response.ok) throw new Error(t("chat.welcome.startSessionError"));
        sessionData = await response.json();
      }

      if (sessionData) {
        const selectedCharacter = characters.find(
          (c) => c.id === selectedCharacterId,
        ) || {
          id: "custom",
          name: customName || t("chat.welcome.customCharacterDefaultName"),
          thumbnail: customImage || "",
          description: customDescription,
        };

        startSession(
          sessionData.session_id,
          selectedCharacter,
          sessionData.image_path,
        );

        onSessionStart?.();
      }
    } catch (err) {
      console.error("Failed to start session:", err);
      setError(
        err instanceof Error
          ? err.message
          : t("chat.welcome.startSessionFailed"),
      );
    } finally {
      setIsStarting(false);
      setLoading(false);
    }
  };

  const canStart = selectedCharacterId || customImage;

  return (
    <div className="welcome-screen">
      {/* ウェルカムメッセージ */}
      <div className="welcome-screen__header">
        <h2 className="welcome-screen__title">{t("chat.welcome.title")}</h2>
        <p className="welcome-screen__description">
          {t("chat.welcome.descriptionLine1")}
          <br />
          {t("chat.welcome.descriptionLine2")}
        </p>
      </div>

      {/* キャラクター選択 */}
      <div className="welcome-screen__characters">
        <h3 className="welcome-screen__section-title">
          {t("chat.welcome.selectCharacter")}
        </h3>

        {isLoadingCharacters ? (
          <div className="welcome-screen__loading">
            {t("chat.welcome.loading")}
          </div>
        ) : (
          <div className="welcome-screen__character-grid">
            {characters.map((character) => (
              <button
                key={character.id}
                type="button"
                className={`welcome-screen__character-card ${
                  selectedCharacterId === character.id ? "is-selected" : ""
                }`}
                onClick={() => handleCharacterSelect(character.id)}
              >
                <img
                  src={
                    character.thumbnail.startsWith("data:")
                      ? character.thumbnail
                      : `data:image/png;base64,${character.thumbnail}`
                  }
                  alt={character.name}
                  className="welcome-screen__character-image"
                />
                <span className="welcome-screen__character-name">
                  {character.name}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* カスタム画像 */}
      <div className="welcome-screen__custom">
        <h3 className="welcome-screen__section-title">
          {t("chat.welcome.customImageSection")}
        </h3>
        <div className="welcome-screen__custom-upload">
          <input
            type="file"
            ref={fileInputRef}
            accept="image/*"
            onChange={handleFileChange}
            className="welcome-screen__file-input"
          />
          <button
            type="button"
            className="welcome-screen__upload-btn"
            onClick={() => fileInputRef.current?.click()}
          >
            {t("chat.welcome.selectImage")}
          </button>
          <button
            type="button"
            className="welcome-screen__upload-btn"
            onClick={() => setShowCustomCharacters((prev) => !prev)}
          >
            {t("chat.welcome.createdCharacters")}
          </button>
          {customImage && (
            <div className="welcome-screen__custom-preview">
              <img src={customImage} alt={t("chat.welcome.customImageAlt")} />
              <button
                type="button"
                className="welcome-screen__remove-btn"
                onClick={() => {
                  setCustomImage(null);
                  setSelectedCustomCharacterId(null);
                }}
              >
                ✕
              </button>
            </div>
          )}
        </div>
        {showCustomCharacters && customCharacters.length > 0 && (
          <div className="welcome-screen__saved-grid">
            {customCharacters.map((character) => (
              <button
                key={character.id}
                type="button"
                className={`welcome-screen__saved-item ${
                  selectedCustomCharacterId === character.id
                    ? "is-selected"
                    : ""
                }`}
                onClick={() => handleCustomCharacterSelect(character)}
              >
                <img
                  src={`data:image/png;base64,${character.thumbnail}`}
                  alt={character.name}
                />
                <span>{character.name}</span>
              </button>
            ))}
          </div>
        )}
        {customImage && (
          <div className="welcome-screen__custom-fields">
            <input
              type="text"
              value={customName}
              onChange={(e) => setCustomName(e.target.value)}
              placeholder={t("chat.welcome.namePlaceholder")}
            />
            <input
              type="text"
              value={customDescription}
              onChange={(e) => setCustomDescription(e.target.value)}
              placeholder={t("chat.welcome.descriptionPlaceholder")}
            />
            <input
              type="text"
              value={customPronoun}
              onChange={(e) => setCustomPronoun(e.target.value)}
              placeholder={t("chat.welcome.pronounPlaceholder")}
            />
            <input
              type="text"
              value={customPersonality}
              onChange={(e) => setCustomPersonality(e.target.value)}
              placeholder={t("chat.welcome.personalityPlaceholder")}
            />
            <select
              value={customGender}
              onChange={(e) => setCustomGender(e.target.value)}
              aria-label={t("chat.welcome.genderAria")}
            >
              <option value="man">{t("chat.welcome.genderMan")}</option>
              <option value="woman">{t("chat.welcome.genderWoman")}</option>
              <option value="other">{t("chat.welcome.genderOther")}</option>
            </select>
          </div>
        )}
      </div>

      {/* 自分自身モード (US5) */}
      <div className="welcome-screen__self-mode">
        <label className="welcome-screen__self-mode-label">
          <input
            type="checkbox"
            checked={gameState.selfMode}
            onChange={(e) => setSelfMode(e.target.checked)}
            className="welcome-screen__self-mode-checkbox"
          />
          <span>{t("chat.welcome.selfMode")}</span>
        </label>
        <p className="welcome-screen__self-mode-desc">
          {t("chat.welcome.selfModeDescription")}
        </p>
      </div>

      {/* 開始ボタン */}
      <div className="welcome-screen__actions">
        <button
          type="button"
          className="welcome-screen__start-btn"
          onClick={handleStartGame}
          disabled={!canStart || isStarting}
        >
          {isStarting
            ? t("chat.welcome.starting")
            : t("chat.welcome.startGame")}
        </button>
      </div>

      {/* 009: カスタム画像サイズ警告モーダル */}
      {showSizeWarning && pendingImageDimensions && (
        <CustomImageSizeWarningModal
          width={pendingImageDimensions.width}
          height={pendingImageDimensions.height}
          onContinue={handleSizeWarningContinue}
          onCancel={handleSizeWarningCancel}
        />
      )}
    </div>
  );
}
