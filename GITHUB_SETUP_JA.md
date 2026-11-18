# TURZX 3.5 GitHub リポジトリ初期セットアップ（V3.6.2）

## リポジトリ作成

1. https://github.com/new を開く。
2. Repository name: `turzx-3p5-dashboard`
3. Visibility: Public（更新の匿名取得を前提）。ソースは公開される点に注意。
4. Add a README file: OFF（アップロード時に入れる）。Create repository。
5. GitHub の `uploading an existing file` から、このZIPを**展開したフォルダの中身をすべて**登録。
   ZIPそのものをそのままアップロードしてもワークフローは動きません。
6. `.github/workflows/build-release.yml` が Code タブで表示されることを確認。
7. Settings → Actions → General → Workflow permissions で `Read and write permissions` を有効化。
   ワークフロー側も `permissions: contents: write` を要求します。
8. Actions → Build and publish TURZX Windows EXE → Run workflow → Run workflow。
9. 完了後 Releases に v3.6.2 と2ファイルが公開されます。
   - `TURZX_3p5_Dashboard.exe`
   - `TURZX_Update_v3.6.2.zip`

## 次バージョンを作る

1. 修正したPythonソースを更新する。
2. `version_info.py` の `APP_VERSION` を変更（例: `3.7.0`）。
3. `.github/workflows/build-release.yml` は基本的にそのまま。
4. Actions で Run workflowを押すと新バージョンのReleasesへ公開されます。
5. 同じバージョン番号で再実行すると、既存Releaseの上書きを避けるため失敗します。

## EXEからのGitHub自動更新

現行 **V3.6.2** にある更新機能は**手動選択したZIP**を適用するものです。
GitHub Releasesへ自動アクセスして最新バージョンを取得する処理は**まだ含まれていません**。
GitHubリポジトリ作成後、リポジトリURLを使用して次の機能を新バージョンへ実装してください。

- `GET https://api.github.com/repos/OWNER/turzx-3p5-dashboard/releases/latest`
- 現在のAPP_VERSIONとtag_nameを比較
- Release assetsの指定ZIPをHTTPSで取得（上限・サイズ・SHA256を検証）
- 既存 `update_manager.py` の署名なし整合性検証・停止・バックアップ・置換処理を流用
- 新版EXEを一度手動で導入すると以後はアプリ内更新を利用可能

**セキュリティ**：APIレスポンスのハッシュとZIP同梱manifestのハッシュは内容破損の検出に使えますが、作者の電子署名の代わりにはなりません。HTTPSで公式GitHubリポジトリ固定、公開キーによる更新署名の導入も推奨します。

## 注意

- Public repositoryにアップロードしたソースやschedule.jsonは一般公開されます。私物のAPIキー、`settings.json`、履歴やログ、認証情報をアップロードしないでください。
- `.github/workflows/build-release.yml` はビルド時にPython依存パッケージをダウンロードします。
- コードのライセンスについては既存 `LICENSE-GPL3.txt` を確認してください。
- GitHub上での実行・WindowsでのEXE実行はこのキット作成時点では未検証です。
