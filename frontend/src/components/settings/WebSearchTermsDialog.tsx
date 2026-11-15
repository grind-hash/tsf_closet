/**
 * Web 検索(Tavily)の利用条件ダイアログ。ON にするときの同意と、読み返しに使う。
 *
 * キャラチャット(セレナ)と AI箱庭で共通。文面は settings.characterChatWebSearchTerms で、
 * AI箱庭では「送信される情報」の節だけを settings.hakoniwaWebSearchTransmission に差し替える
 * (見出しが同じ節を置き換える)。
 */
import { useTranslation } from "react-i18next";
import ConfirmDialog from "../ui/ConfirmDialog";
import "./WebSearchTermsDialog.css";

const TAVILY_AUP_URL = "https://www.tavily.com/acceptable-use-policy";

/** 利用条件の 1 節。段落、箇条書き、箇条書きの後の段落の順に並べる */
interface TermsSection {
  heading: string;
  paragraphs: string[];
  items?: string[];
  after?: string[];
}

/** i18n の settings.characterChatWebSearchTerms の形 */
export interface WebSearchTerms {
  title: string;
  /** 同意のたびに読む要約。詳細は折りたたみの中に置く */
  summary: string[];
  /** 詳細な注意事項の折りたたみの見出し */
  details: string;
  intro: string[];
  sections: TermsSection[];
  consent: string;
  link: string;
  accept: string;
  cancel: string;
  read: string;
  close: string;
}

/** 同意の確認(ON にするとき)か、読み返しか */
export type WebSearchTermsMode = "consent" | "read";

/** どの機能の Web 検索か(送信される情報の説明が変わる) */
export type WebSearchTermsVariant = "characterChat" | "hakoniwa";

/** 利用条件の文面。AI箱庭では送信される情報の節を差し替える */
export function useWebSearchTerms(
  variant: WebSearchTermsVariant,
): WebSearchTerms {
  const { t } = useTranslation();
  const terms = t("settings.characterChatWebSearchTerms", {
    returnObjects: true,
  }) as unknown as WebSearchTerms;
  if (variant === "characterChat") return terms;
  const transmission = t("settings.hakoniwaWebSearchTransmission", {
    returnObjects: true,
  }) as unknown as TermsSection;
  return {
    ...terms,
    sections: terms.sections.map((section) =>
      section.heading === transmission.heading ? transmission : section,
    ),
  };
}

/**
 * 利用条件の本文。要約・規約へのリンク・折りたたんだ詳細な注意事項の順に並べ、
 * 同意の一文は同意を求めるときだけ最後(ボタンの直前)に出す。
 */
function WebSearchTermsBody({
  terms,
  showConsent,
}: {
  terms: WebSearchTerms;
  showConsent: boolean;
}) {
  return (
    <>
      <div className="settings-screen__terms-summary">
        {terms.summary.map((text) => (
          <p key={text}>{text}</p>
        ))}
      </div>
      <p>
        <a href={TAVILY_AUP_URL} target="_blank" rel="noopener noreferrer">
          {terms.link}
        </a>
      </p>
      <details className="settings-screen__terms-details">
        <summary>{terms.details}</summary>
        {terms.intro.map((text) => (
          <p key={text}>{text}</p>
        ))}
        {terms.sections.map((section) => (
          <section key={section.heading}>
            <h4>{section.heading}</h4>
            {section.paragraphs.map((text) => (
              <p key={text}>{text}</p>
            ))}
            {section.items && (
              <ul className="settings-screen__terms-list">
                {section.items.map((text) => (
                  <li key={text}>{text}</li>
                ))}
              </ul>
            )}
            {section.after?.map((text) => (
              <p key={text}>{text}</p>
            ))}
          </section>
        ))}
      </details>
      {showConsent && (
        <p>
          <strong>{terms.consent}</strong>
        </p>
      )}
    </>
  );
}

interface WebSearchTermsDialogProps {
  /** null なら閉じている */
  mode: WebSearchTermsMode | null;
  variant: WebSearchTermsVariant;
  /** 同意して有効にする(mode が consent のときだけ呼ぶ) */
  onAccept: () => void;
  onClose: () => void;
  testId?: string;
}

export default function WebSearchTermsDialog({
  mode,
  variant,
  onAccept,
  onClose,
  testId,
}: WebSearchTermsDialogProps) {
  const terms = useWebSearchTerms(variant);
  const reading = mode === "read";
  return (
    <ConfirmDialog
      open={mode !== null}
      title={terms.title}
      confirmLabel={reading ? terms.close : terms.accept}
      cancelLabel={reading ? undefined : terms.cancel}
      onConfirm={() => {
        if (mode === "consent") onAccept();
        onClose();
      }}
      onCancel={onClose}
      dismissible={reading}
      className="settings-screen__terms-dialog"
      testId={testId}
    >
      <WebSearchTermsBody terms={terms} showConsent={!reading} />
    </ConfirmDialog>
  );
}
