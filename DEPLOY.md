# Life Quest - スマホで使う方法（Streamlit Cloud）

## 1. GitHubにコードをアップロード

### 1-1. GitHubアカウント作成
- https://github.com にアクセス
- アカウント作成（無料）

### 1-2. リポジトリ作成
1. GitHubにログイン
2. 右上の「+」→「New repository」
3. リポジトリ名: `life-quest`（任意）
4. Public を選択
5. 「Create repository」をクリック

### 1-3. コードをアップロード
**方法A: GitHub Desktop（簡単）**
1. https://desktop.github.com から GitHub Desktop をダウンロード・インストール
2. GitHub Desktop を開く
3. 「File」→「Add Local Repository」
4. `C:\Users\takut\OneDrive\Desktop\life_quest` を選択
5. 「Publish repository」をクリック

**方法B: Gitコマンド（上級者向け）**
```bash
cd C:\Users\takut\OneDrive\Desktop\life_quest
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/あなたのユーザー名/life-quest.git
git push -u origin main
```

## 2. Streamlit Cloudにデプロイ

### 2-1. Streamlit Cloudにアクセス
- https://share.streamlit.io にアクセス
- 「Sign in with GitHub」で GitHub アカウントでログイン

### 2-2. アプリをデプロイ
1. 「New app」をクリック
2. **Repository**: `あなたのユーザー名/life-quest` を選択
3. **Branch**: `main` を選択
4. **Main file path**: `app.py` を入力
5. **Advanced settings** を開く:
   - **Secrets**: 以下の形式で追加
     ```toml
     [gcp_service_account]
     type = "service_account"
     project_id = "your-project-id"
     private_key_id = "your-private-key-id"
     private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
     client_email = "your-service-account@your-project.iam.gserviceaccount.com"
     client_id = "your-client-id"
     auth_uri = "https://accounts.google.com/o/oauth2/auth"
     token_uri = "https://oauth2.googleapis.com/token"
     auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
     client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
     
     [sheets]
     url = "https://docs.google.com/spreadsheets/d/..."
     ```
   - この内容は `.streamlit/secrets.toml` からコピーしてください
6. 「Deploy!」をクリック

### 2-3. 完了！
- 数分待つと、`https://あなたのアプリ名.streamlit.app` というURLが生成されます
- このURLをスマホのブラウザで開けば使えます！

## 3. スマホでアクセス

1. スマホのブラウザ（Safari / Chrome）を開く
2. Streamlit Cloudで表示されたURLを入力
3. ホーム画面に追加（iOS: 共有→ホーム画面に追加 / Android: メニュー→ホーム画面に追加）

## 4. コード更新方法

1. ローカルで `app.py` を編集
2. GitHub Desktop で「Commit」→「Push origin」
3. Streamlit Cloud が自動で再デプロイ（数分かかります）

---

## 注意事項

- **secrets.toml は GitHub にアップロードしないでください！**
  - `.gitignore` に `.streamlit/secrets.toml` を追加しておくこと
  - Streamlit Cloud の Secrets に直接入力してください

- **スプレッドシートの共有設定**
  - Google スプレッドシートをサービスアカウントのメールアドレスに「編集者」として共有してください
