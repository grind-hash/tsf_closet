# タスク: 行動モード画像生成

**入力元**: 設計ドキュメント `specs/001-prompt-persona-actions/002-action-scene-image/`
**前提条件**: plan.md (必須), spec.md, research.md, data-model.md, contracts/game-api.md, quickstart.md

**憲章への準拠（Constitution Compliance）**: すべてのタスクは `.specify/memory/constitution.md` の原則を遵守:

- UI/UX変更に対するテストによる品質保証 (原則 II)
- TypeScriptの厳格な型安全性 (原則 III)
- 集約化されたAPIアーキテクチャ (原則 IV)
- 警告ゼロの ESLint/Prettier/Ruff リンティング (原則 III)

**テスト**: spec.md で Playwright E2E テストが要求されているため、テストタスクを含む。

**構成**: この機能は既存プロジェクトへの拡張であり、全ユーザーストーリー (US1-US5) が同一のバックエンドコード（action_prompts.py + game_service.py）に依存するため、機能レイヤーごとにフェーズ分けし、ユーザーストーリーのカバレッジをラベルで追跡する。

## フォーマット: `[ID] [P?] [Story] 説明`

- **[P]**: 並列実行可能 (別ファイルであり、依存関係がない)
- **[Story]**: このタスクがカバーするユーザーストーリー (例: US1, US2, US3)
- 説明には正確なファイルパスを含めること

---

## フェーズ 1: セットアップ (不要)

**目的**: 既存プロジェクトへの拡張のため、セットアップフェーズは不要。

- 新規プロジェクト初期化なし
- 新規依存関係なし
- DB マイグレーションなし
- API エンドポイント追加なし

---

## フェーズ 2: 基盤 — 場面変更用プロンプトテンプレート

**目的**: 全ユーザーストーリーが依存するプロンプトテンプレートとヘルパー関数の作成

**⚠️ 重要**: このフェーズが完了するまで、画像生成パイプラインの改修は開始できません

- [x] T001 [P] backend/gateway/services/action_prompts.py に NovelAI タグ形式の場面変更システムプロンプト `ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI` (SFW) と `ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NOVELAI_NSFW` を追加。キャラクタータグを `{}` で強調維持し背景タグのみ変更する指示を含める
- [x] T002 [P] backend/gateway/services/action_prompts.py に Qwen Image Edit 用の場面変更システムプロンプト `ACTION_IMAGE_EDIT_SYSTEM_PROMPT` (SFW) と `ACTION_IMAGE_EDIT_SYSTEM_PROMPT_NSFW` を追加。"Keep the person exactly as they are" の制約を含める
- [x] T003 [P] backend/gateway/services/action_prompts.py に NovelAI GLM-4.6 用の場面変更タグ生成システムプロンプト `ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM` (SFW) と `ACTION_NOVELAI_PROMPT_GENERATION_SYSTEM_NSFW` を追加。人物タグ維持 + 背景タグ変更の指示を含める
- [x] T004 backend/gateway/services/action_prompts.py に `get_action_image_edit_system_prompt(image_provider: str, nsfw_mode: bool) -> str` を実装。image_provider と nsfw_mode に応じて適切なテンプレートを返す
- [x] T005 backend/gateway/services/action_prompts.py に `build_action_image_edit_prompt(instruction: str, current_description: str) -> str` を実装。行動指示と現在の画像説明から場面変更用ユーザープロンプトを構築する
- [x] T006 backend/gateway/services/action_prompts.py に `get_action_novelai_prompt_generation_system(nsfw_mode: bool, language: str) -> str` を実装。GLM-4.6 用の場面変更システムプロンプトを返す

**チェックポイント**: プロンプトテンプレートと関数が揃い、game_service.py からの呼び出しが可能

---

## フェーズ 3: ユーザーストーリー 1+2+3 (+4基盤) — 行動モード画像生成パイプライン (P1) 🎯 MVP

