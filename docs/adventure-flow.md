# アドベンチャーモードの処理の流れ

Adventure（ミッション系プリセットと恋愛シミュレーション）の処理をシーケンス図でまとめる。
VS Code の Markdown プレビュー、または GitHub 上でそのまま Mermaid として表示できる。

対象コード:

- バックエンド: `backend/gateway/routes/adventure_router.py`、`backend/gateway/services/adventure_service.py`、`backend/gateway/services/adventure_romance.py`
- フロントエンド: `frontend/src/components/adventure/AdventureScreen.tsx`（入口。セットアップは `AdventureHub.tsx`、プレイは `AdventurePlay.tsx`）、`frontend/src/contexts/AdventureContext.tsx`、`frontend/src/apis/adventure.ts`

---

## 1. 全体像

Adventure は通常ゲームとは別の Context・API・サービス・DBモデル・SSE契約を持つ。

```mermaid
flowchart LR
    subgraph FE[フロントエンド]
        Screen[AdventureScreen]
        Ctx[AdventureContext]
        Api[apis/adventure.ts]
    end
    subgraph BE[バックエンド]
        Router[adventure_router]
        Svc[AdventureService]
        Romance[adventure_romance]
    end
    subgraph EXT[外部]
        LLM[llm_service<br/>selfhost / OpenRouter / NovelAI]
        Img[image_service<br/>selfhost / OpenRouter / NovelAI]
    end
    DB[(SQLite<br/>AdventureRun<br/>AdventureTurn)]

    Screen --> Ctx --> Api -->|REST / SSE| Router --> Svc
    Svc --> Romance
    Svc --> LLM
    Svc --> Img
    Svc --> DB
```

---

## 2. 1手番で何が送られるか

**1手番につき LLM を3回呼ぶ。** 画像タグだけを見ても入力側は分からないので、
付与した属性などを確認したいときは各回の user プロンプトを見る。

| 回  | 目的                       | システムプロンプト           | user プロンプト                     |
| --- | -------------------------- | ---------------------------- | ----------------------------------- |
| ①   | 物語本文（ストリーム）     | `_narrative_system_prompt`   | `turn_context` の JSON              |
| ②   | 判定（選択肢・BGM・好感度）| `_resolution_system_prompt`  | `turn_context` の JSON（①と同じ）   |
| ③   | ビジュアル（画像タグ）     | `_visual_system_prompt`      | `_visual_user_payload`（本文を含む）|

`turn_context` には `reality_rules`（付与した属性）、`state`、`sim`、
`required_visual_appearance` などが入る。持ち物システムが ON の run では
`inventory`（所持品と直近ログ）、`npc_states`（境界侵害の記録）、パネル操作なら
`item_action` / `item_resolution` も入り、②の判定出力に `world_events`（物語が実際に
示した受け渡し・使用・着脱・境界侵害）と、現実改変ターンだけ `reality_patch`
（所持品・NPC 記憶の直接書き換え）が加わる。Python 側が所持・数量・能力を検証して
適用するため、プレイヤーの発言だけでは持ち物は増えない。`ENABLE_PROMPT_PREVIEW=true` なら
画像設定ポップオーバーの「プロンプトを確認」から実際の送信文字列を確認できる。

---

## 3. ターン処理（中心的な流れ）

