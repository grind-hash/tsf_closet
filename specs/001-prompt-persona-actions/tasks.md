# タスク: プロンプトのパーソナリティ対応・行動機能・自分自身モード

**入力元**: 設計ドキュメント `/specs/001-prompt-persona-actions/`
**前提条件**: plan.md (必須), spec.md (必須), research.md, data-model.md, contracts/

**憲章への準拠（Constitution Compliance）**: すべてのタスクは `.specify/memory/constitution.md` の原則を遵守する必要があります:

- UI/UX変更に対するテストファースト (原則 II) — US4/US5/US6 の Playwright E2E テスト
- TypeScriptの厳格な型安全性 (原則 III) — `SelfProfile` 型の明示定義、`any` 不使用
- 集約化されたAPIアーキテクチャ (原則 IV) — self-profile API は `src/apis/settings.ts` に集約
- 警告ゼロの Ruff/ESLint リンティング (原則 III) — Phase 9 で全ファイル検証

**テスト**: E2E テスト (Playwright) を US4/US5/US6 に含む。ユニットテストは Phase 9 (Polish) に含む。

**構成**: タスクは6つのユーザーストーリーごとにグループ化。各ストーリーは独立して実装・テスト可能。

## フォーマット: `[ID] [P?] [Story?] 説明`

- **[P]**: 並列実行可能 (別ファイルであり、未完了タスクへの依存なし)
- **[Story]**: このタスクが属するユーザーストーリー (US1〜US6)
- 説明には正確なファイルパスを含む

---

## フェーズ 1: セットアップ (既存プロジェクト確認)

**目的**: 作業ブランチの確認と既存テストのベースライン確立

- [ ] T001 ブランチ 001-prompt-persona-actions であることを確認し、既存テストを実行してベースラインを確立

---

## フェーズ 2: 基盤 (共有ユーティリティ)

**目的**: 複数のユーザーストーリーが利用する性格タイプ分類インフラの構築

**⚠️ 重要**: このフェーズが完了するまで、ユーザーストーリーの作業は開始できません

- [ ] T002 PERSONALITY_TYPE_KEYWORDS 定数と classify_personality_type() 関数を backend/gateway/services/prompts.py に追加（R-010 準拠: キーワードマッチによる bold/gentle/cheerful/shy/calm/passionate/default 判定）
- [ ] T003 select_opening() 関数を backend/gateway/services/prompts.py に追加（性格タイプ別ルーティング + pronoun フォーマット + used_openings 重複除外ロジック、R-003/R-009 準拠）

**チェックポイント**: classify_personality_type() と select_opening() が単体で動作することを確認

---

## フェーズ 3: ユーザーストーリー 1 — 一人称(pronoun)の動的反映 (優先度: P1) 🎯 MVP

**ゴール**: ハードコードされた「僕」6箇所をテンプレート化し、キャラクターの pronoun で動的に置換する

**独立したテスト**: pronoun が「私」のキャラクター（星野エミ）で変身を実行し、オープニングセリフ・心境テキスト・臨界点セリフすべてに「僕」が含まれないことを確認

### ユーザーストーリー 1 の実装

- [ ] T004 [US1] FIRST_TRANSFORMATION_STAGE の openings 2箇所（index 0, 1）のハードコード「僕」を `{pronoun}` テンプレートに置換 in backend/gateway/services/prompts.py
- [ ] T005 [US1] CRITICAL_POINT_SPEECHES の 75/100 合計4箇所のハードコード「僕」を `{pronoun}` テンプレートに置換 in backend/gateway/services/prompts.py
- [ ] T006 [US1] get_critical_speech() に pronoun パラメータを追加し、返却前に .format(pronoun=pronoun) を適用 in backend/gateway/services/prompts.py
- [ ] T007 [US1] build_enhanced_feeling_prompt() 内のオープニング選択後に .format(pronoun=pronoun) を適用し、game_service.py の get_critical_speech() 呼び出しに pronoun を渡す in backend/gateway/services/game_service.py

**チェックポイント**: pronoun が「私」のキャラクターで変身実行時、心境テキスト内に「僕」が出現しないことを確認

---

## フェーズ 4: ユーザーストーリー 2 — キャラクター性格のプロンプト反映 (優先度: P1)

**ゴール**: キャラクターの personality/description をシステムプロンプトに注入し、性格に応じた語調・反応パターンを実現

**独立したテスト**: 性格が異なる2体のキャラクターで同一衣装変更を実行し、心境テキストの語調に明確な差が出ることを確認

### ユーザーストーリー 2 の実装

