import { useTranslation } from "react-i18next";
import { useCharacterChat } from "../../contexts/CharacterChatContext";

/**
 * 案内役の部屋で入力欄のすぐ上に置く「おすすめのプレイを聞く」。
 * 定型の依頼文を提案の要求付きで送る。入力中の文字には触れない。
 */
export default function CharacterChatProposalChip() {
  const { t } = useTranslation();
  const { sending, requestPlayProposal } = useCharacterChat();
  return (
    <button
      type="button"
      className="character-chat__proposal-chip"
      disabled={sending}
      title={t("characterChat.proposal.chipHint")}
      onClick={() => void requestPlayProposal()}
    >
      {t("characterChat.proposal.chip")}
    </button>
  );
}