```mermaid
sequenceDiagram
    autonumber
    actor U as プレイヤー
    participant S as AdventureScreen
    participant C as AdventureContext
    participant R as adventure_router
    participant SV as AdventureService.stream_turn
    participant L as llm_service
    participant I as image_service
    participant DB as SQLite

    U->>S: 選択肢 / 自由入力 / ギフト / バイト / 告白
    S->>C: submitTurn(input, inputKind)
    alt NovelAI かつ romance かつ精密参照ON かつ抑止されていない
        C-->>U: Anlas消費の確認ダイアログ
        U->>C: 続行を選択
    end
    C->>R: POST /runs/{id}/turns/stream
    R->>SV: stream_turn

    SV->>SV: run ロック取得（同一runのターンを直列化）
    SV->>DB: run と turns を取得
    alt client_turn_id が処理済み
        SV-->>C: turn / complete をそのまま返す
        Note over SV,C: 再送は二重に実行しない
    end
    SV->>SV: 開始時外見キーのバックフィル（旧run対応）
    opt 手番0
        SV->>DB: opening_state_json を保存（手番0への巻き戻し用）
    end

    SV->>SV: _build_turn_contexts
    Note over SV: 「現実改変：〜」を検出したら reality_alter へ昇格<br/>手番を使わず付与した未反映ルールを取り出す<br/>romance の金銭・採点・告白成否を先に確定する
    alt 資金不足などで成立しない
        SV-->>C: error
        Note over SV,C: 手番は消費しない
    end

    SV-->>C: status（phase=narrative）
    SV->>L: ① 物語生成
    loop ストリーム受信
        L-->>SV: チャンク
        SV-->>C: narrative_chunk
    end
    SV-->>C: narrative_done

    par ② 判定
        SV->>L: 解決の構造化出力
        L-->>SV: 選択肢 / 手掛かり / 進行目標 / BGM / 好感度
    and ③ ビジュアルと画像生成
        SV->>L: ビジュアルの構造化出力
        L-->>SV: visual_state と画像タグ
        SV->>SV: 外見ロックの更新（外見が変わり得る手番のみ）
        opt 立ち絵ONのターン
            SV->>I: 主人公の立ち絵
            I-->>SV: 画像
            SV-->>C: portrait_image
        end
        opt romance かつ攻略対象が場面に居る
            SV->>I: 攻略対象の立ち絵
            I-->>SV: 画像
            SV-->>C: partner_image
        end
        opt 合成モード
            SV->>I: 合成シーン
            I-->>SV: 画像
            SV-->>C: image
        end
    end

    SV->>SV: _merge_output（state更新・エンド判定）
    opt romance
        SV->>SV: apply_romance_outcome（好感度・所持金・milestone）
        SV->>SV: 攻略対象の外見を visual 出力から書き戻し
    end
    SV->>DB: state_json / turn_count / AdventureTurn を保存
    SV-->>C: turn
    SV-->>C: complete
    C->>R: GET /runs/{id}
    R-->>C: 最新の run
    C-->>S: activeRun を更新
```

### 補足

- **プロバイダーは通常ゲームと同じ設定に従う**。テキストは `FEELING_PROVIDER`、
  画像は `IMAGE_PROVIDER`（selfhost / openrouter / novelai）。NovelAI固有機能は
  次のように劣化する: 非NovelAIではキャラクター枠・negative prompt・seed が
  使えず1本のプロンプトへ畳む（`_flatten_scene_prompt`）。参照画像は追加費用
  なしで常に使う（精密参照トグルはNovelAI専用）。selfhost（ComfyUI）は
  背景を txt2img 用ワークフロー（`COMFYUI_TXT2IMG_WORKFLOW_PATH`、既定は編集用
  テンプレート名の `image_edit` を `image_txt2img` に置き換えたもの）で生成し、
  立ち絵・合成は既存画像の編集で賄う。
- **並列なのは②と③だけ**で、①の本文が確定してから走る。③は本文を入力に取るため。
- **画像は③の中で直列**に生成する（背景 → 主人公の立ち絵 → 攻略対象の立ち絵 →
  合成シーン）。立ち絵と合成で同じシードを使い、衣装の描画差を抑える。
  **対面会話モード**（romance の `state_json["companion_mode"]`）では
  1手番＝1往復の会話になる（半日枠・昼夜・時間経過は無く、判定結果の
  day/slot は LLM に見せない。尺は日数でなくターン数）。本文は3ビート
  「相手の反応の地の文1行 → 攻略対象のセリフ1〜2行 → 相手側からの展開（問い返し・
  行動・話題の一歩）」で全体2〜5文を台本形式（`名前「セリフ」` の独立行）で
  書かせ、FE が話者ラベル表示と読み上げ対象の抽出に使う。拒絶・沈黙など短さが
  答えになる場面は短いままにする。画像は主人公の
  立ち絵と合成シーンを設定に関わらず省き、背景（現在地が変わったときだけ。
  キーは時間帯を含まない現在地のみで、昼夜タグも落として生成する）と
  攻略対象の立ち絵だけを描く。攻略対象の立ち絵を描かなかった手番（場面が
  前手番と同じ・相手が場面に居ない・毎ターン描く OFF・生成失敗・場面判定失敗）は
  理由を `state_json["partner_portrait_status"]` に記録して `turn` / run に載せ、
  FE がメッセージ窓のメタ行とターン詳細に「立ち絵は前の手番のまま（理由）」を出す。
  **OpenRouter のときだけ**、従量課金APIで同時リクエストが可能なため
  背景・主人公・攻略対象を `asyncio.gather` で並列生成する（合成のみ後段）。
  `model_execution_gate` も OpenRouter は直列化しない。並列時の state 保存は
  `_persist_locks` で read-modify-write を直列化する。