- [ ] T008 [US2] build_enhanced_feeling_prompt() に personality と description パラメータを追加 in backend/gateway/services/prompts.py
- [ ] T009 [US2] personality が非空の場合、システムプロンプト末尾に「キャラクターの性格」セクションを動的挿入するロジックを実装 in backend/gateway/services/prompts.py（R-002 準拠）
- [ ] T010 [US2] _generate_feeling_stream() からキャラクターの personality と description を build_enhanced_feeling_prompt() に渡す in backend/gateway/services/game_service.py

**チェックポイント**: personality が「気が強い」と「おっとり」のキャラクターで同じ指示を実行し、語調が異なることを確認

---

## フェーズ 5: ユーザーストーリー 3 — オープニングセリフのバリエーション拡充 (優先度: P2)

**ゴール**: 各心理段階のオープニングセリフを性格タイプ別辞書に拡張し、重複回避メカニズムを追加

**独立したテスト**: 同一キャラクターで連続10回の変身を実行し、オープニングセリフの重複が2回以下であることを確認

**依存関係**: US1 の完了が必要（US1 でテンプレート化した openings をさらに構造変更するため）

### ユーザーストーリー 3 の実装

- [ ] T011 [US3] PSYCHOLOGICAL_STAGES（通常 + NSFW）と FIRST_TRANSFORMATION_STAGE の openings をフラットリストから性格タイプ別辞書構造（default/bold/gentle/cheerful/shy キー）に変換 in backend/gateway/services/prompts.py
- [ ] T012 [US3] 各段階の default オープニングを10個以上、各性格タイプ別オープニングを5個以上に拡充 in backend/gateway/services/prompts.py（NSFW 版も含む）
- [ ] T013 [US3] build_enhanced_feeling_prompt() 内のオープニング選択ロジックを select_opening() 呼び出しに置き換え（classify_personality_type + used_openings 連携）in backend/gateway/services/prompts.py
- [ ] T014 [US3] _generate_feeling_stream() でセッション履歴の直近 feeling_text から冒頭文字列を抽出し used_openings として渡す in backend/gateway/services/game_service.py

**チェックポイント**: 連続10回の変身でオープニングの重複2回以下 + 性格タイプ別に語調が異なること

---

## フェーズ 6: ユーザーストーリー 4 — 変身を伴わない「行動」機能 (優先度: P2)

**ゴール**: `instruction_type: "action"` で場面転換テキストのみを生成し、画像・パラメータの変更をスキップ

**独立したテスト**: メイド服に変身済みのキャラクターに「コンビニに行く」と指示し、テキストが生成され画像が変わらないことを確認

### ユーザーストーリー 4 の実装

- [ ] T015 [P] [US4] 行動機能用プロンプトモジュール backend/gateway/services/action_prompts.py を新規作成（build_action_prompt(): 心理段階別システムプロンプト + NSFW 版、R-005 準拠）
- [ ] T016 [P] [US4] InstructionType に "action" を追加し INSTRUCTION_TYPE_LABELS に「行動」を追加 in frontend/src/types/index.ts
- [ ] T017 [US4] play_with_stream() に instruction_type == "action" 分岐を追加（画像生成・パラメータ計算・タグ分類をスキップし text + complete イベントのみ送信）in backend/gateway/services/game_service.py
- [ ] T018 [US4] ChatInput の instruction_type セレクタに「行動」オプションを追加 in frontend/src/components/chat/ChatInput.tsx
- [ ] T019 [US4] 行動機能の E2E テスト（行動指示 → テキスト生成確認 + 画像未変更確認）in frontend/tests/e2e/action-mode.spec.ts

**チェックポイント**: 行動指示でテキスト生成、画像は変更なし、パラメータは不変

---

## フェーズ 7: ユーザーストーリー 5 — 「自分自身」モード (優先度: P2)

**ゴール**: self_mode フラグでパラメータ計算・心理段階制御をバイパスし、性格プロフィールに基づく自然な反応を生成

**独立したテスト**: 自分自身モードで性格「明るく元気。TSしたい。」のプロフィールで変身を実行し、パラメータが変動せず前向きな反応が返ることを確認

### ユーザーストーリー 5 の実装

