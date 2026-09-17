# Live2D Cubism Core の配置先

このディレクトリには Live2D Cubism Core を配置します。Cubism Core は Live2D
Proprietary Software License の配布物のため、このリポジトリには含めていません。
Live2D 表示を使うときは、各自でダウンロードして配置してください。

## 手順

1. [Cubism SDK for Web](https://www.live2d.com/sdk/download/web/) をダウンロードする。
2. ZIP 内の `Core/live2dcubismcore.min.js` を取り出す。
3. 次の場所へ置く。
   - ソースから起動する場合: `frontend/public/live2d/vendor/`
   - 配布パッケージの場合: `backend/static/live2d/vendor/`
4. アプリを再起動し、ブラウザを再読み込みする。

配置しない場合、Live2D の表示は選択できず、2D 立ち絵が使われます。アプリの他の
機能には影響しません。ビルドも通ります。SDK に付属する型定義ファイル
(`live2dcubismcore.d.ts`) は、このリポジトリには同梱も転記もしていません。Core は
型を持たない外部スクリプトとして扱い、境界は
`frontend/src/components/characterChat/live2d/cubismPilotRenderer.ts` の
`CubismCore` 別名 1 箇所に閉じています。

## ライセンス

Cubism Core の利用条件は
[Live2D Proprietary Software 使用許諾契約書](https://www.live2d.com/eula/live2d-proprietary-software-license-agreement_jp.html)
に従います。ZIP に同梱される `LICENSE.md` と `RedistributableFiles.txt` も併せて
確認してください。