**ゴール**: action mode で場面変更画像を生成し、テキストと並列でストリーミングする。変身後 (US1)、変身前 (US2)、NovelAI Opus (US3) の全ケースに対応。非 NovelAI (US4) の基盤パスも含む。

**独立したテスト**: 「行動」モードで指示を送信し、SSEストリームで画像とテキストの両方が返されることを確認。変身回数が変わらないことを検証。

### US1+US2+US3 の実装

- [x] T007 [US1] [US2] [US3] backend/gateway/services/game_service.py の action mode セクションに NovelAI Opus 判定を追加。`is_novelai_opus_mode` フラグを取得し、`previous_prompt` を最新履歴の `after_description` から取得する
- [x] T008 [US3] backend/gateway/services/game_service.py の action mode に NovelAI Opus パスを実装。`get_action_novelai_prompt_generation_system()` で専用システムプロンプトを取得し、`llm_service.generate_novelai_image_prompt()` で場面変更タグを生成する。`build_novelai_prompt_generation_user()` には既存の `previous_prompt` と `character_base_tags` を渡す
- [x] T009 [US4] backend/gateway/services/game_service.py の action mode に非 NovelAI パスを実装。Vision LLM (`_describe_image()`) で現在画像を分析し、`get_action_image_edit_system_prompt()` と `build_action_image_edit_prompt()` で場面変更用編集プロンプトを生成する
- [x] T010 [US1] [US2] [US3] backend/gateway/services/game_service.py の action mode に行動専用のデフォルト i2i_strength (0.85) を設定。`inpaint_strength` が明示指定されていない場合のみ適用する（i2i_noise は環境変数デフォルト 0.0 をそのまま使用。R-001 実測に基づき 0.45 から変更）
- [x] T011 [US1] [US2] [US3] backend/gateway/services/game_service.py の action mode でテキスト生成と画像生成を `asyncio.gather()` で並列実行するよう改修。`text_producer` (既存の心境モノローグ生成) と `image_producer` (`_generate_image()` 呼び出し) を並列で実行する
- [x] T012 [US1] [US2] [US3] backend/gateway/services/game_service.py の action mode に SSE イベント送信を追加。`image` イベント (生成された場面画像 + history_id)、`cost` イベント (画像生成コスト)、`complete` イベント (`transformation_count` は変更なし) を送信する。`stats`/`critical`/`ending`/`achievement` イベントは送信しない
- [x] T013 [US5] backend/gateway/services/game_service.py の action mode の履歴保存を改修。`add_history()` に生成された場面画像を `image_data` として渡し、`after_description` に生成されたプロンプト/タグを保存する。`current_image_path` をセッションに更新する
- [x] T014 [US1] [US2] backend/gateway/services/game_service.py の action mode で変身回数インクリメント・パラメータ更新・タグ分類・臨界点判定・エンディング判定・実績判定をスキップすることを確認。早期 return の代わりに、画像生成後に complete イベントを送信して正常終了する

**チェックポイント**: action mode で画像生成が動作し、text + image + complete イベントが SSE で返され、変身回数・パラメータが変化しない

---

## フェーズ 4: フォールバック — 画像生成失敗時の処理 (P2)

**ゴール**: NovelAI / 非 NovelAI 双方の画像生成パスにおいて、失敗時にテキストのみでフォールバックする。

**独立したテスト**: 画像生成を意図的に失敗させ、テキストのみ表示で前回の画像が維持されることを確認。

### FR-011 の実装

> T009 で基本的な非 NovelAI パスは実装済み。ここでは全パスのフォールバックを対応。

- [x] T015 [US1] [US3] [US4] backend/gateway/services/game_service.py の action mode 全パス（NovelAI / 非 NovelAI）に画像生成失敗時のフォールバックを実装。画像生成に失敗した場合はテキストのみ表示し、前回の画像を維持する (FR-011)

