# TURZX v3.9.1：天気APIの選択機能

V3.9.0の天気・乗換表示レイアウトを維持し、WeatherAPI.com／Open-Meteoを切り替える機能を追加しました。

## 使い方

1. [WeatherAPI.com](https://www.weatherapi.com/signup.aspx) で無料アカウントを作成し、APIキーを取得します。
2. TURZXの設定画面で「天気API取得元」→ `WeatherAPI.com` を選択します。
3. 「WeatherAPI.com APIキー」の伏せ字入力欄にキーを入力します。
4. 地域・緯度経度・更新間隔は既存の設定を利用します。
5. 「天気APIテスト」でWeatherAPIの応答を確認してから、「設定を即時反映」を押します。

Open-Meteoを選ぶ場合、APIキーは不要です。以前の気象データを無断でバックアップ先へ切り替えることはしません。APIが取得できない場合は、その状態を画面やログで判別できるようにします。

## 表示と判定

- WeatherAPIの `current.condition.code` から日本語の短い天候名と既存のアイコン分類を決定します。
- **降水量 `current.precip_mm` は天候判定の補正に使用しません。** 天候コードが晴れなら、降水量が多い場合でも晴れ系のまま表示します。
- `forecast.forecastday[0].day` の最高／最低気温と `daily_chance_of_rain`（**当日の降水確率**）を利用します。降水確率は現在降っている雨の割合ではありません。
- `current.wind_kph` はm/sに変換します。
- 天気APIテストでは、データ時刻と現在降水量を確認できます。
- 天気の取得先を変更しても、乗換・NTP時計・USB送信・レイアウト編集・既存GitHub自動更新は維持します。

## 設定・APIキーの保存

保存先は従来どおり `%LOCALAPPDATA%\TURZXDashboard\settings.json` です。WeatherAPIキーはWindows設定画面で伏せ字表示されますが、**設定ファイルには暗号化されず保存されます。** GitHub Actionsのビルドにはキーを必要とせず、GitHubリポジトリにはキーを登録しません。設定ファイルを他者へ共有したりGitHubに登録したりしないでください。

## トラブルシューティング

- 「キー未設定」: WeatherAPI.comでキーを発行し、設定画面に入力してください。
- 「APIキーが無効」: キーの内容と有効状態を確認してください。
- 「利用回数上限」: WeatherAPIの利用枠を確認してください。
- 「取得失敗」: ログ `%LOCALAPPDATA%\TURZXDashboard\logs\dashboard.log` を確認してください。
- 実際の雨と違う: APIの現在天候コード／気象データ時刻と、当日の降水確率を区別してください。降水量による天候補正は無効です。

## 検証
`python -X utf8 -m unittest discover -v -p "tests_*.py"`

GitHub Windowsビルド後も、実機でAPIキー入力、APIテスト、天候描画が正常か確認してください。
