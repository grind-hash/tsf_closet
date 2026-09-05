export const character = {
  panel: {
    title: "登場人物",
    description:
      "この情報は、画像生成時のプロンプトにのみ反映されます（チャット応答の内容には反映されません）。",
    add: "追加",
    adding: "追加中…",
    delete: "削除",
    edit: "編集",
    close: "閉じる",
    empty: "まだ登場人物が登録されていません。",
    featureToggle: "有効",
    featureToggleHint:
      "OFFにすると、複数人表示自体はそのまま保ちつつ、このパネルの登場人物情報を画像プロンプトへ注入しなくなります（v0.5.0 以前の旧仕様・不安定ながら動作していた複数人表示の振る舞いに戻る）。",
  },
  field: {
    name: "名前",
    appearance_natural: "外見（自然文）",
    appearance_tags: "外見タグ (NovelAI 形式)",
    position: "立ち位置",
  },
  save_status: {
    saved: "保存済み",
    saving: "保存中…",
    dirty: "未保存",
    error: "保存失敗",
  },
  error: {
    name_required: "名前を入力してください",
    limit_exceeded: "登場人物は最大4人までです",
  },
  confirm: {
    delete: "{{name}}を削除しますか？",
  },
  preset: {
    apply_button: "プリセット",
    picker_title: "プリセットから追加",
    loading: "読み込み中…",
    empty: "保存済みのプリセットはありません。",
    apply: "適用",
    applying: "適用中…",
    save: "プリセット保存",
    saving: "保存中…",
    save_prompt: "プリセット名を入力",
  },
};