**チェックポイント**: 全モードで画像生成失敗時にテキストのみ表示され、前回の画像が維持される

---

## フェーズ 5: ユーザーストーリー 5 — 行動後の履歴管理 (P2)

**ゴール**: 行動で生成された画像が履歴に正しく保存され、次回の行動/変身のベースになる。

**独立したテスト**: 行動実行後に履歴を確認し、行動画像が表示されることを検証。その画像をベースに次の変身が可能なことを確認。

### US5 の実装

> T013 で基本的な履歴保存とセッション更新は実装済み。ここでは連続行動の動作を確認。

- [ ] T016 [US5] backend/gateway/services/game_service.py の action mode で連続行動（行動→行動）のシナリオを手動テストで検証。前回の行動画像が `before_image` として使用され、`previous_prompt` (NovelAI) / Vision LLM 分析 (非 NovelAI) のベースになることを確認する（E2E テスト T026 でも部分的に検証）

**チェックポイント**: 行動画像が履歴に保存され、連続行動時に前回の行動画像がベースとして使用される

---

## フェーズ 6: テスト

**目的**: ユニットテストと E2E テストによる品質保証

- [x] T017 [P] [US3] backend/tests/unit/test_action_prompts.py に `get_action_image_edit_system_prompt()` のテストを追加。NovelAI SFW/NSFW、Qwen SFW/NSFW の 4パターンで正しいテンプレートが返されることを検証する
- [x] T018 [P] [US4] backend/tests/unit/test_action_prompts.py に `build_action_image_edit_prompt()` のテストを追加。instruction と current_description が正しくプロンプトに埋め込まれることを検証する
- [x] T019 [P] [US3] backend/tests/unit/test_action_prompts.py に `get_action_novelai_prompt_generation_system()` のテストを追加。SFW/NSFW で正しいシステムプロンプトが返されることを検証する
- [x] T020 [P] [US1] backend/tests/unit/test_action_prompts.py に全テンプレートの「人物保持」制約文言検証テストを追加。全プロンプトテンプレートに人物外見保持の指示が含まれることを確認する
- [ ] T025 [US1] [US3] [US4] backend/gateway/services/game_service.py の action mode が self_mode 有効時にも正しく動作することを手動テストで検証。self_profile の性格がテキストプロンプトに反映され、画像生成ロジックは通常モードと同一であることを確認する (FR-012)
- [ ] T026 frontend/tests/e2e/ に Playwright E2E テストを追加。行動モードで画像が SSE ストリームで表示されること、変身回数が変化しないことを検証する (Constitution II)

**チェックポイント**: 全ユニットテストがパスし、Playwright E2E テストで行動モードの画像表示と変身回数不変が検証された

---

## フェーズ 7: 仕上げと横断的な関心事

**目的**: コード品質と統合確認

- [x] T021 backend/ で `uv run ruff check .` を実行し lint エラーゼロを確認
- [x] T022 backend/ で `uv run python -m pytest -v` を実行し全テストパスを確認
- [x] T023 frontend/ で `npx eslint .` を実行し lint エラーゼロを確認 (フロントエンド変更がない場合でも回帰確認)
- [ ] T024 quickstart.md の検証手順を実行し、行動モードの画像生成が正常に動作することを確認

---

## 依存関係と実行順序

### フェーズ間の依存関係

- **フェーズ 1 (セットアップ)**: 不要 — 既存プロジェクト
- **フェーズ 2 (基盤)**: 依存関係なし — すぐに開始可能。T001/T002/T003 は並列実行可能
- **フェーズ 3 (US1+2+3+4基盤)**: フェーズ 2 完了に依存 — プロンプトテンプレートが必要
- **フェーズ 4 (フォールバック)**: フェーズ 3 の T009/T011 完了に依存 — 画像生成パイプラインの基本実装が必要
- **フェーズ 5 (US5)**: フェーズ 3 の T013 完了に依存 — 履歴保存の基本実装が必要
- **フェーズ 6 (テスト)**: ユニットテスト (T017-T020) はフェーズ 2 完了後に開始可能。E2E テスト (T026) はフェーズ 3 完了 + サーバー起動が必要。self_mode テスト (T025) はフェーズ 3 完了に依存
- **フェーズ 7 (仕上げ)**: 全フェーズ完了に依存

