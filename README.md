# ⚔️ Life Quest: Recovery

日々のタスクをRPG風のゲームに変換するアプリ。タスクを完了して冒険を進めよう！

## 🎮 特徴

- **RPG風ゲーミフィケーション**: タスク完了でゴールド・経験値・階層が上がる
- **100階層ダンジョン**: 1階から100階まで、階層ごとにミニイベント発生
- **転生システム**: 100階到達で転生して永久ボーナスと称号を獲得
- **ガチャシステム**: N/R/SR/SSR/UR の5段階レアリティ
- **ADHD向け設計**: 小さな成功を重視、ドーパミンが出やすい仕組み
- **モバイル対応**: スマホでも使いやすいレスポンシブデザイン

## 🚀 セットアップ

### 1. 必要なもの

- Python 3.8以上
- Google スプレッドシート（データ保存用）
- Google Cloud Platform サービスアカウント（スプレッドシートアクセス用）

### 2. インストール

```bash
pip install -r requirements.txt
```

### 3. 設定

`.streamlit/secrets.toml` を作成して、以下を設定：

```toml
[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."

[sheets]
url = "https://docs.google.com/spreadsheets/d/..."
```

### 4. 実行

```bash
streamlit run app.py
```

## 📋 スプレッドシート構成

詳細は `SPREADSHEET.md` を参照してください。

## 🌐 デプロイ（スマホで使う）

詳細は `DEPLOY.md` を参照してください。

## 📝 ライセンス

個人利用・学習目的で自由に使用できます。
