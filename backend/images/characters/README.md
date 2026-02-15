# キャラクター画像ディレクトリ

このディレクトリには、ゲームで使用するキャラクター画像を配置します。

## ファイル形式

- PNG または JPEG 形式
- 推奨サイズ: 512x512 〜 1024x1024 px
- ファイル名: `{id}.png` (例: `char1.png`, `char2.png`)

## キャラクター定義

各キャラクターには対応する設定ファイル `characters.json` が必要です:

```json
[
  {
    "id": "char1",
    "name": "主人公A",
    "image_path": "images/characters/char1.png",
    "description": "普通の男の子",
    "pronoun": "僕",
    "personality": "素直で恥ずかしがり屋"
  }
]
```
