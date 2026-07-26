# Frontend (React + TypeScript + Vite)

## 開発

```bash
npm run dev
```

## Lint / Format

Linter / Formatter は **Biome** を利用します。Markdown のみ **Prettier** です。

```bash
# Lint + format チェック
npm run lint

# Lint + format の自動修正（safe fixes）
npm run lint:fix

# Format のみ
npm run format

# Markdown の format
npm run format:md
npm run format:md:check
```

設定ファイル:

- `biome.json` … JS/TS/CSS/JSON などの lint / format
- `.prettierrc` … Markdown 専用 format

## テスト

```bash
npm run e2e:test
```
