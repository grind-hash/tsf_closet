/**
 * キャラクター(CharacterPreset)の設定を編集するフォーム。キャラクター画面と、
 * キャラチャットの右パネルで共用する。
 *
 * テキスト欄は確定時(blur・画面を離れたとき)に保存し、保存のたびに更新後の
 * キャラクターを onSaved で親へ渡す。プロフィールは 1 つの JSON で保存されるため、
 * 直前に保存した値に変更分を重ねて丸ごと送る。
 */

import { type ReactNode, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { type AvatarModel, listAvatarModels } from "../../apis/avatars";
import {
  generateCharacterProfile,
  type UpdateCharacterPresetPayload,
  updateCharacterPreset,
} from "../../apis/characters";
import {
  type AivisSpeaker,
  getAivisSpeakers,
} from "../../apis/speechSynthesis";
import type { CharacterPreset } from "../../types";
import {
  avatarModelLabel,
  sortAvatarModels,
} from "../../utils/avatarModelLabel";
import SavedTextField from "../panel/SavedTextField";
import ProfileFields from "../settings/ProfileFields";
import { type FullCharacterProfile, fullProfile } from "./characterMaker";
import MakerSection from "./MakerSection";
import "./CharactersScreen.css";

interface CharacterSettingsEditorProps {
  preset: CharacterPreset;
  onSaved: (preset: CharacterPreset) => void;
  /** 開閉状態を覚える localStorage のキー(画面ごとに分ける) */
  sectionStorageKey: string;
  /** 「外見と立ち絵」の節の中身。省くと節ごと出さない */
  appearance?: ReactNode;
  /** 「外見と立ち絵」の節を出さないときに、代わりに出す一文 */
  appearanceNote?: ReactNode;
}

export default function CharacterSettingsEditor({
  preset,
  onSaved,
  sectionStorageKey,
  appearance,
  appearanceNote,
}: CharacterSettingsEditorProps) {
  const { t } = useTranslation();
  const [error, setError] = useState<string | null>(null);
  const onSavedRef = useRef(onSaved);
  onSavedRef.current = onSaved;

  // 直前に保存したプロフィール。欄ごとの保存が重なっても他の欄の値を戻さない
  const [profileDraft, setProfileDraft] = useState<FullCharacterProfile>(() =>
    fullProfile(preset),
  );
  const profileRef = useRef(profileDraft);
  const presetIdRef = useRef(preset.id);
  useEffect(() => {
    // 別のキャラクターに切り替わったか、外(自動生成・取り込み)で変わったら取り込む
    const next = fullProfile(preset);
    if (
      presetIdRef.current !== preset.id ||
      JSON.stringify(next) !== JSON.stringify(profileRef.current)
    ) {
      presetIdRef.current = preset.id;
      profileRef.current = next;
      setProfileDraft(next);
    }
  }, [preset]);

  const save = async (payload: UpdateCharacterPresetPayload) => {
    try {
      const updated = await updateCharacterPreset(preset.id, payload);
      setError(null);
      onSavedRef.current(updated);
    } catch (err) {
      console.error("Failed to save character", err);
      setError(t("characters.errors.saveFailed"));
      throw err;
    }
  };

  const commitProfile = async (patch: Partial<FullCharacterProfile>) => {
    const next = { ...profileRef.current, ...patch };
    profileRef.current = next;
    setProfileDraft(next);
    await save({ profile: next });
  };

  const [generating, setGenerating] = useState(false);
  const [generateError, setGenerateError] = useState<string | null>(null);
  const handleGenerateProfile = async () => {
    setGenerating(true);
    setGenerateError(null);
    try {
      const generated = await generateCharacterProfile({
        name: preset.name,
        appearance_natural: preset.appearance_natural,
        appearance_tags: preset.appearance_tags,
        memo: profileRef.current.memo,
      });
      // 下書きは性格まわりだけ。口調・セリフの例・知識・最初のひとことは残す
      const current = profileRef.current;
      await commitProfile({
        personality: generated.personality,
        reaction_style: generated.reaction_style,
        pronoun: generated.pronoun,
        gender: generated.gender,
        interests: generated.interests,
        tsf_attitude: generated.tsf_attitude,
        memo: current.memo,
      });
    } catch (err) {
      console.error("Failed to generate character profile", err);
      setGenerateError(t("characters.generateProfileError"));
    } finally {
      setGenerating(false);
    }
  };

  // 登録済みの 3D モデルと AivisSpeech の話者は、フォームを開いたときに 1 回だけ取る
  const [models, setModels] = useState<AvatarModel[] | null>(null);
  const [speakers, setSpeakers] = useState<AivisSpeaker[] | null>(null);
  const [speakersFailed, setSpeakersFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    listAvatarModels()
      .then((items) => {
        if (!cancelled) setModels(sortAvatarModels(items));
      })
      .catch(() => {
        if (!cancelled) setModels([]);
      });
    getAivisSpeakers()
      .then((items) => {
        if (!cancelled) setSpeakers(items);
      })
      .catch(() => {
        if (!cancelled) setSpeakersFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const avatarId = preset.avatar_model_id ?? "";
  const avatarMissing =
    avatarId !== "" &&
    models !== null &&
    !models.some((model) => model.id === avatarId);
  const voice = preset.voice ?? { speaker_id: "", style_id: "" };
  const speaker =
    speakers?.find((item) => item.speaker_uuid === voice.speaker_id) ?? null;

  const handleSpeakerChange = (speakerId: string) => {
    const next = speakers?.find((item) => item.speaker_uuid === speakerId);
    void save({
      voice: {
        speaker_id: speakerId,
        style_id: next?.styles[0] ? String(next.styles[0].id) : "",
      },
    }).catch(() => {});
  };

  return (
    <div className="character-maker">
      {error && (
        <p className="character-maker__error" role="alert">
          {error}
        </p>
      )}

      <MakerSection
        id="profile"
        storageKey={sectionStorageKey}
        title={t("characters.sections.profile")}
      >
        <SavedTextField
          label={t("characters.fields.name")}
          value={preset.name}
          maxLength={120}
          onSave={async (next) => {
            const name = next.trim();
            if (!name) throw new Error("name_required");
            await save({ name });
          }}
        />
        <SavedTextField
          label={t("characters.fields.memo")}
          value={profileDraft.memo}
          multiline
          rows={3}
          maxLength={1000}
          placeholder={t("characters.fields.memoPlaceholder")}
          onSave={(next) => commitProfile({ memo: next })}
          action={
            <button
              type="button"
              className="character-panel__btn"
              onClick={() => void handleGenerateProfile()}
              disabled={generating}
            >
              {generating ? (
                <>
                  <span className="character-cast__spinner" aria-hidden />
                  {t("characters.generatingProfile")}
                </>
              ) : (
                t("characters.generateProfile")
              )}
            </button>
          }
          hint={generateError ?? t("characters.generateProfileHint")}
        />
        <ProfileFields
          value={profileDraft}
          onChange={(patch) =>
            setProfileDraft((prev) => {
              const next = { ...prev, ...patch } as FullCharacterProfile;
              return next;
            })
          }
          onCommit={(patch) =>
            void commitProfile(patch as Partial<FullCharacterProfile>).catch(
              () => {},
            )
          }
          allowUnsetGender
        />
      </MakerSection>

      <MakerSection
        id="speech"
        storageKey={sectionStorageKey}
        title={t("characters.sections.speech")}
      >
        <SavedTextField
          label={t("characters.fields.speechStyle")}
          value={profileDraft.speech_style}
          maxLength={300}
          placeholder={t("characters.fields.speechStylePlaceholder")}
          onSave={(next) => commitProfile({ speech_style: next })}
        />
        <SavedTextField
          label={t("characters.fields.sampleLines")}
          value={profileDraft.sample_lines}
          multiline
          rows={4}
          maxLength={1000}
          placeholder={t("characters.fields.sampleLinesPlaceholder")}
          hint={t("characters.fields.sampleLinesHint")}
          onSave={(next) => commitProfile({ sample_lines: next })}
        />
      </MakerSection>

      <MakerSection
        id="knowledge"
        storageKey={sectionStorageKey}
        title={t("characters.sections.knowledge")}
      >
        <SavedTextField
          label={t("characters.fields.knowledge")}
          value={profileDraft.knowledge}
          multiline
          rows={6}
          maxLength={4000}
          placeholder={t("characters.fields.knowledgePlaceholder")}
          onSave={(next) => commitProfile({ knowledge: next })}
        />
      </MakerSection>

      {appearance ? (
        <MakerSection
          id="appearance"
          storageKey={sectionStorageKey}
          title={t("characters.sections.appearance")}
        >
          {appearance}
        </MakerSection>
      ) : (
        appearanceNote && (
          <p className="character-maker__note">{appearanceNote}</p>
        )
      )}

      <MakerSection
        id="avatarVoice"
        storageKey={sectionStorageKey}
        title={t("characters.sections.avatarVoice")}
      >
        <label className="character-maker__select-field">
          <span>{t("characters.fields.vrm")}</span>
          <select
            value={avatarId}
            disabled={models === null}
            onChange={(event) =>
              void save({ avatar_model_id: event.target.value }).catch(() => {})
            }
          >
            <option value="">{t("characters.fields.vrmNone")}</option>
            {avatarMissing && (
              <option value={avatarId}>
                {t("characters.fields.vrmMissing")}
              </option>
            )}
            {(models ?? []).map((model) => (
              <option key={model.id} value={model.id}>
                {avatarModelLabel(model)}
              </option>
            ))}
          </select>
        </label>
        <p className="character-cast__hint">
          {avatarMissing
            ? t("characters.fields.vrmMissing")
            : t("characters.fields.vrmHint")}
        </p>

        <label className="character-maker__select-field">
          <span>{t("characters.fields.voice")}</span>
          <select
            value={voice.speaker_id}
            disabled={speakers === null}
            onChange={(event) => handleSpeakerChange(event.target.value)}
          >
            <option value="">{t("characters.fields.voiceDefault")}</option>
            {(speakers ?? []).map((item) => (
              <option key={item.speaker_uuid} value={item.speaker_uuid}>
                {item.name}
              </option>
            ))}
          </select>
        </label>
        {speaker && speaker.styles.length > 1 && (
          <label className="character-maker__select-field">
            <span className="character-maker__select-sub">
              {t("settings.speech.style")}
            </span>
            <select
              value={voice.style_id}
              onChange={(event) =>
                void save({
                  voice: {
                    speaker_id: voice.speaker_id,
                    style_id: event.target.value,
                  },
                }).catch(() => {})
              }
            >
              {speaker.styles.map((style) => (
                <option key={style.id} value={String(style.id)}>
                  {style.name}
                </option>
              ))}
            </select>
          </label>
        )}
        <p className="character-cast__hint">
          {speakersFailed
            ? t("characters.fields.voiceUnavailable")
            : speakers === null
              ? t("characters.fields.voiceLoading")
              : t("characters.fields.voiceHint")}
        </p>
      </MakerSection>

      <MakerSection
        id="greeting"
        storageKey={sectionStorageKey}
        title={t("characters.sections.greeting")}
      >
        <SavedTextField
          label={t("characters.fields.greeting")}
          value={profileDraft.greeting}
          multiline
          rows={2}
          maxLength={300}
          placeholder={t("characters.fields.greetingPlaceholder")}
          hint={t("characters.fields.greetingHint")}
          onSave={(next) => commitProfile({ greeting: next })}
        />
      </MakerSection>
    </div>
  );
}
