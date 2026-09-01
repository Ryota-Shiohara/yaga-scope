# 矢上祭 本部 Live Transcript

本部PCのデフォルトマイクを常時取得し、Silero VADで発話区間を切り出し、faster-whisperで日本語文字起こしを行うMVPです。認識結果とシステム状態をFastAPI + WebSocketで同一LAN上の複数ブラウザへ配信します。

音声取得、VAD、音声認識、WebSocket配信はそれぞれ有界Queueで分離しています。Whisper処理や1台のブラウザが遅延・失敗しても、マイク入力と他クライアントを止めないことを優先しています。文字起こしや音声は保存しません。

## 必要環境

- Python 3.11以上（3.11または3.12を推奨）
- 16 kHz / mono入力に対応するマイク
- 初回セットアップ・モデル取得時のみインターネット接続
- Windows 11、macOS、またはLinux
- GPUは不要（既定値はCPU + INT8）

初回起動時にfaster-whisperのモデルがダウンロードされます。モデルがキャッシュされた後は、インターネットが切れてもLAN内で利用できます。

## セットアップ

PowerShellの例です。

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

Linuxで`PortAudio library not found`が出る場合は、先にPortAudioを導入します。

```bash
sudo apt-get install libportaudio2
```

## マイクデバイスの確認

仮想環境を有効にした状態で実行します。

```powershell
python -m sounddevice
```

先頭に`>`が付く入力デバイスが既定のマイクです。別のデバイスを使う場合は、`.env`の`AUDIO_DEVICE`に一覧の番号または正確なデバイス名を指定してください。

Windowsでは、設定の「プライバシーとセキュリティ > マイク」でデスクトップアプリのマイク利用も許可してください。

## まずコンソールで確認する

Web UIを使う前に、マイク → VAD → Whisperが安定して動くことを確認します。

```powershell
python -m app.console
```

「ステージ担当者お願いします」と発話し、数秒後に次のような表示が出れば音声パイプラインは正常です。

```text
[10:32:14] ステージ担当者お願いします
```

終了は`Ctrl+C`です。

## サーバーを起動する

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

本部PCでは次を開きます。

```text
http://localhost:8000
```

状態確認用エンドポイント:

```text
http://localhost:8000/health
```

## LAN内のブラウザから接続する

本部PCのLAN IPv4アドレスを確認します。

```powershell
ipconfig
```

同じLANに接続した端末から次を開きます。

```text
http://<本部PCのLAN IPv4アドレス>:8000
```

例: `http://192.168.1.20:8000`

Windows Defender Firewallの確認が出たら、会場で使用する「プライベート ネットワーク」だけ許可してください。公共ネットワークへの公開やルーターでのポート開放は不要です。

## 設定一覧

設定は`.env`で変更します。変更後はサーバーを再起動してください。

| 設定 | 既定値 | 説明 |
|---|---:|---|
| `AUDIO_SAMPLE_RATE` | `16000` | 入力サンプルレート（固定） |
| `AUDIO_CHANNELS` | `1` | mono（固定） |
| `AUDIO_BLOCK_SIZE` | `512` | Sileroに渡す1チャンクのサンプル数（固定） |
| `AUDIO_DEVICE` | 未指定 | 入力デバイス番号または名前。未指定は既定マイク |
| `VAD_THRESHOLD` | `0.5` | 発話判定しきい値 |
| `VAD_MIN_SILENCE_MS` | `600` | 発話終了とみなす無音時間 |
| `VAD_SPEECH_PAD_MS` | `250` | 発話開始前後に確保する余白 |
| `VAD_MAX_SPEECH_SECONDS` | `20` | 1発話の最大秒数 |
| `WHISPER_MODEL` | `small` | `tiny` / `base` / `small` / `medium` |
| `WHISPER_DEVICE` | `cpu` | 推論デバイス |
| `WHISPER_COMPUTE_TYPE` | `int8` | 推論精度形式 |
| `WHISPER_LANGUAGE` | `ja` | 認識言語 |
| `WHISPER_BEAM_SIZE` | `1` | Beam size |
| `SOURCE_ID` | `hq_mic` | 配信イベントの音声ソース名 |
| `HOST` | `0.0.0.0` | 待ち受けアドレス（起動コマンドにも指定） |
| `PORT` | `8000` | 待ち受けポート（起動コマンドにも指定） |
| `TIMEZONE` | `Asia/Tokyo` | 発話時刻のタイムゾーン |
| `AUDIO_QUEUE_SIZE` | `256` | 音声Queueの最大チャンク数 |
| `UTTERANCE_QUEUE_SIZE` | `64` | 発話Queueの最大件数 |
| `BROADCAST_QUEUE_SIZE` | `256` | 配信Queueの最大件数 |
| `WEBSOCKET_SEND_TIMEOUT_SECONDS` | `2` | 遅いクライアントの送信タイムアウト |
| `LOG_LEVEL` | `INFO` | Pythonログレベル |

