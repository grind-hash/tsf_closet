/**
 * WelcomeScreen - ウェルカム画面とキャラクター選択UI
 * 007-chat-interactive-ux
 *
 * チャットエリア内に表示されるウェルカム画面。
 * キャラクター選択を行い、ゲームセッションを開始する。
 */

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { useGame } from "../../contexts/GameContext";
import { ROUTES } from "../../routes";
import type { Character } from "../../types";
import { API_BASE } from "../../utils/api";
import PlayStartModeOptions, {
  usePlayStartBlocked,
} from "./PlayStartModeOptions";
import "./WelcomeScreen.css";

interface WelcomeScreenProps {
  onSessionStart?: () => void;
}

export default function WelcomeScreen({ onSessionStart }: WelcomeScreenProps) {
  const { t } = useTranslation();
  const {
    startSession,
    setLoading,
    setError,
    state: gameState,
    generateRequest,
  } = useGame();

  // キャラクター一覧
  const [characters, setCharacters] = useState<Character[]>([]);
  const [isLoadingCharacters, setIsLoadingCharacters] = useState(true);

  // 選択状態
  const [selectedCharacterId, setSelectedCharacterId] = useState<string | null>(
    null,
  );
  const [isStarting, setIsStarting] = useState(false);

  // 自分自身モードON + プロフィール未設定の判定
  const selfModeNeedsProfile = usePlayStartBlocked();

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

  const selectedCharacter = characters.find(
    (character) => character.id === selectedCharacterId,
  );

  // ゲーム開始ハンドラ
  const handleStartGame = async () => {
    if (!selectedCharacter) return;

    try {
      setIsStarting(true);
      setLoading(true);

      const response = await fetch(`${API_BASE}/game/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          character_id: selectedCharacter.id,
          difficulty: "normal",
          nsfw_mode: false,
          self_mode: gameState.selfMode,
        }),
      });
      if (!response.ok) throw new Error(t("chat.welcome.startSessionError"));
      const sessionData: { session_id: string; image_path: string } =
        await response.json();

      await startSession(
        sessionData.session_id,
        selectedCharacter,
        sessionData.image_path,
      );
      // 依頼モード: 開始を待たせず、依頼カードのスピナーを出しながら生成する
      if (gameState.requestMode && !gameState.selfMode) {
        void generateRequest(sessionData.session_id, {
          turnLimit: gameState.requestTurnLimit,
        });
      }

      onSessionStart?.();
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
                onClick={() => setSelectedCharacterId(character.id)}
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
        {selectedCharacter && (
          <CharacterProfileSummary character={selectedCharacter} />
        )}
        <p className="welcome-screen__own-characters">
          {t("chat.welcome.ownCharactersHint")}
          <Link to={ROUTES.CHARACTERS}>{t("chat.welcome.openCharacters")}</Link>
        </p>
      </div>

      <PlayStartModeOptions />

      {/* 開始ボタン */}
      <div className="welcome-screen__actions">
        <button
          type="button"
          className="welcome-screen__start-btn"
          onClick={handleStartGame}
          disabled={!selectedCharacter || isStarting || selfModeNeedsProfile}
        >
          {isStarting
            ? t("chat.welcome.starting")
            : t("chat.welcome.startGame")}
        </button>
      </div>
    </div>
  );
}

/**
 * 選んだテンプレートキャラクターの人物像。依頼モードの依頼文と反応は性格と
 * TSF への態度で決まるため、選ぶ前に全文で読めるようにする。空の項目は出さない。
 */
function CharacterProfileSummary({ character }: { character: Character }) {
  const { t } = useTranslation();
  const facts = [
    {
      key: "personality",
      label: t("chat.welcome.profilePersonality"),
      value: character.personality,
    },
    {
      key: "pronoun",
      label: t("chat.welcome.profilePronoun"),
      value: character.pronoun,
    },
    {
      key: "tsf_attitude",
      label: t("chat.welcome.profileTsfAttitude"),
      value: character.tsf_attitude,
    },
  ].filter((fact) => (fact.value ?? "").trim());
  return (
    <section
      className="welcome-screen__profile"
      aria-label={t("chat.welcome.profileTitle", { name: character.name })}
    >
      <h4 className="welcome-screen__profile-name">{character.name}</h4>
      {character.description && (
        <p className="welcome-screen__profile-description">
          {character.description}
        </p>
      )}
      {facts.length > 0 && (
        <dl className="welcome-screen__profile-facts">
          {facts.map((fact) => (
            <div key={fact.key}>
              <dt>{fact.label}</dt>
              <dd>{fact.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}
