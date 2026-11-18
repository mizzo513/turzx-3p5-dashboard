# Windows EXE生成と更新方法

## 一括生成
`BUILD_EXE_AND_UPDATER_WINDOWS.bat` を実行すると以下を生成します。

- `dist\TURZX_3p5_Dashboard.exe` — 単一ファイル実行形式
- `dist\TURZX_Update_v3.6.1.zip` — 更新用ZIP（manifest.json、EXE、SHA256整合性情報）

`BUILD_ONE_EXE_WINDOWS.bat` でも同じビルダーを起動します。Windows 10/11 x64、Python 3.11～3.14、PyInstallerを使用します。初回はネット接続が必要です。

## 初回導入
旧EXEを終了し、新しいEXEをユーザーフォルダに配置して実行します。`%LOCALAPPDATA%\TURZXDashboard`の設定は維持されます。

## 次回以降の更新
将来のソース版で`APP_VERSION`を更新してから同じビルダーでビルドすると新しい更新ZIPを作れます。V3.6以降のEXEでは設定画面から更新ZIPを選択して適用できます。破損または旧版の更新ZIPは拒否されます。

実行中のEXEはWindowsがロックするため、補助PowerShellが停止を待って置換します。旧EXEは `TURZX_3p5_Dashboard_backup_v3.6.1.exe` 等の名前で保存します（バックアップがある場所は実行EXEと同じフォルダ）。失敗ログは `%LOCALAPPDATA%\TURZXDashboard\updates\updater.log` です。

**セキュリティ**：更新ZIPのSHA256は破損検出用で、配布元の署名検証ではありません。不明なZIPを使用しないでください。

**制約**：実機、Win32 EXEビルド、ファイル置換の実行試験はユーザー側Windowsで必要です。アップデータはEXEモードのみ有効です。データはユーザー領域に保持されるため、真の「一切ファイル不要」とは異なります。