- [ ] T020 [P] [US5] DB マイグレーション 008_add_self_mode.py を作成（Session.self_mode BOOLEAN DEFAULT FALSE + User.self_profile_json TEXT NULLABLE）in backend/migrations/versions/008_add_self_mode.py
- [ ] T021 [P] [US5] Session モデルに self_mode カラム、User モデルに self_profile_json カラムを追加 in backend/gateway/databases/models.py
- [ ] T022 [P] [US5] SelfProfile Pydantic モデルを追加（personality, reaction_style, pronoun, interests, tsf_attitude, raw_input フィールド + バリデーション）in backend/gateway/models.py
- [ ] T023 [P] [US5] 自分自身モード用プロンプトモジュール backend/gateway/services/self_mode_prompts.py を新規作成（build_self_mode_feeling_prompt(): 心理段階不使用、self_profile ベース、R-007 準拠）
- [ ] T024 [US5] create_session() に self_mode パラメータを追加し、セッション作成時に保存 in backend/gateway/services/session.py
- [ ] T025 [P] [US5] GameStartRequest に self_mode フィールドを追加し、session レスポンスにも self_mode を含める in backend/gateway/routes/game_router.py
- [ ] T026 [US5] play_with_stream() に self_mode 分岐を追加（パラメータ計算スキップ + 臨界点チェックスキップ + self_mode_prompts 使用）in backend/gateway/services/game_service.py
- [ ] T027 [US5] GameContext に selfMode 状態を追加し、セッション開始時に self_mode を API に渡す in frontend/src/contexts/GameContext.tsx
- [ ] T028 [US5] WelcomeScreen に自分自身モード選択トグル UI を追加 in frontend/src/components/chat/WelcomeScreen.tsx
- [ ] T029 [US5] 自分自身モードの E2E テスト（self_mode ON → 変身 → パラメータ不変確認 + テキスト生成確認）in frontend/tests/e2e/self-mode.spec.ts

**チェックポイント**: self_mode ON で変身後、bloom/shame/adaptation が変動せず、性格に合った反応テキストが生成

---

## フェーズ 8: ユーザーストーリー 6 — 性格自動生成機能 (優先度: P2)

**ゴール**: 入力テキストから LLM で SelfProfile を自動生成し、手動編集・保存を可能にする設定 UI を提供

**独立したテスト**: テキスト入力欄に「アニメオタクの会社員。女装に興味あり。」と入力し「性格を作成」ボタンをクリック、3秒以内にプロフィールが自動生成され編集可能であることを確認

**依存関係**: US5 の完了が必要（DB スキーマ・SelfProfile モデル・self_mode_prompts.py を利用するため）

### ユーザーストーリー 6 の実装

- [ ] T030 [US6] build_self_profile_generation_prompt() を追加（入力テキストから JSON 形式の SelfProfile を生成する LLM プロンプト、R-008 準拠）in backend/gateway/services/self_mode_prompts.py
- [ ] T031 [US6] generate_self_profile()、save_self_profile()、get_self_profile() を実装 in backend/gateway/services/settings_service.py
- [ ] T032 [US6] self-profile CRUD 3エンドポイント（POST /generate、PUT /save、GET /retrieve）を追加 in backend/gateway/routes/settings_router.py
- [ ] T033 [P] [US6] self-profile API 関数（generateSelfProfile, saveSelfProfile, getSelfProfile）を追加 in frontend/src/apis/settings.ts（新規作成）
- [ ] T034 [P] [US6] SettingsContext に selfProfile 状態管理と API 連携を追加 in frontend/src/contexts/SettingsContext.tsx
- [ ] T035 [US6] SelfProfileEditor コンポーネントを新規作成（テキスト入力 + 生成ボタン + 各フィールド編集フォーム + 保存ボタン）in frontend/src/components/settings/SelfProfileEditor.tsx
- [ ] T036 [US6] SettingsScreen に性格プロフィール設定セクションを追加し SelfProfileEditor を統合 in frontend/src/components/settings/SettingsScreen.tsx

**チェックポイント**: テキスト入力 → 自動生成 → 編集 → 保存 → 再読み込みで保存内容が維持されること

---

## フェーズ 9: 仕上げと横断的な関心事

**目的**: コード品質確保、テスト、ドキュメント整合性

- [ ] T037 [P] pronoun 置換・personality 注入・オープニング選択・重複回避のユニットテストを作成 in backend/tests/unit/test_prompts.py
- [ ] T038 [P] 行動プロンプト生成のユニットテストを作成 in backend/tests/unit/test_action_prompts.py
- [ ] T039 [P] 自分自身モードプロンプト生成・性格自動生成プロンプトのユニットテストを作成 in backend/tests/unit/test_self_mode_prompts.py
- [ ] T040 Ruff リンターを全変更バックエンドファイルに実行し warn/error をゼロにする
- [ ] T041 ESLint + Prettier を全変更フロントエンドファイルに実行し warn/error をゼロにする
- [ ] T042 quickstart.md のテストシナリオを通しで検証し、全ステップが正常動作することを確認

---

## 依存関係と実行順序

### フェーズ間の依存関係