- **API料金（OpenRouter）**はターン内の全呼び出しを `_CostTracker`
  （ContextVar）で集計し、`complete` 直前に `cost` イベントで配信する。
  REST応答（run作成・セットアップ生成・選択肢再生成・画像再生成）は
  `cost_usd` フィールドで返す。FEは `SettingsContext.totalCost` へ累算し、
  HUDのメトリクス行に累計を表示する。
- **攻略対象の外見の書き戻しは `apply_romance_outcome` より後**に行う。
  判定側は visual を見ない別呼び出しで、入れ替わり宣言でも元の外見をそのまま
  返してくることがあり、先に書くと上書きされて次の手番で姿が戻る。
- SSE イベントは `status` / `narrative_chunk` / `narrative_done` / `portrait_image` /
  `partner_image` / `background_image` / `image` / `cost` / `turn` / `complete` /
  `error`。通常ゲームの `useSSE` には流さず、`apis/adventure.ts` の専用パーサで
  処理する。トーク（5. 参照）は同じパーサで `talk_chunk` / `talk_done` を扱う。
- **3D モデル表示中の FE** は `narrative_done` の時点で攻略対象のセリフの読み上げを
  始め（②の判定と保存を待たない）、ステージの進捗オーバーレイを出さずに判定中の
  進捗を行動パネルに出す。表情・身振りは `turn` で届くので、その時点で切り替える。

---

## 4. Run の作成

```mermaid
sequenceDiagram
    autonumber
    actor U as プレイヤー
    participant S as セットアップ画面
    participant C as AdventureContext
    participant R as adventure_router
    participant SV as AdventureService
    participant L as llm_service
    participant I as image_service
    participant DB as SQLite

    U->>S: 素材セッション / プリセット / 日数・手数を選択
    S->>C: generateSetup
    C->>R: POST /adventure/setup/generate
    R->>SV: generate_setup
    SV->>L: 設定・目的・制約の生成
    L-->>SV: setting / objective / constraints
    SV-->>C: セットアップ案
    C-->>U: 内容を確認・編集

    U->>S: 開始
    alt NovelAI かつ精密参照ON
        C-->>U: Anlas消費の確認ダイアログ
        U->>C: 続行を選択
    end
    S->>C: createRun
    C->>R: POST /adventure/runs
    R->>SV: create_run
    SV->>DB: 素材セッションのスナップショット取得
    opt romance
        SV->>L: 相手プロフィール / ギフトカタログ / 隠し好みの生成
        Note over SV: 素材の人物は攻略対象。主人公は別途選択したキャラへ差し替える
    end
    SV->>L: 開幕シーンの生成
    L-->>SV: 本文 / 選択肢 / visual_state
    SV->>I: 開始画像
    SV->>DB: AdventureRun を作成
    SV->>SV: _generate_opening_visuals
    SV->>I: 背景 / 主人公の立ち絵 / 攻略対象の立ち絵 / 合成シーン
    Note over SV: 失敗しても run 作成は成功扱いにする<br/>OpenRouterでは背景・立ち絵を並列生成する<br/>selfhostはtxt2imgワークフローで背景を描く
    SV-->>C: run（OpenRouterでは cost_usd を含む）
    C-->>U: プレイ画面へ
```

---

## 5. 手番を消費しない操作