### ユーザーストーリーの依存関係

- **US1 (変身後行動)**: フェーズ 2 基盤完了後に T007-T014 で実装
- **US2 (初期状態行動)**: US1 と同一タスクで実装 (同じコードパス)
- **US3 (NovelAI)**: フェーズ 2 の T001/T003/T006 + フェーズ 3 の T008 で実装
- **US4 (非 NovelAI)**: フェーズ 2 の T002/T004/T005 + フェーズ 3 の T009 + フェーズ 4 の T015 で実装
- **US5 (履歴管理)**: フェーズ 3 の T013 + フェーズ 5 の T016 で実装
- **FR-012 (self_mode)**: フェーズ 6 の T025 で検証

### 並列化の機会

```
# フェーズ 2: T001, T002, T003 は全て並列実行可能 (同一ファイル内だが独立したテンプレート定義)
T001: NovelAI タグ形式テンプレート
T002: Qwen Image Edit テンプレート
T003: GLM-4.6 タグ生成テンプレート

# フェーズ 6: T017, T018, T019, T020 は全て並列実行可能 (ユニットテスト)
T017: get_action_image_edit_system_prompt テスト
T018: build_action_image_edit_prompt テスト
T019: get_action_novelai_prompt_generation_system テスト
T020: 人物保持制約テスト
# T025 (self_mode) と T026 (E2E) はフェーズ 3 完了後に実行
```

### plan.md / tasks.md フェーズ対応表

| plan.md | tasks.md     | 内容                                         |
| ------- | ------------ | -------------------------------------------- |
| Phase A | フェーズ 2   | プロンプトテンプレート (action_prompts.py)   |
| Phase B | フェーズ 3-5 | game_service.py 改修 + フォールバック + 履歴 |
| Phase C | フェーズ 6   | テスト (ユニット + E2E + self_mode)          |
| Phase D | フェーズ 7   | 品質チェック (Lint/Test/検証)                |

---

## 実装戦略

### MVPファースト (US1+US2+US3)

1. フェーズ 2: 基盤プロンプトテンプレート (T001-T006) を完了
2. フェーズ 3: 画像生成パイプライン (T007-T014) を完了
3. **停止して検証**: NovelAI モードで行動→画像生成が動作するか確認
4. フェーズ 6: ユニットテスト (T017-T020) + self_mode 検証 (T025) + E2E テスト (T026) を追加
5. フェーズ 7: 品質チェック (T021-T024) を実行

### 増分デリバリー

1. 基盤 + US1+2+3 → NovelAI モードで動作確認 (MVP)
2. US4 追加 → 非 NovelAI モードで動作確認
3. US5 追加 → 連続行動の履歴確認
4. テスト + 仕上げ → 品質保証

---

## メモ

- フロントエンド変更なし — SSE の `image` イベントは既にハンドリング済み
- DB マイグレーション不要 — 既存の PersistedHistory テーブルで完全に対応
- 新規 API エンドポイント不要 — 既存の `/game/play/stream` + `instruction_type=action`
- i2i_strength 0.85 は実測ベースの初期値 (R-001: 0.45 では背景変化が発生しないことを確認済み)。人物細部への影響はキャラクタータグ `{}` 強調で緩和
- [P] タスク = 別ファイルまたは独立した定義、依存関係なし
- [Story] ラベルはトレーサビリティのためにタスクをユーザーストーリーに紐付け
- 各チェックポイントで停止し、独立して検証可能
