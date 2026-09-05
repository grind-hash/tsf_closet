import i18n, { type ParseKeys } from "i18next";
import { initReactI18next } from "react-i18next";

import { en } from "./en";
import { ja } from "./ja";

/** t() に渡せる翻訳キー（ja のリソースから導出） */
export type TranslationKey = ParseKeys;

export const resources = {
  ja: { translation: ja },
  en: { translation: en },
};

// t() のキーを ja のリソースから型付けする。存在しないキーはコンパイルエラーになる。
declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation";
    resources: (typeof resources)["ja"];
  }
}

// ja と en のキー構成が一致していることを型で保証する（片方だけの追加・削除を検出する）。
const _enHasEveryJaKey: typeof ja = en;
const _jaHasEveryEnKey: typeof en = ja;
void _enHasEveryJaKey;
void _jaHasEveryEnKey;

i18n.use(initReactI18next).init({
  resources,
  lng: "ja",
  fallbackLng: "ja",
  interpolation: {
    escapeValue: false,
  },
});

export default i18n;