進行を進めずに state だけを変える操作。いずれも `stream_turn` と同じ run ロックを
取るので、ターン処理中は完了を待ってから実行される。

```mermaid
sequenceDiagram
    autonumber
    actor U as プレイヤー
    participant C as AdventureContext
    participant R as adventure_router
    participant SV as AdventureService
    participant DB as SQLite

    rect rgb(240, 240, 245)
        Note over U,DB: 属性（現実改変ルール）の管理
        U->>C: 付与のみ / 編集 / 削除
        C->>R: PATCH /runs/{id}/reality-rules
        R->>SV: update_reality_rules
        SV->>SV: 正規化・重複排除・上限12件を検証
        SV->>SV: 新規分を pending_reality_rules に控える
        SV->>DB: state_json を更新
        SV-->>C: run 全体
        Note over SV: 控えた分は次の手番で一度だけ<br/>「この手番で確定したルール」として渡る
    end

    rect rgb(240, 245, 240)
        Note over U,DB: 画像設定の変更
        U->>C: 精密参照 / 合成モード / 衣装レイヤー / 対面会話モード
        C->>R: PATCH /runs/{id}/settings
        R->>SV: update_run_settings
        SV->>DB: state_json を更新
        SV-->>C: run 全体
    end

    rect rgb(250, 240, 245)
        Note over U,DB: トーク（romance。手番を消費しない会話）
        U->>C: 「トーク」で自由入力を送信
        C->>R: POST /runs/{id}/talk/stream
        R->>SV: stream_talk
        SV->>SV: 攻略対象として返答（LLM 1回、画像なし）
        SV-->>C: talk_chunk（逐次）
        SV->>DB: state_json.talk_log だけを更新（上限40件）
        SV-->>C: talk_done / cost / complete
        Note over SV: turn_count・status・sim・AdventureTurn には触れない。<br/>最後の手番以降の分は次の手番へ recent_talk として渡る。<br/>採点（好感度・金銭）には影響させない
    end

    rect rgb(245, 240, 240)
        Note over U,DB: プロンプト確認（ENABLE_PROMPT_PREVIEW 有効時のみ）
        U->>C: プロンプトを確認
        C->>R: POST /runs/{id}/preview-prompt
        R->>SV: preview_turn_prompts
        SV->>SV: state のコピー上で3回分を組み立てる
        SV-->>C: system / user と画像生成の最終文字列
        Note over SV: LLMは呼ばず、state も書き換えない
    end

    rect rgb(245, 245, 235)
        Note over U,DB: 巻き戻し
        U->>C: ここからやり直す
        C->>R: POST /runs/{id}/rewind
        R->>SV: rewind_to_turn
        SV->>DB: 対象手番のスナップショットで state を復元
        SV->>DB: それ以降の AdventureTurn を削除
        Note over SV: 画像設定と人称は現在値を引き継ぐ<br/>付与した属性は復元対象なので巻き戻る
        SV-->>C: run 全体
    end
```

---

## 6. 画像の再生成

場面画像のタグを手で直して描き直す経路。手番は進まない。

```mermaid
sequenceDiagram
    autonumber
    actor U as プレイヤー
    participant M as AdventureImagePromptModal
    participant C as AdventureContext
    participant R as adventure_router
    participant SV as AdventureService
    participant I as image_service

    U->>M: scene_tags / player_tags / npc_tags を編集
    M->>C: regenerateImage
    C->>R: POST /runs/{id}/image/stream
    R->>SV: 立ち絵 または 合成シーン、または攻略対象の立ち絵（target: partner。対面会話モードの↻）の生成
    Note over SV: 編集内容は prompt_override として渡るので<br/>画像タグ生成のLLM呼び出しは走らない
    SV->>I: 画像生成
    I-->>SV: 画像
    SV-->>C: image / portrait_image / partner_image
    opt OpenRouter利用時
        SV-->>C: cost（このストリームのAPI料金）
    end
    C-->>U: ステージを更新
```

> このモーダルが扱うのは最終段の画像タグだけで、付与した属性などの入力側は
> すでにタグへ蒸留されている。入力側を見たい場合は「5. 手番を消費しない操作」の
> プロンプト確認を使う。
