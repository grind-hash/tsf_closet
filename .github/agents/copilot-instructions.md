# TSF Closet 開発ガイドライン

## アクティブな技術

- **バックエンド**: Python 3.12, FastAPI, SQLAlchemy (async), aiosqlite, Alembic, sse-starlette
- **フロントエンド**: React 19 + TypeScript, Vite, React Router
- **データベース**: SQLite (backend/data)
- **外部API**: NovelAI, ComfyUI (画像生成), LiteLLM Proxy (LLaVA/LLM), Ollama

## プロジェクト構造

```text
backend/
└── gateway/
	├── app.py          # FastAPIアプリ
	├── game.py         # APIエンドポイント
	├── game_service.py # ゲームロジック
	├── database.py     # DB接続・スキーマ
	├── models.py       # データモデル
	├── session.py      # セッション管理
	└── ...

frontend/
└── src/
	├── components/     # 画面コンポーネント
	├── routes/         # ルーティング
	├── apis/           # APIクライアント
	└── ...
```

## コマンド

```bash
# バックエンド起動 (FastAPI)
uv run uvicorn gateway.app:app --host 0.0.0.0 --port 8000 --reload

# バックエンド起動 (ランチャー)
uv run python launcher.py --workflow workflows/instruct_game_template.json --port 8000

# フロントエンド起動
npm run dev

# 開発時のアクセス先
# フロントエンド: http://localhost:3000
# バックエンド: http://localhost:8000 (Vite proxy: /api, /history, /health, /novelai)

# リント/フォーマット
ruff check backend/gateway/
ruff format backend/gateway/

# フロントエンドリント
npm run lint
```

## コードスタイル

- Python: Ruff (pyproject.tomlで設定)
- 型ヒント必須
- Pydanticモデルでバリデーション
- React + TypeScript (TSX) を優先

## ゲームパラメータシステム (002-tsf-game-progression)

- 開花度 (0-100): 変身の累積効果
- 羞恥心 (0-100): 心理負荷
- 順応度 (-50〜+50): 受容/抵抗傾向

### 臨界点閾値

- 25: 第一臨界点
- 50: 第二臨界点
- 75: 第三臨界点
- 100: 最終臨界点

### 変身タグ3軸

- costume_category: 衣装カテゴリ
- exposure_level: 露出度 (high/medium/low)
- age_impression: 年齢印象
