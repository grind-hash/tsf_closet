# リサーチ: 行動モード画像生成

**機能**: 002-action-scene-image  
**日付**: 2026-02-21

## R-001: NovelAI img2img — 背景のみ変更時の i2i_strength

### 判定: 背景を実際に変更するには Strength 0.80〜0.90 が必要。低値では元画像がほぼそのまま再現される

- **0.50 以下**: 背景変更がほぼ効かない。元画像と実質的に同一の出力になる（実測済み: 0.45 でカフェ背景プロンプトを適用しても変化なし）
- **0.50〜0.70**: 背景に微小な変化が出るが、場面移動としては不十分
- **0.80〜0.90**: 背景に明確な変化が現れる。人物の大まかな構図・ポーズは維持されるが、細部（衣装ディテール、目の色等）に影響が出る可能性あり
- **0.90 以上**: 背景変更は大きいが、キャラクター自体も大幅に変わるリスク

### 根拠

- **実測 (2026-02-21)**: i2i_strength 0.45 で "1boy in the cafe, background cafe" プロンプトを適用した結果、元画像とほぼ同一の出力。背景の変化は識別不可能
- **実測 (2026-02-21)**: i2i_strength 0.85 程度で背景が明確に変化することを確認
- NovelAI 公式ドキュメント: "Higher Strength values allow the AI free rein to reinterpret the image"
- NovelAI の i2i_strength の低値は「元画像を強く保持」するため、背景変更を目的とする場合には逆効果
- img2img は画像全体に一律適用されるため、前景/背景の選択的制御は構造上不可能

### 重要な知見

- NovelAI の i2i_strength では、低い値 = 元画像からほとんど変わらない。背景のみ変更という目的で低値にすると、そもそも変更が反映されない
- 高い strength (0.85) では背景が変わる反面、人物の細部にも影響が出る。これは img2img の構造的限界であり、プロンプト側でキャラクタータグを `{}` で強調することで緩和を図る

### 検討した代替案

- Inpainting (マスク反転) → R-002 で詳述
- Qwen Image Edit (命令ベース) → R-003 で詳述

---

## R-002: Inpainting (マスク反転) によるキャラクター保護

### 判定: Inpainting が背景変更の最も確実な手法だが、マスク生成の追加コストがある

**利点:**

- マスク外の領域は完全保護 (NovelAI 公式: "Anything that is not marked by the Mask, will remain the same")
- Inpainting Strength を高く (0.7〜1.0) 設定しても、マスク外のキャラクターに影響なし
- 背景の大幅な変更が可能

**課題:**

- キャラクターのセグメンテーションマスク生成が必要 (rembg, SAM 等)
- マスク境界のアーティファクト (ピクセル漏れ) リスク
- 新規ライブラリの導入・計算コスト

### 本プロジェクトでの判断: Phase 1 では導入しない

理由:

1. 新規セグメンテーションライブラリの導入は Constitution Principle I (公式ドキュメント照合) の追加検証が必要
2. 現在の既存パイプラインは img2img ベースで動作しており、マスク生成をフローに追加する工数が大きい
3. img2img + プロンプト制御で「十分に許容可能な品質」(SC-002: 90%以上) を先に検証し、不足であれば Phase 2 で Inpainting を追加する段階的アプローチが適切

---

## R-003: Qwen Image Edit の背景変更プロンプトパターン

### 判定: 命令ベース編集により「背景だけ変更」が自然言語で指示可能

**推奨プロンプトパターン:**

```
Change the background to [具体的な背景描写] while keeping the person exactly as they are.
```

**性能指標 (evolink.ai レビュー):**

- アイデンティティ保持率: 91.7%
- 背景一貫性: 89.6%

**本プロジェクトでの適用:**

- 非 NovelAI モード (ComfyUI + Qwen Image Edit) ではこのパターンを直接使用
- `change_scope: "background_only"` パラメータで image_edit テンプレートを切り替え

---

## R-004: 既存パイプラインの行動モード統合方式

### 判定: action mode の早期 return を削除し、通常パイプラインに「scene-only」分岐を追加

**現在のフロー:**

1. `instruction_type == "action"` → テキスト生成のみ → 早期 return
2. 通常パイプライン → describe → edit prompt → image + text 並列生成

**修正後のフロー:**

1. `instruction_type == "action"` → テキスト生成 + **画像生成** → 完了
2. 画像生成はe通常パイプラインと同じ関数を使用するが、プロンプト生成部分で「場面変更専用」テンプレートを使用
3. 変身回数・パラメータ更新・タグ分類・エンディング判定は**スキップ**

**根拠:**

- 最小限の変更で既存パイプラインを活用
- 新規 API エンドポイント不要 (既存の `/game/play/stream` に `instruction_type=action` で統合)
- フロントエンドは既に SSE の `image` イベントをハンドリング可能

---

## R-005: NovelAI Opus での行動画像プロンプト生成戦略

### 判定: 既存の GLM-4.6 タグ生成を利用し、専用システムプロンプトで「人物タグ維持 + 背景タグ変更」を指示

**方式:**

1. `previous_prompt` (前回タグ) からキャラクタータグを継承
2. `character_base_tags` はそのまま使用
3. 新しい専用システムプロンプトで「キャラクタータグは `{}` で強調して維持、背景タグのみ変更」を指示
4. `instruction` は場面移動の自然言語指示 (例: "カフェに行く")

**i2i_strength の推奨:**

- 行動モード専用のデフォルト値: 0.85 (背景変更を実現するために高めの値が必要 — R-001 実測結果に基づく)
- フロントエンドから `inpaint_strength` をオーバーライド可能 (既存の仕組み)
- 人物の細部変化を抑えるため、キャラクタータグを `{}` で強調するプロンプト戦略を併用

### 根拠

- 既存の `generate_novelai_image_prompt()` を再利用し、システムプロンプトのみ差し替え
- `previous_prompt` がコンテキストとして使えるため、キャラクター一貫性が高い
- NovelAI 公式推奨: キャラクタータグを `{}` で強化して一貫性確保

---

## R-006: 非 NovelAI (Vision LLM) での行動画像プロンプト生成戦略

### 判定: Vision LLM で現在画像を分析 → 専用テンプレートで「背景変更のみ」の編集プロンプトを生成

**方式:**

1. `_describe_image()` で現在の画像をVision LLMで分析 (人物の詳細記述を取得)
2. 新しい `build_action_edit_prompt()` で「人物記述をそのまま保持、背景のみ {instruction} に変更」という編集プロンプトを生成
3. Qwen Image Edit に渡す

**プロンプト構造:**

```
Current image description: {current_description}
Change the background/scene to: {instruction}
Keep the person's appearance (outfit, hair, body, accessories) exactly as described above.
Only change the background, environment, and lighting to match the new scene.
```

### 根拠

- Qwen Image Edit のアイデンティティ保持率 91.7% (R-003)
- 既存の `_describe_image()` + `generate_image_edit_prompt()` の仕組みを活用
- `change_scope` パラメータの追加で通常編集と場面変更編集を区別
