# GitHub アップロード前チェック

## 絶対にアップロードしてはいけないファイル

| ファイル / フォルダ | 理由 |
|---------------------|------|
| **`.streamlit/secrets.toml`** | GCP の秘密鍵・スプレッドシート URL が入っている。漏れると第三者に悪用される |

`.gitignore` にすでに含まれているので、**「すべてのファイルを追加」する前に、このファイルが一覧に含まれていないか必ず確認**してください。

---

## アップロードしてOKなファイル（例）

- `app.py`
- `requirements.txt`
- `README.md`
- `DEPLOY.md`
- `SPREADSHEET.md`
- `SPREADSHEET_CHECKLIST.md`
- `あなたがやること.md`
- `IMPROVEMENTS.md`
- `ADHD_IMPROVEMENTS.md`
- `発展案_さらに.md`
- `実行方法.md`
- `.gitignore`
- `.streamlit/config.toml`（テーマ設定のみで機密情報なし）

---

## 注意点

1. **コミット前に「変更されるファイル」を確認する**  
   GitHub Desktop や `git status` で、**`secrets.toml` が含まれていないこと**を確認してからコミット。

2. **すでに secrets.toml を push してしまった場合**  
   - そのリポジトリの「サービスアカウントキー」は**無効化し、新しいキーを発行**する  
   - スプレッドシートの共有設定を見直す  
   - リポジトリを **private** にし、必要ならキーをローテーションする  

3. **スマホで見る方法**  
   - **同じ Wi‑Fi のとき**  
     PC で `streamlit run app.py` を実行し、スマホのブラウザで `http://（PCのIP）:8501` を開く（例: `http://192.168.1.10:8501`）。  
   - **どこからでも見たいとき**  
     [Streamlit Community Cloud](https://share.streamlit.io/) などにデプロイする。  
     その場合は **Secrets** に `secrets.toml` の内容を設定する必要があり、Git には上げずにクラウドの画面からだけ入力する。

4. **列の追加はローカルで**  
   スプレッドシートの列（`unlocked_titles` など）は **Google スプレッドシート側で手動追加**。GitHub にはスプレッドシートは含めません。

---

## まとめ

- **上げない:** `.streamlit/secrets.toml` だけは絶対に含めない。
- **上げてよい:** 上記「アップロードしてOK」のファイル・フォルダ。
- **スマホ:** 同じ Wi‑Fi なら PC の IP:8501、外出先からなら Streamlit Cloud などのデプロイを検討。
