import type { AvatarModel } from "../apis/avatars";

/** 登録済み 3D モデルの表示名(分類済みなら「キャラクター / 差分」) */
export function avatarModelLabel(model: AvatarModel): string {
  if (!model.character_name) return model.name;
  return `${model.character_name} / ${model.variant_label ?? model.name}`;
}

/** 表示名の順に並べた新しい配列を返す */
export function sortAvatarModels(
  models: readonly AvatarModel[],
): AvatarModel[] {
  return [...models].sort((a, b) =>
    avatarModelLabel(a).localeCompare(avatarModelLabel(b), "ja"),
  );
}
