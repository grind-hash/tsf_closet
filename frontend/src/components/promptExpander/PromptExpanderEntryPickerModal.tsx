/**
 * PromptExpanderEntryPickerModal - Prompt Expander エントリの選択モーダル
 *
 * EntryGrid をモーダルで包んだもの。他画面（WelcomeScreen / Adventure）からの再利用を想定。
 */

import { useTranslation } from "react-i18next";
import type { PromptExpanderEntry } from "../../apis/promptExpander";
import PromptExpanderEntryGrid from "./PromptExpanderEntryGrid";
import PromptExpanderModal from "./PromptExpanderModal";
import "./PromptExpanderShared.css";

interface PromptExpanderEntryPickerModalProps {
  open: boolean;
  title: string;
  selectedEntryId?: string | null;
  onSelect: (entry: PromptExpanderEntry) => void;
  onClose: () => void;
}

export default function PromptExpanderEntryPickerModal({
  open,
  title,
  selectedEntryId,
  onSelect,
  onClose,
}: PromptExpanderEntryPickerModalProps) {
  const { t } = useTranslation();
  return (
    <PromptExpanderModal
      open={open}
      title={title}
      onClose={onClose}
      closeLabel={t("promptExpander.picker.close")}
      size="lg"
    >
      <PromptExpanderEntryGrid
        selectedEntryId={selectedEntryId}
        onSelect={onSelect}
      />
    </PromptExpanderModal>
  );
}
