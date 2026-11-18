# TURZX V3.8.3: GitHub自動更新後の再起動問題を修正

## 修正対象
V3.8.1からV3.8.2へアプリ内更新した直後に発生し得る「Failed to start embedded python interpreter!」。

## 想定原因と修正
PyInstaller onefileアプリの古い起動環境 (`_PYI_*`) がPowerShell更新処理へ継承され、新EXEの独立起動に失敗する可能性への対策。

- `PYINSTALLER_RESET_ENVIRONMENT=1` に設定し、古い `_PYI_*` をPowerShellと新EXEに引き継がない
- EXEを置換する前に、一時配置した新EXEを `--self-test` で起動確認
- 置換後のEXEも再度 `--self-test` で起動確認し、失敗時は旧EXEをバックアップから戻す
- PowerShell更新補助スクリプトのSHA256検証は .NET暗号処理を使用
- Windows Actions環境で環境変数汚染を模擬したEXE置換結合テストを必須化

## 今回の導入方法（重要）
V3.8.2までのアップデーターには上記修正がないため、**V3.8.3への更新は一度だけ手動ダウンロードで行ってください**。

1. GitHub ReleasesのV3.8.3から `TURZX_3p5_Dashboard.exe` をダウンロード
2. 旧TURZXの画面・エンジンを停止
3. 旧EXEを別名バックアップしてから、同名の新EXEを配置
4. EXEをダブルクリックして起動・表示動作を確認
5. 次回バージョンへのアプリ内更新で再起動処理を確認

設定ファイル、天気・列車情報、レイアウト設定は `%LOCALAPPDATA%\TURZXDashboard` に保持されます。

## 診断
更新のログ: `%LOCALAPPDATA%\TURZXDashboard\updates\updater.log`。
Windows Securityの保護履歴で新EXEの実行がブロックされていないかも確認してください。

**注意:** Windows Actions結合テストはリモートのWindows環境であり、ユーザー実機での再起動確認を置き換えるものではありません。
