export const character = {
  panel: {
    title: "登場人物",
    description:
      "登場中の人物は、画像生成と、心の声・行動・チャットの文章に反映されます。性格を設定すると、その人物の一人称や口調が文章に反映されます。",
    add: "追加",
    adding: "追加中…",
    delete: "削除",
    edit: "編集",
    close: "閉じる",
    empty: "まだ登場人物が登録されていません。",
    featureToggle: "有効",
    featureToggleHint:
      "OFFにすると、複数人表示自体はそのまま保ちつつ、このパネルの登場人物を画像・文章に反映しなくなります（v0.5.0 以前の旧仕様・不安定ながら動作していた複数人表示の振る舞いに戻る）。",
    disabledNote:
      "OFF の間は、登録した登場人物を画像・文章に反映しません。登録内容はそのまま残ります。",
    protagonist_badge: "主人公",
    editCast: "登場人物を編集",
    editOne: "{{name}}の姿と性格を編集",
    groups: "組み合わせ",
    onStageCount: "登場 {{count}} / {{limit}}",
    overLimit:
      "今の画像モデルで1枚に描けるのは{{limit}}人までです。並び順の後ろの人物は生成に使われません。登場をOFFにして人数を調整してください。",
    alwaysOnStage: "主人公は常に登場します",
    onStageLimitReached:
      "今の画像モデルで登場できる人数（{{limit}}人）に達しています",
    notUsed:
      "今の画像モデルで1枚に描ける{{limit}}人を超えているため、生成に使われません",
  },
  field: {
    name: "名前",
    appearance_natural: "外見（自然文）",
    appearance_tags: "外見タグ (NovelAI 形式)",
    negative_tags: "ネガティブタグ（この人物に描かないもの）",
    negative_tags_placeholder: "例：glasses, beard, hat",
    position: "立ち位置",
    appearance_lock: "姿を固定（毎回、設定どおりに描く）",
    exclude_from_effects: "効果対象外（指示の影響を受けない）",
    on_stage: "登場",
    on_stage_of: "{{name}}を登場させる",
  },
  position: {
    left: "左",
    "center-left": "中央左",
    center: "中央",
    "center-right": "中央右",
    right: "右",
  },
  badge: {
    appearance_lock: "姿を固定中：毎回、設定どおりに描きます",
    lock_short: "固定",
    exclude_from_effects: "効果対象外：指示の影響を受けません",
    bystander_short: "対象外",
    profile: "性格が設定されています",
    profile_short: "性格",
    not_used_short: "上限外",
    look_changed:
      "直前の手番で、設定から姿が変わっています（次の手番もこの姿を引き継ぎます）",
    look_changed_short: "変化あり",
  },
  save_status: {
    saved: "保存済み",
    saving: "保存中…",
    dirty: "未保存",
    error: "保存失敗",
  },
  error: {
    name_required: "名前を入力してください",
    limit_exceeded: "登場人物は主人公を含めて最大{{max}}人まで登録できます",
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
    overwrite_confirm:
      "「{{name}}」という名前のプリセットが既に存在します。上書きしますか？",
    delete_confirm: "「{{name}}」を削除しますか？",
    deleting: "削除中…",
    apply_to_protagonist: "主人公に適用",
    apply_to_protagonist_title:
      "現在の主人公の外見をこのプリセットで上書きします",
    apply_to_protagonist_confirm:
      "「{{preset}}」を主人公「{{name}}」に上書き適用しますか？",
  },
  cast: {
    title: "登場人物の設定",
    registeredCount: "登録 {{count}} / {{max}}",
    add: "人物を追加",
    addFromPreset: "プリセットから追加",
    newName: "人物{{number}}",
    appearanceSection: "姿の設定",
    currentLookSection: "現在の姿（直前の手番の結果）",
    currentLookHistory:
      "次の手番は、この姿を引き継いで描きます。姿の設定の欄は書き換わりません。",
    currentLookSpecNext:
      "設定が直前の手番より新しいため、次の手番は設定の姿で描きます。下は直前の手番で描いた姿です。",
    currentLookFixed: "姿を固定しているため、毎回設定の姿で描きます。",
    currentLookEmpty:
      "まだ手番の結果がありません。次の手番は設定の姿で描きます。",
    copyToSpec: "設定にコピー",
    copyToSpecConfirm: "今の外見タグを、現在の姿のタグで置き換えますか？",
    resetLook: "設定の姿に戻す（次の手番から）",
    resetLookUnavailable: "次の手番はすでに設定の姿で描きます",
    generateTags: "自然文からタグを作る",
    generatingTags: "タグを作成中…",
    generateTagsError: "タグを作れませんでした",
    generateTagsConfirm:
      "今の外見タグを、自然文から作ったタグで置き換えますか？",
    generateTagsNeedNatural: "先に外見（自然文）を入力してください",
    tagsHint: "画像にはタグを使います。タグが空のときだけ自然文を使います。",
    naturalChangedHint:
      "自然文を変えましたが、画像には今のタグが使われます。必要なら「自然文からタグを作る」でタグを作り直してください。",
    profileSection: "性格",
    pickAppearance: "姿を選ぶ",
    pickerTitle: "{{name}}の姿を選ぶ",
    resolving: "姿を読み込み中…",
    resolveError: "選んだ姿を読み込めませんでした",
    overwriteAppearanceConfirm:
      "今の外見（自然文・タグ）を、選んだ姿で置き換えますか？",
    noThumbnail: "姿が未選択",
    protagonistProfileNote:
      "主人公の性格は、キャラクターの設定、または自分自身モードのキャラ設定を使います。",
    savePreset: "この人物をプリセットに保存",
    deleteCharacter: "この人物を削除",
  },
  profile: {
    memo: "性格メモ",
    memoPlaceholder:
      "例：主人公の幼なじみ。面倒見がよく、少しおせっかい。料理が得意。",
    generate: "メモから性格を生成",
    generating: "生成中…",
    generateError: "性格の生成に失敗しました",
    generateHint:
      "メモが空のときは、名前と外見から性格を考えます。生成した内容は下の欄で直せます。",
    genderUnset: "未設定",
  },
  group: {
    title: "登場人物の組み合わせ",
    description:
      "主人公以外の登場人物（外見・ネガティブタグ・性格・登場ON/OFF）をまとめて保存し、別のセッションで呼び出せます。",
    namePlaceholder: "組み合わせの名前",
    saveCurrent: "今の登場人物を組み合わせとして保存",
    saving: "保存中…",
    saved: "「{{name}}」を保存しました",
    overwriteConfirm:
      "「{{name}}」という組み合わせが既にあります。今の登場人物で上書きしますか？",
    apply: "この組み合わせに入れ替える",
    applying: "入れ替え中…",
    applyConfirm:
      "主人公以外の登場人物を「{{name}}」の{{count}}人に入れ替えます。今の登場人物（主人公以外）は削除されます。よろしいですか？",
    applied: "「{{name}}」に入れ替えました。",
    delete: "組み合わせ「{{name}}」を削除",
    deleteConfirm: "組み合わせ「{{name}}」を削除しますか？",
    empty: "保存済みの組み合わせはありません。",
    loading: "読み込み中…",
    memberCount: "{{count}}人",
    showMembers: "メンバーを表示",
    hideMembers: "メンバーを隠す",
    offStage: "登場OFF",
    nothingToSave:
      "主人公以外の登場人物がいないため、組み合わせとして保存できません",
  },
};
