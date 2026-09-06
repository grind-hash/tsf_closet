# キャラチャットの同梱立ち絵

拠点キャラ「セレナ」の立ち絵をこのディレクトリに `serena.png` として置く。
画像はキャラチャット画面の左ペインにそのまま表示され、着替えを頼んだときの
編集元（参照画像）にもなる。

ファイルが無い場合、画面には配置先の案内と「立ち絵を生成」ボタンが出て、
`backend/gateway/consts/character_chat.py` の外見タグ（`BASE_IDENTITY_TAGS` /
`BASE_CLOTHING_TAGS`）から画像生成できる。
