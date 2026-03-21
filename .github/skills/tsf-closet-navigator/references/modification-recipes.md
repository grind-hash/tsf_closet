# 変更レシピ集

> 最終検証: 2026-03-22 | 更新条件: 新しい変更パターンの発見やファイル構成の変更時

クイックルックアップ: 「〇〇をしたい」→「このファイルを読む/変更する」

## バックエンドレシピ

### 新しい API エンドポイントの追加

| 手順 | 操作                                | ファイル                                           |
| ---- | ----------------------------------- | -------------------------------------------------- |
| 1    | Pydantic リクエスト/レスポンス定義   | `backend/gateway/models.py`                        |
| 2    | ルートハンドラの追加                 | `backend/gateway/routes/{router}.py`               |
| 3    | （新規ルーターの場合）アプリに登録   | `backend/gateway/app.py`                           |
| 4    | ビジネスロジックの追加               | `backend/gateway/services/{service}.py`            |
| 5    | （DB必要時）モデル追加               | `backend/gateway/databases/models.py`              |
| 6    | （DB必要時）マイグレーション作成     | `uv run alembic revision --autogenerate -m "desc"` |

### ゲームプレイロジックの変更（変身パイプライン）

| 優先度 | 読むべきファイル                                                        |
| ------ | ----------------------------------------------------------------------- |
| コア   | `backend/gateway/services/game_service.py` (play_with_stream)           |
| LLM    | `backend/gateway/services/llm_service.py`                               |
| 画像   | `backend/gateway/services/image_generation.py`                          |
| プロンプト | `backend/gateway/services/action_prompts.py` or `reality_prompts.py`|
| ステータス | `backend/gateway/services/game_service.py` (ステータス計算部分)      |

### 実績の追加/変更

| ファイル                                             | 目的                    |
| ---------------------------------------------------- | ----------------------- |
| `backend/gateway/services/achievement_service.py`    | 解除条件                 |
| `backend/gateway/services/achievement_classifier.py` | カテゴリ分類             |
| `backend/gateway/databases/models.py`                | Achievement/AchievedEnding モデル |

### エンディング条件の変更

| ファイル                                      | 目的                          |
| --------------------------------------------- | ----------------------------- |
| `backend/gateway/services/summary_service.py` | エンディング評価ロジック       |
| `backend/gateway/services/summary_prompts.py` | エンディングプロンプトテンプレート |
| `backend/gateway/services/endings.py`         | エンディング定義               |

### LLM プロンプトの変更

| プロンプト種別       | ファイル                                        |
| -------------------- | ----------------------------------------------- |
| 着せ替え指示         | `backend/gateway/services/action_prompts.py`    |
| 現実改変             | `backend/gateway/services/reality_prompts.py`   |
| セルフモード         | `backend/gateway/services/self_mode_prompts.py` |
| サマリー/エンディング | `backend/gateway/services/summary_prompts.py`   |
| 共通ユーティリティ   | `backend/gateway/services/prompts.py`           |

### 新しい DB テーブルの追加

| 手順 | 操作                       | ファイル                                                    |
| ---- | -------------------------- | ----------------------------------------------------------- |
| 1    | SQLAlchemy モデル定義       | `backend/gateway/databases/models.py`                       |
| 2    | マイグレーション生成        | `uv run alembic revision --autogenerate -m "add_tablename"` |
| 3    | マイグレーション適用        | `uv run alembic upgrade head`                               |

## フロントエンドレシピ

### 新しいページ/画面の追加

| 手順 | 操作             | ファイル                                                |
| ---- | ---------------- | ------------------------------------------------------- |
| 1    | コンポーネント作成 | `frontend/src/components/{feature}/FeatureScreen.tsx`   |
| 2    | ルート追加        | `frontend/src/App.tsx` (パスのスイッチ)                  |
| 3    | ナビリンク追加    | `frontend/src/components/layout/SideMenu.tsx`           |
| 4    | i18n キー追加     | `frontend/src/assets/` (ロケール JSON ファイル)          |

### 共有状態の追加

| 手順 | 操作                                    | ファイル                                  |
| ---- | --------------------------------------- | ----------------------------------------- |
| 1    | 既存の Context に収まるか確認            | SKILL.md の Context 表を参照              |
| 2a   | 既存 Context に追加                      | `frontend/src/contexts/{Context}.tsx`     |
| 2b   | （新規 Context の場合）新規作成          | `frontend/src/contexts/NewContext.tsx`    |
| 3    | （新規 Context の場合）プロバイダでラップ | `frontend/src/main.tsx` or `App.tsx`      |

### ゲーム UI（メインプレイ画面）の変更

