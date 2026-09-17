import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type {
  CharacterChatPlayProposal,
  CharacterChatProposalInstructionType,
} from "../../apis/characterChat";
import { useCharacterChat } from "../../contexts/CharacterChatContext";
import { useSettings } from "../../contexts/SettingsContext";
import type { TranslationKey } from "../../i18n";
import { getGameSessionPath } from "../../routes";

/** プレイ画面の指示タイプ選択と同じ表示名 */
const INSTRUCTION_TYPE_LABEL_KEY: Record<
  CharacterChatProposalInstructionType,
  TranslationKey
> = {
  dress_up: "chat.instructionType.dressUp",
  reality_alter: "chat.instructionType.realityAlter",
  action: "chat.instructionType.action",
  conversation: "chat.instructionType.conversation",
};

interface CharacterChatPlayProposalCardProps {
  proposal: CharacterChatPlayProposal;
}

/**
 * 案内役が返答に添えたおすすめの通常プレイ。
 * 開始すると提案のキャラクターでセッションを作り、最初の指示をプレイ画面の入力欄と
 * 指示タイプへ入れてから(送信はしない)プレイ画面へ移る。文言は省略せず全文を出す。
 */
export default function CharacterChatPlayProposalCard({
  proposal,
}: CharacterChatPlayProposalCardProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { startProposedPlay, sending } = useCharacterChat();
  const { selfProfile } = useSettings();
  const [starting, setStarting] = useState(false);
  const [failed, setFailed] = useState(false);
  // 自分自身モードはキャラ設定(セルフプロフィール)が無いと始められない
  const selfProfileMissing = proposal.self_mode && !selfProfile;
  // 返答の処理中(立ち絵・要約の工程を含む)は始めない。途中で画面を離れると料金の表示が届かない
  const blocked = sending || selfProfileMissing;
  const { first_instruction: instruction } = proposal;

  const handleStart = async () => {
    if (starting || blocked) return;
    setStarting(true);
    setFailed(false);
    let sessionId: string;
    try {
      sessionId = await startProposedPlay(proposal);
    } catch (err) {
      console.warn("proposed play start failed", err);
      setFailed(true);
      setStarting(false);
      return;
    }
    // 成功時はこの画面ごと離れるため、starting は戻さない
    navigate(getGameSessionPath(sessionId));
  };

  return (
    <section
      className="character-chat__proposal"
      aria-label={t("characterChat.proposal.label")}
    >
      <span className="character-chat__proposal-label">
        {t("characterChat.proposal.label")}
      </span>
      <h3 className="character-chat__proposal-title">{proposal.title}</h3>
      {proposal.reason && (
        <p className="character-chat__proposal-reason">{proposal.reason}</p>
      )}
      <dl className="character-chat__proposal-rows">
        <dt>{t("characterChat.proposal.character")}</dt>
        <dd>
          <span>{proposal.character.name}</span>
          {proposal.self_mode && (
            <span className="character-chat__badge">
              {t("characterChat.proposal.selfMode")}
            </span>
          )}
        </dd>
        <dt>{t("characterChat.proposal.firstInstruction")}</dt>
        <dd>
          <span className="character-chat__chip">
            {t(INSTRUCTION_TYPE_LABEL_KEY[instruction.instruction_type])}
          </span>
          <span className="character-chat__proposal-instruction">
            {instruction.text}
          </span>
        </dd>
      </dl>
      <p className="character-chat__proposal-note">
        {selfProfileMissing
          ? t("characterChat.proposal.selfProfileMissing")
          : t("characterChat.proposal.startNote")}
      </p>
      {failed && (
        <p className="character-chat__proposal-error" role="alert">
          {t("characterChat.proposal.startFailed")}
        </p>
      )}
      <button
        type="button"
        className={`character-chat__primary character-chat__proposal-start${starting ? " is-starting" : ""}`}
        disabled={starting || blocked}
        aria-busy={starting}
        onClick={() => void handleStart()}
      >
        {starting ? (
          <span className="character-chat__progress" role="status">
            <span />
            {t("characterChat.proposal.starting")}
          </span>
        ) : (
          t("characterChat.proposal.start")
        )}
      </button>
    </section>
  );
}