- **セットアップ (フェーズ 1)**: 依存なし — すぐに開始可能
- **基盤 (フェーズ 2)**: セットアップ完了に依存 — 全ユーザーストーリーをブロック
- **US1 (フェーズ 3)**: 基盤完了に依存
- **US2 (フェーズ 4)**: 基盤完了に依存 — US1 と並列開始可能（異なるプロンプト領域）
- **US3 (フェーズ 5)**: **US1 完了に依存**（US1 でテンプレート化した openings を構造変更するため）
- **US4 (フェーズ 6)**: 基盤完了に依存 — US1/US2/US3 と独立
- **US5 (フェーズ 7)**: 基盤完了に依存 — US1/US2/US3/US4 と独立
- **US6 (フェーズ 8)**: **US5 完了に依存**（DB スキーマ・SelfProfile モデルを利用）
- **仕上げ (フェーズ 9)**: 全ユーザーストーリー完了に依存

### ユーザーストーリーの依存関係

```
基盤 (Phase 2)
  ├── US1 (Phase 3) ──→ US3 (Phase 5)
  ├── US2 (Phase 4)      (US3 は US1 に依存)
  ├── US4 (Phase 6)
  └── US5 (Phase 7) ──→ US6 (Phase 8)
                          (US6 は US5 に依存)
```

### 各ユーザーストーリー内の順序

- prompts.py の定数変更 → 関数変更 → game_service.py の呼び出し変更
- バックエンド完了 → フロントエンド → E2E テスト
- モデル → サービス → ルーター → フロントエンド
- 各タスクまたは論理グループごとにコミット

---

## 並列実行の例

### US1 + US2 の並列 (基盤完了後)

```
開発者 A: US1 (Phase 3) - prompts.py のオープニング/臨界点テンプレート化
開発者 B: US2 (Phase 4) - prompts.py のシステムプロンプト性格注入
→ ただし同一ファイル (prompts.py) への変更のためマージ時の注意が必要
```

### US4 + US5 の並列 (基盤完了後)

```
開発者 A: US4 (Phase 6) - action_prompts.py + game_service.py action 分岐 + frontend
開発者 B: US5 (Phase 7) - DB migration + self_mode_prompts.py + game_service.py self_mode 分岐 + frontend
→ 新規ファイルが多く、game_service.py のみ競合リスクあり
```

### US5 Phase 内の並列 (T020〜T023)

```
並列バッチ 1:
  T020 [P]: 008_add_self_mode.py (migration)
  T021 [P]: databases/models.py (ORM columns)
  T022 [P]: gateway/models.py (Pydantic model)
  T023 [P]: self_mode_prompts.py (new module)

順次バッチ 2 (バッチ 1 完了後):
  T024: session.py → T025 [P]: game_router.py
  T026: game_service.py

順次バッチ 3 (バッチ 2 完了後):
  T027: GameContext.tsx → T028: WelcomeScreen.tsx → T029: E2E test
```

### US6 Phase 内の並列 (T033〜T034)

```
順次: T030 → T031 → T032 (backend pipeline)

並列バッチ (T032 完了後):
  T033 [P]: apis/settings.ts (API functions)
  T034 [P]: SettingsContext.tsx (state management)

順次: T035 → T036 (frontend components)
```

---

## 実装戦略

### MVP ファースト (US1 のみ)

1. フェーズ 1: セットアップ を完了
2. フェーズ 2: 基盤 を完了
3. フェーズ 3: US1 (pronoun 動的反映) を完了
4. **停止して検証**: pronoun が「私」のキャラクターで全テキストが正しく出力されることを確認
5. 必要なら修正して次へ

### 増分デリバリー (Incremental Delivery)

1. セットアップ + 基盤 → 基盤準備完了
2. US1 + US2 → P1 既存バグ修正完了 → **検証ポイント**
3. US3 → オープニングバリエーション拡充完了 → **検証ポイント**
4. US4 → 行動機能完了 → **検証ポイント**
5. US5 + US6 → 自分自身モード + 性格自動生成完了 → **検証ポイント**
6. 仕上げ → 全ユニットテスト + リンティング + 通しテスト

---

## メモ

- [P] タスク = 別ファイル、依存関係なし → 並列実行可能
- [Story] ラベルはタスクを特定ユーザーストーリーに紐付け
- 各ユーザーストーリーは独立して完了・テスト可能（依存ストーリーを除く）
- game_service.py は US1/US2/US3/US4/US5 すべてで変更されるため、順次マージに注意
- prompts.py は US1/US2/US3 で変更されるため、US1 → US2 → US3 の順序を推奨
- 各タスクまたは論理グループごとにコミット推奨
- 避けるべきこと: 同一ファイルへの並列変更、ストーリー間の暗黙的依存
