export const characters = {
  title: "キャラクター",
  intro:
    "キャラチャットで話すキャラクターを作って管理します。名前・一人称・性格・口調・知識・姿・3D モデル・声を決めておくと、そのキャラクターとして会話を始められます。作ったキャラクターは通常プレイの登場人物にも使えます。",
  create: "新しいキャラクターを作る",
  creating: "作成しています...",
  newName: "新しいキャラクター",
  empty: "まだキャラクターがありません。",
  loading: "読み込み中...",
  talk: "このキャラと話す",
  talking: "会話を準備しています...",
  edit: "編集する",
  delete: "このキャラクターを削除",
  deleteTitle: "キャラクターを削除しますか？",
  deleteBody:
    "{{name}}の設定と立ち絵を削除します。このキャラクターとの会話は残り、いまの名前と一人称のまま続けられます。元に戻せません。",
  deleteConfirm: "削除する",
  cancel: "キャンセル",
  back: "一覧へ戻る",
  notFound: "このキャラクターは見つかりませんでした。",
  badgeVrm: "3D",
  badgeVoice: "声",
  noPersonality: "性格は未設定",
  sections: {
    profile: "名前と性格",
    speech: "話し方",
    knowledge: "知識・背景",
    appearance: "外見と立ち絵",
    avatarVoice: "3D モデルと声",
    greeting: "会話の始まり",
  },
  fields: {
    name: "名前",
    memo: "メモ",
    memoPlaceholder:
      "キャラクターの雰囲気や設定のメモ。「LLM で性格を下書き」の手がかりになります。",
    speechStyle: "口調・話し方",
    speechStylePlaceholder: "例: 丁寧語で、相手を「先輩」と呼ぶ",
    sampleLines: "セリフの例",
    sampleLinesPlaceholder:
      "1 行に 1 つ書きます。例:\n「おかえりなさい、先輩」\n「もう、しょうがないですね」",
    sampleLinesHint:
      "口調の手本として渡します。キャラクターがそのまま繰り返すことはありません。",
    knowledge: "知識・背景",
    knowledgePlaceholder:
      "生い立ち、仕事、好きなもの、相手との関係など。キャラクターにとっての事実として扱います。",
    greeting: "最初のひとこと",
    greetingPlaceholder: "例: いらっしゃい。今日は何の話をしようか？",
    greetingHint:
      "新しく会話を始めたとき、キャラクターの最初の発言として表示します。空なら、あなたから話しかけて始まります。",
    appearanceNatural: "外見（自然文）",
    appearanceTags: "外見タグ",
    appearanceTagsHint:
      "立ち絵の生成と、キャラチャットの姿の初期値に使います。性別のタグ（1girl など）が無いときは、性格の性別から補います。",
    vrm: "3D モデル",
    vrmNone: "使わない（立ち絵で表示）",
    vrmMissing: "選んでいた 3D モデルは削除されています。",
    vrmHint:
      "キャラチャットで、このキャラクターを 3D モデルで表示します。会話中に「姿」メニューで別のモデルへ切り替えることもできます。",
    voice: "声",
    voiceDefault: "設定画面の声を使う",
    voiceLoading: "AivisSpeech の話者を読み込んでいます...",
    voiceUnavailable:
      "AivisSpeech の話者を読み込めませんでした。設定画面で音声合成を有効にすると選べます。",
    voiceHint: "キャラチャットで返答を読み上げるときの声です。",
  },
  generateProfile: "LLM で性格を下書き",
  generatingProfile: "下書きしています...",
  generateProfileHint:
    "名前・外見・メモから、性格・一人称・性別・趣味などを埋めます。口調・セリフの例・知識は変えません。",
  generateProfileError: "性格を下書きできませんでした。",
  generateTags: "外見の自然文からタグを作る",
  generatingTags: "タグを作っています...",
  generateTagsNeedNatural: "外見の自然文を入れると作れます。",
  generateTagsConfirm:
    "いまの外見タグを、自然文から作ったタグで置き換えますか？",
  generateTagsError: "外見タグを作れませんでした。",
  portrait: {
    title: "立ち絵",
    none: "立ち絵はまだありません。",
    import: "素材の画像を立ち絵にする",
    importTitle: "立ち絵にする画像を選ぶ",
    importHint:
      "セッション・お気に入り・Prompt Expander の画像をそのまま使います。外見タグが空なら、その画像の外見も取り込みます。",
    generate: "外見タグから立ち絵を描く",
    generating: "立ち絵を描いています...",
    generatingHint:
      "画像生成には1分ほどかかることがあります。描き終わるまでこの画面を開いたままにしてください。",
    needTags: "外見タグを入れると描けます。",
    precise: "精密参照を使う",
    preciseHint:
      "いまの立ち絵を精密参照（character reference）として送り、参照1枚あたり Anlas を追加消費します。",
    anlasBody:
      "精密参照を使って立ち絵を描きます。参照1枚あたり Anlas を追加消費します。続けますか？",
    imported: "素材の画像を立ち絵にしました。",
    importedWithTags: "素材の画像を立ち絵にし、外見タグも取り込みました。",
  },
  preview: {
    title: "プレビュー",
    vrmLoading: "3D モデルを読み込んでいます...",
    talkHint:
      "このキャラクターとの会話があれば続きを開き、無ければ新しく始めます。",
  },
  errors: {
    loadFailed: "キャラクターを読み込めませんでした。",
    saveFailed: "保存できませんでした。",
    createFailed: "キャラクターを作れませんでした。",
    deleteFailed: "キャラクターを削除できませんでした。",
    talkFailed: "会話を始められませんでした。",
    portraitFailed: "立ち絵を描けませんでした。",
    importFailed: "画像を立ち絵にできませんでした。",
  },
};
