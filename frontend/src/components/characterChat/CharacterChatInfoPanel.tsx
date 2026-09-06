import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import type { CharacterChatThread } from "../../apis/characterChat";
import { ROUTES } from "../../routes";

interface CharacterChatInfoPanelProps {
  thread: CharacterChatThread;
  memoryText: string | null;
}

const TIMELINE_TYPES = [
  "dress_up",
  "reality_alter",
  "action",
  "conversation",
  "image_only",
] as const;
type TimelineType = (typeof TIMELINE_TYPES)[number];

function isTimelineType(value: string): value is TimelineType {
  return (TIMELINE_TYPES as readonly string[]).includes(value);
}

/**
 * 右パネル。キャラクターがいま参照している記憶(ユーザーメモリ・会話の要約)と、
 * セッション由来キャラならそのセッションの概要、そして姿の情報を並べる。
 */
export default function CharacterChatInfoPanel({
  thread,
  memoryText,
}: CharacterChatInfoPanelProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const persona = thread.persona ?? {};
  const isSession = thread.kind === "session";
  const isAdventure = thread.kind === "adventure";
  const adventure = isAdventure ? (thread.adventure ?? null) : null;
  const standing = thread.appearance.portrait_kind === "standing";
  const source = thread.appearance.source;
  const sourceLabel = standing
    ? t("characterChat.room.sourceStanding")
    : source.type === "prompt_expander"
      ? t("characterChat.room.sourcePromptExpander")
      : source.type === "session"
        ? t("characterChat.room.sourceSession")
        : t("characterChat.room.sourceBase");
  const tags = [
    thread.appearance.identity_tags,
    thread.appearance.clothing_tags,
  ]
    .filter(Boolean)
    .join(", ");
  const formatDate = (value: string | null | undefined) => {
    if (!value) return "";
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? value
      : date.toLocaleDateString(i18n.language);
  };

  // 経緯は同じ文が並び得るため、React key は並び順込みで組み立てる
  const timelineEntries = (persona.timeline ?? []).map((item, index) => ({
    ...item,
    key: `${index}:${item.type}:${item.text}`,
  }));

  return (
    <div className="character-chat-panel">
      <h2 className="character-chat-panel__title">
        {t("characterChat.panel.title")}
      </h2>

      <section className="character-chat-panel__section">
        <h3>{t("characterChat.panel.memory")}</h3>
        <p className="character-chat-panel__hint">
          {t("characterChat.panel.memoryHint")}
        </p>
        {memoryText?.trim() ? (
          <p className="character-chat-panel__text">{memoryText}</p>
        ) : (
          <>
            <p className="character-chat-panel__empty">
              {t("characterChat.panel.memoryEmpty")}
            </p>
            <button
              type="button"
              className="character-chat__secondary"
              onClick={() => navigate(ROUTES.SETTINGS)}
            >
              {t("characterChat.panel.openSettings")}
            </button>
          </>
        )}
      </section>

      <section className="character-chat-panel__section">
        <h3>{t("characterChat.panel.summary")}</h3>
        <p className="character-chat-panel__hint">
          {t("characterChat.panel.summaryHint")}
        </p>
        {thread.summary_text ? (
          <p className="character-chat-panel__text">{thread.summary_text}</p>
        ) : (
          <p className="character-chat-panel__empty">
            {t("characterChat.room.summaryEmpty")}
          </p>
        )}
      </section>

      {isAdventure && (
        <section className="character-chat-panel__section">
          <h3>{t("characterChat.panel.adventure")}</h3>
          <p className="character-chat-panel__hint">
            {t("characterChat.panel.adventureHint")}
          </p>
          {adventure && !adventure.available && (
            <p className="character-chat-panel__empty">
              {t("characterChat.panel.runMissing")}
            </p>
          )}
          {(adventure?.title || persona.summary_title) && (
            <p className="character-chat-panel__label">
              {adventure?.title || persona.summary_title}
            </p>
          )}
          <dl className="character-chat-panel__facts">
            {(adventure?.affection ?? persona.affection) != null && (
              <div>
                <dd>
                  {t("characterChat.panel.affection", {
                    value: adventure?.affection ?? persona.affection,
                    stage: adventure?.stage ?? persona.stage_label ?? "",
                  })}
                </dd>
              </div>
            )}
            {(adventure?.day ?? persona.day) != null && (
              <div>
                <dd>
                  {t("characterChat.panel.day", {
                    day: adventure?.day ?? persona.day,
                    slot: adventure?.slot ?? persona.slot ?? "",
                  })}
                </dd>
              </div>
            )}
            {(adventure?.dating ?? persona.dating) && (
              <div>
                <dd>{t("characterChat.panel.dating")}</dd>
              </div>
            )}
          </dl>
          {persona.summary_text && (
            <p className="character-chat-panel__text">{persona.summary_text}</p>
          )}
          {persona.speech_style && (
            <>
              <h4>{t("characterChat.panel.speechStyle")}</h4>
              <p className="character-chat-panel__text">
                {persona.speech_style}
              </p>
            </>
          )}
          {persona.given_gifts && persona.given_gifts.length > 0 && (
            <>
              <h4>{t("characterChat.panel.gifts")}</h4>
              <ul className="character-chat-panel__list">
                {persona.given_gifts.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {persona.completed_milestones &&
            persona.completed_milestones.length > 0 && (
              <>
                <h4>{t("characterChat.panel.milestones")}</h4>
                <ul className="character-chat-panel__list">
                  {persona.completed_milestones.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </>
            )}
          {persona.attributes && persona.attributes.length > 0 && (
            <>
              <h4>{t("characterChat.panel.attributes")}</h4>
              <ul className="character-chat-panel__list">
                {persona.attributes.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {timelineEntries.length > 0 && (
            <>
              <h4>{t("characterChat.panel.recentScenes")}</h4>
              <ol className="character-chat-panel__timeline">
                {timelineEntries.map((item) => (
                  <li key={item.key}>
                    <span>{item.text}</span>
                  </li>
                ))}
              </ol>
            </>
          )}
        </section>
      )}

      {isSession && (
        <section className="character-chat-panel__section">
          <h3>{t("characterChat.panel.session")}</h3>
          <p className="character-chat-panel__hint">
            {t("characterChat.panel.sessionHint")}
          </p>
          <dl className="character-chat-panel__facts">
            {persona.session_updated_at && (
              <div>
                <dd>
                  {t("characterChat.panel.updatedAt", {
                    date: formatDate(persona.session_updated_at),
                  })}
                </dd>
              </div>
            )}
            {persona.self_mode && (
              <div>
                <dd>{t("characterChat.panel.selfMode")}</dd>
              </div>
            )}
            <div>
              <dd>
                {t("characterChat.panel.transformations", {
                  count: persona.transformation_count ?? 0,
                })}
              </dd>
            </div>
            {persona.stage_label && (
              <div>
                <dt>{t("characterChat.panel.stage")}</dt>
                <dd>
                  {persona.stage_label}
                  {persona.stats && (
                    <span className="character-chat-panel__stats">
                      {t("characterChat.panel.stats", persona.stats)}
                    </span>
                  )}
                </dd>
              </div>
            )}
          </dl>
          {persona.summary_title && (
            <p className="character-chat-panel__label">
              {persona.summary_title}
            </p>
          )}
          {persona.summary_text ? (
            <p className="character-chat-panel__text">{persona.summary_text}</p>
          ) : (
            <p className="character-chat-panel__empty">
              {t("characterChat.panel.sessionSummaryEmpty")}
            </p>
          )}
          {persona.outfit_description && (
            <>
              <h4>{t("characterChat.panel.outfit")}</h4>
              <p className="character-chat-panel__text">
                {persona.outfit_description}
              </p>
            </>
          )}
          {persona.attributes && persona.attributes.length > 0 && (
            <>
              <h4>{t("characterChat.panel.attributes")}</h4>
              <ul className="character-chat-panel__list">
                {persona.attributes.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            </>
          )}
          {timelineEntries.length > 0 && (
            <>
              <h4>{t("characterChat.panel.timeline")}</h4>
              <ol className="character-chat-panel__timeline">
                {timelineEntries.map((item) => (
                  <li key={item.key}>
                    <span className="character-chat__chip">
                      {isTimelineType(item.type)
                        ? t(`characterChat.panel.timelineType.${item.type}`)
                        : item.type}
                    </span>
                    <span>{item.text}</span>
                  </li>
                ))}
              </ol>
            </>
          )}
          {persona.play_memory_context && (
            <details className="character-chat__tags">
              <summary>{t("characterChat.panel.playMemory")}</summary>
              <p>{persona.play_memory_context}</p>
            </details>
          )}
        </section>
      )}

      <section className="character-chat-panel__section">
        <h3>{t("characterChat.panel.appearance")}</h3>
        <div className="character-chat__portrait-source">{sourceLabel}</div>
        {thread.appearance.description && (
          <p className="character-chat-panel__text">
            {thread.appearance.description}
          </p>
        )}
        {tags && (
          <details className="character-chat__tags">
            <summary>{t("characterChat.room.appearanceTags")}</summary>
            <p>{tags}</p>
          </details>
        )}
      </section>
    </div>
  );
}