### Whisperモデルの選び方

- 遅延やCPU使用率を下げたい: `tiny`または`base`
- 初期推奨: `small`
- 精度を優先し、処理時間に余裕がある: `medium`

会場と同程度の雑音・マイク位置で、CPU使用率と発話から表示までの時間を計測して選んでください。

## ブラウザ画面の動作

- WebSocket切断後、2秒おきに自動再接続します。
- 新しい発話を受け取ると最下部へ追従します。
- 過去の発話を見るため上へスクロールすると追従を停止します。「最新の発話へ」で再開できます。
- `Mic`、`VAD`、`ASR`は色だけでなく「稼働中」「発話中」「認識中」「エラー」の文字でも状態を示します。
- DOMの継続的な肥大化を防ぐため、1画面に保持する発話は最新1000件までです。サーバー側には保存しません。

## テスト

外部モデルや実マイクを使わない自動テスト:

```powershell
python -m unittest discover -s tests -v
```

または開発依存関係を導入した環境では:

```powershell
pytest
```

本番前には次も手動で確認してください。

1. 短い発話を10回続け、順番に表示されること
2. 3台のブラウザで同じ結果を受信できること
3. 1台を閉じても残りの配信が続くこと
4. Wi-Fiを切断・復帰し、ページ再読み込みなしで再接続すること
5. Whisper認識中も次の発話をQueueに保持できること
6. 30分以上運転し、メモリ、CPU、Queue overflow、音声停止を監視すること

## トラブルシューティング

### `Mic エラー` / 音声デバイスを開けない

- `python -m sounddevice`で入力デバイスが見えるか確認する
- `.env`の`AUDIO_DEVICE`を確認する
- OSのマイク権限を確認する
- マイクを占有する会議アプリや録音アプリを終了する
- 16 kHz入力を受け付けない機器では、OS側のデバイス形式を16 kHzまたは互換形式へ変更する

### `VAD エラー`

- `silero-vad`と`torch`が仮想環境に入っているか確認する
- 初回セットアップ中はモデル取得が完了するまでネット接続を維持する
- 雑音で発話状態が終わらない場合は`VAD_THRESHOLD`を少し上げる
- 語尾が切れる場合は`VAD_MIN_SILENCE_MS`または`VAD_SPEECH_PAD_MS`を増やす

### `ASR エラー` / 初回起動が長い

- 初回はWhisperモデルを取得するため時間がかかる
- CPUやメモリが不足する場合は`WHISPER_MODEL=base`または`tiny`に下げる
- モデル取得後にオフライン動作を確認しておく

### LAN端末から開けない

- サーバーが`--host 0.0.0.0`で起動しているか確認する
- 端末と本部PCが同じLANにいるか確認する
- Windows FirewallでTCP 8000のプライベートネットワーク通信を確認する
- ゲストWi-Fiの「端末間通信を禁止」する設定が有効でないか確認する

### Queue overflowがログに出る

継続的に出る場合は下流処理が入力に追いついていません。まずWhisperモデルを小さくしてください。Queueサイズを増やすだけでは表示遅延が伸びるため、会場運用ではモデル変更を優先します。

## API

- `GET /` — 閲覧画面
- `GET /health` — マイク、VAD、ASR、接続クライアント数
- `WS /ws` — `status` / `transcript`イベント

このMVPには認証、永続化、検索、話者分離、要約、通知、クラウドサービス依存を含めていません。