| ファイル                                         | 目的                             |
| ------------------------------------------------ | -------------------------------- |
| `frontend/src/components/GamePlayScreen.tsx`     | メインゲーム画面レイアウト        |
| `frontend/src/components/chat/ChatMessageList.tsx` | チャットメッセージ一覧          |
| `frontend/src/components/chat/ChatInput.tsx`     | ユーザー入力 + 指示タイプ選択     |
| `frontend/src/components/chat/ChatMessage.tsx`   | メッセージ単体表示 / 削除・編集UI |
| `frontend/src/components/ParameterBars.tsx`      | ステータス表示                    |
| `frontend/src/components/HistoryPanel.tsx`       | 履歴サイドバー                    |
| `frontend/src/components/layout/MainLayout.tsx`  | 2カラムレイアウトフレーム         |
| `frontend/src/components/layout/RightPanel.tsx`  | 右サイドバー                      |

補足: `ChatContainer.tsx` は現状のメイン導線では使われておらず、チャット領域の実装主体は `GamePlayScreen.tsx` です。

### メッセージ削除 / 履歴削除の変更

| レイヤー | ファイル                                         | 目的                                      |
| -------- | ------------------------------------------------ | ----------------------------------------- |
| FE UI    | `frontend/src/components/GamePlayScreen.tsx`     | 削除確認ダイアログ、削除後の画面同期       |
| FE UI    | `frontend/src/components/chat/ChatMessage.tsx`   | 削除ボタンの表示条件                      |
| FE API   | `frontend/src/apis/game.ts`                      | `deleteHistoryEntry`, `deleteLatestHistory` |
| FE State | `frontend/src/contexts/GameContext.tsx`          | 履歴削除後の `history/currentImage` 更新   |
| FE State | `frontend/src/contexts/ChatContext.tsx`          | メッセージID / `relatedHistoryId` 解決     |
| BE Route | `backend/gateway/routes/game_router.py`          | `/game/history/{history_id}` などの削除API |
| BE Logic | `backend/gateway/services/session.py`            | 履歴・画像・会話の実削除処理              |

### フロントエンドから API 呼び出しの追加

| 手順 | 操作                              | ファイル                                             |
| ---- | --------------------------------- | ---------------------------------------------------- |
| 1    | 関数を追加                         | `frontend/src/apis/{module}.ts`                      |
| 2    | （新しい型が必要な場合）型を定義    | `frontend/src/types/index.ts`                        |
| 3    | Hook または Context アクションから呼出 | `frontend/src/hooks/` or `frontend/src/contexts/` |

### SSE イベントハンドリングの変更

| ファイル                                     | 目的                                                 |
| -------------------------------------------- | ---------------------------------------------------- |
| `frontend/src/hooks/useSSE.ts`               | SSE イベント解析 + コールバック                        |
| `frontend/src/components/GamePlayScreen.tsx` | コールバックの接続                                    |
| 受信側 Context                               | `GameContext` / `ChatContext` / `NotificationContext` |

### i18n 翻訳の追加

| 手順 | ファイル                                                   |
| ---- | ---------------------------------------------------------- |
| 1    | `frontend/src/assets/` のロケール JSON にキーを追加         |
| 2    | コンポーネントで `useTranslation()` Hook or `t()` 関数を使用 |
| 3    | 設定は `frontend/src/i18n.ts`                               |

## フルスタックレシピ

### 新機能のエンドツーエンド実装

| レイヤー    | 手順                        | ファイル                                  |
| ----------- | --------------------------- | ----------------------------------------- |
| バックエンド | 1. Pydantic モデル          | `backend/gateway/models.py`               |
| バックエンド | 2. サービスロジック          | `backend/gateway/services/new_service.py` |
| バックエンド | 3. ルート                    | `backend/gateway/routes/{router}.py`      |
| バックエンド | 4. （DB必要時）モデル + マイグレーション | `databases/models.py` + Alembic |
| フロントエンド | 5. 型定義                  | `frontend/src/types/index.ts`             |
| フロントエンド | 6. API クライアント        | `frontend/src/apis/{module}.ts`           |
| フロントエンド | 7. Hook または Context アクション | `hooks/` or `contexts/`            |
| フロントエンド | 8. UI コンポーネント       | `components/{feature}/`                   |
| フロントエンド | 9. ルート（ページの場合）  | `App.tsx`                                 |
| フロントエンド | 10. i18n                   | ロケールファイル                           |
| テスト       | 11. E2E (Playwright)       | `frontend/tests/e2e/`                     |

### SSE イベントタイプの追加

| レイヤー      | 手順                              | ファイル                                     |
| ------------- | --------------------------------- | -------------------------------------------- |
| バックエンド   | 1. game_service でイベントを送出   | `backend/gateway/services/game_service.py`   |
| フロントエンド | 2. コールバック型の追加            | `frontend/src/hooks/useSSE.ts`               |
| フロントエンド | 3. コールバックの接続              | `frontend/src/components/GamePlayScreen.tsx` |
| フロントエンド | 4. Context で処理                  | 該当する Context ファイル                     |
