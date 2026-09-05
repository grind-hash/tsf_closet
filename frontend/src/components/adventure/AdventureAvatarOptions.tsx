import { useTranslation } from "react-i18next";
import {
  type AvatarModel,
  avatarVariantLabel,
  groupAvatarModels,
} from "../../apis/avatars";

// 3D モデル(VRM)の選択肢と衣装差分のヒント。セットアップ画面とプレイ画面で共有する。

/**
 * 3D モデル選択の option 群。同じキャラクターの衣装差分は optgroup にまとめ、
 * 差分ラベルで見せる(未分類はモデル名のまま)
 */
export function AvatarModelOptions({ models }: { models: AvatarModel[] }) {
  return (
    <>
      {groupAvatarModels(models).map((group) =>
        group.character === null ? (
          group.models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.name}
            </option>
          ))
        ) : (
          <optgroup
            key={`character:${group.character}`}
            label={group.character}
          >
            {group.models.map((model) => (
              <option key={model.id} value={model.id}>
                {avatarVariantLabel(model)}
              </option>
            ))}
          </optgroup>
        ),
      )}
    </>
  );
}

/** 選択中モデルに衣装差分(同じキャラクター 2 件以上)があるときだけ出す説明 */
export function AvatarWardrobeHint({
  models,
  selectedId,
}: {
  models: AvatarModel[];
  selectedId: string | null | undefined;
}) {
  const { t } = useTranslation();
  const selected = models.find((model) => model.id === selectedId);
  if (!selected?.character_name) return null;
  const total = models.filter(
    (model) => model.character_name === selected.character_name,
  ).length;
  if (total < 2) return null;
  return (
    <span className="adventure-setup-turns__hint adventure-setup-avatar__wardrobe">
      {t("adventure.avatar.wardrobeHint", {
        character: selected.character_name,
        total,
      })}
    </span>
  );
}
