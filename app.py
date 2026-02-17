import streamlit as st
import pandas as pd
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid
from datetime import datetime, date, timedelta
import random
import time
import altair as alt

# --- 設定: ページ設定（モバイルでサイドバーは初期非表示） ---
st.set_page_config(page_title="Life Quest: Recovery", page_icon="⚔️", layout="wide", initial_sidebar_state="collapsed")

# --- 画像生成 API (RPG風) ---
def get_avatar_url(seed):
    # 主人公用: RPG風アドベンチャー風
    return f"https://api.dicebear.com/9.x/adventurer/png?seed={seed}&size=96&backgroundColor=2d2d44"

def get_monster_url(seed, rarity="N"):
    # モンスター用: ドット絵RPG風（pixel-artで名前通りに）
    bg = {"N": "94a3b8", "R": "60a5fa", "SR": "a78bfa", "SSR": "f97316", "UR": "fbbf24"}.get(rarity, "94a3b8")
    return f"https://api.dicebear.com/9.x/pixel-art/png?seed={seed}&size=128&backgroundColor={bg}"

# --- マスターデータ ---
TASKS = {
    "🏃 偵察任務 (Walk)": {"reward": 30, "type": "physical", "desc": "周辺調査"},
    "🧹 聖域整地 (Clean)": {"reward": 30, "type": "holy", "desc": "拠点浄化"},
    "💪 肉体強化 (Train)": {"reward": 40, "type": "physical", "desc": "攻撃力UP"},
    "⚡ 魔導構築 (Code)": {"reward": 50, "type": "magic", "desc": "世界改変"},
    "📖 古代魔術 (Study)": {"reward": 50, "type": "magic", "desc": "知識探求"},
}

JOBS = {
    "Novice": {
        "name": "村人", "bonus": None, "img_seed": "novice",
        "desc": "なんでもこなす初心者。特典なし。",
        "bonus_text": "特典なし",
        "good_at": "ー",
    },
    "Warrior": {
        "name": "戦士", "bonus": "physical", "img_seed": "warrior",
        "desc": "肉体系クエストで報酬1.5倍。",
        "bonus_text": "肉体系タスクで報酬×1.5",
        "good_at": "偵察・肉体強化",
    },
    "Wizard": {
        "name": "魔導士", "bonus": "magic", "img_seed": "wizard",
        "desc": "魔法系クエストで報酬1.5倍。",
        "bonus_text": "魔法系タスクで報酬×1.5",
        "good_at": "魔導構築・古代魔術",
    },
    "Engineer": {
        "name": "技師", "bonus": "magic", "img_seed": "engineer",
        "desc": "魔法系クエストで報酬1.5倍。",
        "bonus_text": "魔法系タスクで報酬×1.5",
        "good_at": "魔導構築・古代魔術",
    },
    "Jester": {
        "name": "遊び人", "bonus": "ALL_RANDOM", "img_seed": "jester_clown",
        "desc": "50%で2倍・50%で0.1倍の大博打。",
        "bonus_text": "50%で×2 / 50%で×0.1",
        "good_at": "運任せ",
    },
}

WEEKLY_BOSSES = [
    {"name": "ギガントゴーレム", "weak": "magic", "hp": 2000, "seed": "boss_golem", "desc": "魔法が弱点"},
    {"name": "深淵のスライム", "weak": "holy", "hp": 1500, "seed": "boss_slime", "desc": "浄化が弱点"},
    {"name": "紅蓮の魔獣", "weak": "physical", "hp": 1800, "seed": "boss_beast", "desc": "物理が弱点"},
]

MONSTERS = {
    "スライム": {"rarity": "N", "skill": "gold_up", "val": 1.1, "seed": "slime", "skill_name": "金運アップ", "skill_desc": "報酬ゴールド+10%"},
    "ゴブリン": {"rarity": "N", "skill": "xp_up", "val": 1.1, "seed": "goblin", "skill_name": "応援", "skill_desc": "報酬経験値+10%"},
    "コボルト": {"rarity": "N", "skill": "xp_up", "val": 1.05, "seed": "kobold", "skill_name": "お手伝い", "skill_desc": "報酬経験値+5%"},
    "ミミック": {"rarity": "R", "skill": "chest_up", "val": 1.5, "seed": "mimic", "skill_name": "宝箱アップ", "skill_desc": "宝箱イベント報酬+50%"},
    "ウィスプ": {"rarity": "R", "skill": "gold_up", "val": 1.2, "seed": "wisp", "skill_name": "光の加護", "skill_desc": "報酬ゴールド+20%"},
    "ケルベロス": {"rarity": "SR", "skill": "boss_killer", "val": 1.3, "seed": "cerberus", "skill_name": "ボス狩り", "skill_desc": "週間ボスダメージ+30%"},
    "フェニックス": {"rarity": "SR", "skill": "xp_up", "val": 1.25, "seed": "phoenix", "skill_name": "復活の炎", "skill_desc": "報酬経験値+25%"},
    "ヴァルキリー": {"rarity": "SSR", "skill": "gold_up", "val": 1.6, "seed": "valkyrie", "skill_name": "戦乙女の祝福", "skill_desc": "報酬ゴールド+60%"},
    "ドラゴン": {"rarity": "UR", "skill": "boss_killer", "val": 1.5, "seed": "dragon", "skill_name": "ボスキラー", "skill_desc": "週間ボスダメージ+50%"},
    "魔王の影": {"rarity": "UR", "skill": "gold_up", "val": 2.0, "seed": "demon", "skill_name": "金運大アップ", "skill_desc": "報酬ゴールド+100%"},
}

# ガチャ確率（N 68% / R 25.8% / SR 5% / SSR 1% / UR 0.2%）※1000分率
GACHA_WEIGHTS = {"N": 680, "R": 258, "SR": 50, "SSR": 10, "UR": 2}
def gacha_draw():
    pool_by_rarity = {"N": [], "R": [], "SR": [], "SSR": [], "UR": []}
    for k, v in MONSTERS.items():
        r = v["rarity"]
        if r in pool_by_rarity:
            pool_by_rarity[r].append(k)
    r = random.choices(list(GACHA_WEIGHTS.keys()), weights=list(GACHA_WEIGHTS.values()), k=1)[0]
    return random.choice(pool_by_rarity[r]) if pool_by_rarity[r] else random.choice(list(MONSTERS.keys()))

# SR以上確定ガチャ（SR 80% / SSR 19% / UR 1%）
SR_GUARANTEED_WEIGHTS = {"SR": 80, "SSR": 19, "UR": 1}
def gacha_draw_sr_guaranteed():
    pool = {"SR": [], "SSR": [], "UR": []}
    for k, v in MONSTERS.items():
        r = v["rarity"]
        if r in pool:
            pool[r].append(k)
    r = random.choices(list(SR_GUARANTEED_WEIGHTS.keys()), weights=list(SR_GUARANTEED_WEIGHTS.values()), k=1)[0]
    return random.choice(pool[r]) if pool[r] else random.choice([m for m, d in MONSTERS.items() if d["rarity"] in ("SR","SSR","UR")])

# --- 階層ミニイベント（宝箱・何もない・トラップ） ---
FLOOR_EVENTS = [
    ("treasure", 30, "📦 宝箱を発見！", lambda: random.randint(25, 60)),
    ("nothing", 50, "⋯ 静まり返っている。", lambda: 0),
    ("trap", 20, "⚠️ トラップに引っかかった！", lambda: -random.randint(10, 30)),
]
def roll_floor_event():
    total = sum(w for _, w, _, _ in FLOOR_EVENTS)
    r = random.randint(1, total)
    for event_type, weight, msg, gold_fn in FLOOR_EVENTS:
        r -= weight
        if r <= 0:
            return msg, gold_fn()
    return FLOOR_EVENTS[1][2], 0

# --- 100階層・転生 ---
MAX_FLOOR = 100
TITLES_BY_REBIRTH = [
    "", "初転生者", "二転の勇者", "三転の覇者", "四転の賢者", "五転の伝説",
    "六転の覚者", "七転の星", "八転の王", "九転の神", "十転の超越者"
]
def get_rebirth_title(rebirth_count):
    if rebirth_count <= 0: return ""
    if rebirth_count < len(TITLES_BY_REBIRTH): return TITLES_BY_REBIRTH[rebirth_count]
    return f"輪廻の{rebirth_count}転生者"

# --- ADHD向け・定期的に開きたくなる仕組み ---
def calc_task_streak(df_t):
    """連続でタスクを1回以上やった日数（今日から遡る）"""
    if df_t.empty or 'dt' not in df_t.columns:
        return 0
    today = date.today()
    streak = 0
    d = today
    while True:
        cnt = len(df_t[df_t['dt'].dt.date == d])
        if cnt >= 1:
            streak += 1
            d -= timedelta(days=1)
        else:
            break
    return streak

# --- ペットのセリフ（励まし・昨日比） ---
PET_MESSAGES = [
    "今日も一緒に頑張ろう！",
    "少しずつで大丈夫だよ。",
    "君ならできる！",
    "休むのも大事だよ。",
    "いい調子だね！",
    "ダンジョン、深く潜ってるね。",
]
def get_pet_message(buddy_name, today_count, yesterday_count):
    if today_count > yesterday_count and yesterday_count >= 0:
        return f"昨日は{yesterday_count}回だったけど、今日はもう{today_count}回！ すごい進んでる！"
    if today_count == 2:
        return "あと1つでデイリーだね！ でも2つでも十分頑張ってるよ。"
    if today_count == 1:
        return "1つできた！ それだけで今日はOKだよ。"
    if today_count > 0:
        return random.choice(PET_MESSAGES)
    return "今日はまだクエストしてないね。1つだけやってみよう！ 小さく始めよう。"

# --- CSS: 確実に適用させるスタイル ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DotGothic16&display=swap');

/* 全体：ドット絵RPG風ダンジョン（石壁・レンガ・暗い洞窟） */
.stApp {
    background: #1a1a2e !important;
    background-image:
        radial-gradient(circle at 20% 50%, rgba(40,30,50,0.3) 0%, transparent 50%),
        radial-gradient(circle at 80% 80%, rgba(30,20,40,0.3) 0%, transparent 50%),
        repeating-linear-gradient(0deg, rgba(20,15,25,0.4) 0px, rgba(20,15,25,0.4) 1px, transparent 1px, transparent 8px),
        repeating-linear-gradient(90deg, rgba(25,20,30,0.3) 0px, rgba(25,20,30,0.3) 1px, transparent 1px, transparent 8px),
        linear-gradient(180deg, #0f0f1a 0%, #1a1a2e 30%, #1a1a2e 70%, #0f0f1a 100%) !important;
    color: #e8e0d5 !important;
    font-family: 'DotGothic16', sans-serif;
    image-rendering: pixelated;
    image-rendering: -moz-crisp-edges;
    image-rendering: crisp-edges;
}

/* 本文・キャプションも読みやすく */
p, span, .stCaption, [data-testid="stMarkdownContainer"] { color: #e8e0d5 !important; }
label { color: #c9b896 !important; }

/* タスク・行動ボタン：ドット絵RPG風・ソシャゲ風（枠・光） */
.stButton > button {
    background: linear-gradient(180deg, #3a2f4a 0%, #2a1f3a 100%) !important;
    color: #ffecd2 !important;
    border: 3px solid #8b7355 !important;
    border-radius: 4px !important;
    font-weight: bold !important;
    font-size: 0.95rem !important;
    height: 64px !important;
    text-shadow: 2px 2px 0 #000, 0 0 6px rgba(0,0,0,0.9) !important;
    box-shadow: 
        inset 0 2px 0 rgba(255,255,255,0.15),
        inset 0 -2px 0 rgba(0,0,0,0.5),
        0 0 8px rgba(139,115,85,0.3),
        0 2px 4px rgba(0,0,0,0.6) !important;
    position: relative;
    overflow: hidden;
}
.stButton > button::before {
    content: '';
    position: absolute;
    top: 0; left: -100%;
    width: 100%; height: 100%;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
    transition: left 0.5s;
}
.stButton > button:hover {
    border-color: #c9a227 !important;
    color: #fff5e0 !important;
    box-shadow: 
        0 0 16px rgba(201, 162, 39, 0.6),
        inset 0 2px 0 rgba(255,255,255,0.2),
        inset 0 -2px 0 rgba(0,0,0,0.5),
        0 2px 8px rgba(0,0,0,0.7) !important;
    transform: translateY(-1px);
}
.stButton > button:hover::before {
    left: 100%;
}

/* ウィンドウ枠：ドット絵RPG風（レトロゲーム風） */
.rpg-window {
    background: rgba(25, 20, 30, 0.95);
    border: 4px solid #8b7355;
    border-style: double;
    border-radius: 0px;
    padding: 16px;
    margin-bottom: 20px;
    box-shadow: 
        inset 0 0 20px rgba(0,0,0,0.5),
        0 0 0 2px rgba(139,115,85,0.3),
        0 4px 8px rgba(0,0,0,0.4) !important;
    position: relative;
}
.rpg-window::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(139,115,85,0.05) 2px, rgba(139,115,85,0.05) 4px);
    pointer-events: none;
}

/* バイオーム (背景色) - コンテナ全体に適用 */
[data-testid="stVerticalBlock"] > div:has(div.biome-mark) {
    padding: 20px;
    border-radius: 10px;
    margin-bottom: 20px;
}

/* バイオーム：ドット絵RPG風 */
.biome-forest { 
    background: linear-gradient(to bottom, #134e5e, #71b280); 
    background-image: repeating-linear-gradient(45deg, transparent, transparent 4px, rgba(0,0,0,0.1) 4px, rgba(0,0,0,0.1) 8px);
    color: #fff; padding: 20px; border-radius: 0px; border: 3px solid #2d5a3d; text-shadow: 2px 2px 0 #000; 
}
.biome-sea    { 
    background: linear-gradient(to bottom, #1c92d2, #004e92); 
    background-image: repeating-linear-gradient(45deg, transparent, transparent 4px, rgba(0,0,0,0.1) 4px, rgba(0,0,0,0.1) 8px);
    color: #fff; padding: 20px; border-radius: 0px; border: 3px solid #1a5a7a; text-shadow: 2px 2px 0 #000; 
}
.biome-volcano{ 
    background: linear-gradient(to bottom, #800000, #ff4d4d); 
    background-image: repeating-linear-gradient(45deg, transparent, transparent 4px, rgba(0,0,0,0.1) 4px, rgba(0,0,0,0.1) 8px);
    color: #fff; padding: 20px; border-radius: 0px; border: 3px solid #5a1a1a; text-shadow: 2px 2px 0 #000; 
}
.biome-castle { 
    background: linear-gradient(to bottom, #232526, #414345); 
    background-image: repeating-linear-gradient(45deg, transparent, transparent 4px, rgba(0,0,0,0.15) 4px, rgba(0,0,0,0.15) 8px);
    color: #fff; padding: 20px; border-radius: 0px; border: 3px solid #1a1a1a; text-shadow: 2px 2px 0 #000; 
}

/* ゲージ：HP/EXP（ドット絵風・ソシャゲ風） */
.bar-bg { 
    background: #1a1a1a; 
    height: 16px; 
    width: 100%; 
    border-radius: 0px; 
    overflow: hidden; 
    margin-top: 6px; 
    border: 2px solid #444; 
    box-shadow: inset 0 2px 4px rgba(0,0,0,0.5);
}
.bar-fill-xp { 
    background: linear-gradient(90deg, #2ECC40, #3dff52); 
    background-image: repeating-linear-gradient(45deg, transparent, transparent 2px, rgba(255,255,255,0.1) 2px, rgba(255,255,255,0.1) 4px);
    height: 100%; 
    box-shadow: 0 0 8px rgba(46,204,64,0.6), inset 0 1px 0 rgba(255,255,255,0.2);
}
.bar-fill-hp { 
    background: linear-gradient(90deg, #cc3322, #FF4136); 
    background-image: repeating-linear-gradient(45deg, transparent, transparent 2px, rgba(255,255,255,0.1) 2px, rgba(255,255,255,0.1) 4px);
    height: 100%; 
    box-shadow: 0 0 8px rgba(255,65,54,0.5), inset 0 1px 0 rgba(255,255,255,0.2);
}

h1, h2, h3 { 
    color: #ffecd2 !important; 
    text-shadow: 3px 3px 0 #000, 0 0 12px rgba(201, 162, 39, 0.4);
    letter-spacing: 1px;
    font-weight: bold;
}

/* info/成功メッセージ：ゲーム風 */
[data-testid="stAlert"] { border: 1px solid #8b7355 !important; border-radius: 8px !important; }
[data-testid="stAlert"] div { color: #e8e0d5 !important; }

/* レアリティバッジ・クエストカード */
.rarity-N { color: #94a3b8; font-weight: bold; text-shadow: 1px 1px 0 #000; }
.rarity-R { color: #60a5fa; font-weight: bold; text-shadow: 1px 1px 0 #000, 0 0 8px rgba(96,165,250,0.6); }
.rarity-SR { color: #a78bfa; font-weight: bold; text-shadow: 1px 1px 0 #000, 0 0 8px rgba(167,139,250,0.6); }
.rarity-SSR { color: #f97316; font-weight: bold; text-shadow: 1px 1px 0 #000, 0 0 10px rgba(249,115,22,0.7); }
.rarity-UR { color: #fbbf24; font-weight: bold; text-shadow: 2px 2px 0 #000, 0 0 12px rgba(251,191,36,0.8); }
.pet-speech { 
    background: rgba(30,28,24,0.95); 
    border-left: 4px solid #8b7355; 
    border-radius: 0px; 
    padding: 10px 14px; 
    margin: 8px 0; 
    font-size: 0.95em; 
    color: #e8e0d5; 
    box-shadow: inset 0 0 8px rgba(0,0,0,0.3);
}
/* 画像をドット絵風に */
img { image-rendering: pixelated; image-rendering: -moz-crisp-edges; image-rendering: crisp-edges; }
.event-chest { background: linear-gradient(135deg, rgba(80,60,30,0.9), rgba(120,90,40,0.9)); border: 2px solid #c9a227; }
.event-trap { background: linear-gradient(135deg, rgba(60,30,30,0.9), rgba(90,40,40,0.9)); border: 2px solid #cc4444; }
.event-nothing { background: rgba(40,40,50,0.9); border: 1px solid #555; }
.quest-card { 
    background: rgba(40,38,32,0.95); 
    border: 3px solid #8b7355; 
    border-radius: 0px; 
    padding: 16px; 
    margin: 10px 0; 
    box-shadow: inset 0 0 10px rgba(0,0,0,0.4), 0 2px 4px rgba(0,0,0,0.3);
}
.quest-card-done { 
    border-color: #2ECC40; 
    background: rgba(30,60,40,0.9); 
    box-shadow: 0 0 12px rgba(46,204,64,0.4), inset 0 0 10px rgba(0,0,0,0.3);
}
.reward-big { 
    font-size: 1.4rem; 
    color: #fbbf24; 
    font-weight: bold; 
    text-shadow: 2px 2px 0 #000, 0 0 8px rgba(251,191,36,0.6);
}

/* ===== モバイル・レスポンシブ ===== */
@media (max-width: 768px) {
    .stApp { padding: 0.5rem !important; }
    .stButton > button {
        height: 52px !important;
        min-height: 48px !important;
        font-size: 0.95rem !important;
        padding: 12px 16px !important;
    }
    [data-testid="stSidebar"] {
        width: 100% !important;
        min-width: 100% !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 1rem !important;
    }
    .rpg-window { padding: 12px !important; margin-bottom: 12px !important; }
    h1 { font-size: 1.4rem !important; }
    h2, h3 { font-size: 1.1rem !important; }
    .pet-speech { font-size: 0.9em !important; padding: 8px 12px !important; }
    .reward-big { font-size: 1.2rem !important; }
}

/* タッチデバイス向け：ボタン押しやすく（44px以上推奨） */
@media (pointer: coarse) {
    .stButton > button {
        min-height: 48px !important;
        padding: 14px 18px !important;
    }
}

/* スマホのダークモード対応（システム設定に追従） */
@media (prefers-color-scheme: dark) {
    .stApp, [data-testid="stAppViewContainer"] {
        background: #0a0a0f !important;
        color: #e8e0d5 !important;
    }
    [data-testid="stSidebar"] {
        background: #12121a !important;
        color: #e8e0d5 !important;
    }
    [data-testid="stSidebar"] * { color: #e8e0d5 !important; }
}
</style>
""", unsafe_allow_html=True)

# --- DB接続 ---
def connect_to_gsheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    creds = ServiceAccountCredentials.from_json_keyfile_dict(dict(st.secrets["gcp_service_account"]), scope)
    client = gspread.authorize(creds)
    return client.open_by_url(st.secrets["sheets"]["url"])

def _unique_headers(raw_headers):
    """重複・空ヘッダーを一意の名前にする（自前でレコード構築する用）。gspread には渡さない。"""
    seen = {}
    result = []
    for i, h in enumerate(raw_headers):
        name = (h or "").strip()
        if not name:
            name = f"_col{i}"
        if name in seen:
            seen[name] += 1
            result.append(f"{name}_{seen[name]}")
        else:
            seen[name] = 1
            result.append(name)
    return result

def get_user_data(ws):
    """users シート: 列G(7)=rebirth_count, 列U(21)=title または titles があると転生が保存されます。
    空ヘッダー・重複ヘッダーがあっても自前で読み取るためエラーにしない。"""
    all_values = ws.get_all_values()
    if not all_values:
        raise ValueError("users シートが空です")
    raw_headers = all_values[0]
    if not raw_headers:
        raise ValueError("users シートの1行目（ヘッダー）が空です")
    headers = _unique_headers(raw_headers)
    records = []
    for row in all_values[1:]:
        row_padded = (row + [""] * len(headers))[:len(headers)]
        records.append(dict(zip(headers, row_padded)))
    df = pd.DataFrame(records)
    if df.empty:
        raise ValueError("users シートにデータ行がありません")
    # user_id 列を探す（ヘッダーが user_id または先頭列）
    uid_col = "user_id" if "user_id" in df.columns else df.columns[0]
    matches = df[df[uid_col].astype(str).str.strip() == "u001"]
    if matches.empty:
        raise ValueError("users シートに user_id='u001' の行がありません")
    idx = int(matches.index[0]) + 2
    user_row = matches.iloc[0]
    return user_row.to_dict(), idx

def get_user_title(user):
    """スプレッドシートの列名が title または titles のどちらでも読めるように"""
    return (user.get('title') or user.get('titles') or '')

def _apply_xp_gain(ws_u, u_idx, new_xp, u_nxt_xp, u_lv):
    """経験値獲得をシートに反映（レベルアップ・オーバーフロー対応）"""
    if new_xp >= u_nxt_xp:
        overflow = new_xp - u_nxt_xp
        ws_u.update_cell(u_idx, 3, u_lv + 1)
        ws_u.update_cell(u_idx, 5, int(((u_lv + 1) ** 1.5) * 100))
        ws_u.update_cell(u_idx, 4, overflow)
    else:
        ws_u.update_cell(u_idx, 4, new_xp)

def _int(val, default=0):
    """スプレッドシートから読み取った値を int に変換（文字列で来ても安全）"""
    if val is None or (isinstance(val, str) and str(val).strip() == ''):
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default

def get_weekly_boss():
    week_num = datetime.now().isocalendar()[1]
    return WEEKLY_BOSSES[week_num % len(WEEKLY_BOSSES)]

def get_biome_html(floor):
    # 100階層: 1-25 森, 26-50 海, 51-75 火山, 76-100 魔王城
    f = min(max(1, int(floor)), MAX_FLOOR)
    if f <= 25: return "biome-forest", "🌲 始まりの森"
    if f <= 50: return "biome-sea", "🌊 紺碧の海岸"
    if f <= 75: return "biome-volcano", "🌋 灼熱の火山"
    return "biome-castle", "🏰 魔王城"

# --- メインロジック ---
def main():
    try:
        sh = connect_to_gsheet()
        ws_u = sh.worksheet("users")
        ws_t = sh.worksheet("tasks")
        ws_i = sh.worksheet("inventory")
        user, u_idx = get_user_data(ws_u)
    except Exception as e:
        st.error("DB接続エラー")
        with st.expander("詳細を表示"):
            st.exception(e)
            st.caption("確認: .streamlit/secrets.toml に gcp_service_account と sheets.url が正しく設定されているか、スプレッドシートの共有でサービスアカウントのメールに編集権限を付与しているか")
        st.stop()

    if 'battle_log' not in st.session_state:
        st.session_state.battle_log = ["システム起動..."]

    today = date.today()
    yesterday = today - timedelta(days=1)
    df_t = pd.DataFrame(ws_t.get_all_records())
    d_cnt, w_cnt, yesterday_cnt = 0, 0, 0
    if not df_t.empty:
        df_t['dt'] = pd.to_datetime(df_t['created_at'])
        d_cnt = len(df_t[df_t['dt'].dt.date == today])
        yesterday_cnt = len(df_t[df_t['dt'].dt.date == yesterday])
        start_wk = today - timedelta(days=today.weekday())
        w_cnt = len(df_t[df_t['dt'].dt.date >= start_wk])
    d_claim = (str(user.get('daily_claimed')) == str(today))
    wk_id = f"{today.year}-W{today.isocalendar()[1]}"
    w_claim = (str(user.get('weekly_claimed')) == wk_id)

    # --- 1. ヘッダー (アバター & ステータス) ---
    st.markdown("""
    <div style="text-align: center; margin-bottom: 8px;">
        <h1 style="font-size: 1.8rem; letter-spacing: 2px;">⚔️ LIFE QUEST: Recovery</h1>
        <p style="color: #8b7355; margin: 0; font-size: 0.85rem;">― 日々のタスクで冒険を進めろ ―</p>
    </div>
    """, unsafe_allow_html=True)
    
    col_h1, col_h2 = st.columns([1, 2])
    
    with col_h1:
        # アバター
        job_info = JOBS.get(user.get('job_class') or 'Novice', JOBS['Novice'])
        avatar = get_avatar_url(job_info['img_seed'] + str(user.get('name', '')))
        
        c_av1, c_av2 = st.columns([1, 2])
        c_av1.image(avatar, width=80)
        with c_av2:
            rebirth_count = int(user.get('rebirth_count') or 0)
            title = get_user_title(user)
            st.markdown(f"**Lv.{_int(user.get('level'), 1)} {user.get('name', '')}**")
            st.caption(f"Job: {job_info['name']}")
            if rebirth_count > 0 or title:
                st.caption(f"🔄 転生{rebirth_count}回" + (f" ｜ 「{title}」" if title else ""))
        
        # XP（スプレッドシートは文字列で返るため _int で数値化）
        cur_xp = _int(user.get('current_xp'))
        nxt_xp = max(1, _int(user.get('next_level_xp'), 100))
        xp_pct = min(100, (cur_xp / nxt_xp) * 100)
        st.markdown(f"""<div class="bar-bg"><div class="bar-fill-xp" style="width:{xp_pct}%;"></div></div>""", unsafe_allow_html=True)
        st.caption(f"Exp: {cur_xp}/{nxt_xp}")
        st.write(f"💰 {_int(user.get('gold'))} G")
        task_streak = calc_task_streak(df_t)
        login_streak = _int(user.get('login_streak'))
        st.caption(f"🌞 デイリー {d_cnt}/3 ｜ 📅 ウィークリー {w_cnt}/15")
        st.caption(f"🔥 タスク連続 {task_streak}日 ｜ 📆 ログイン {login_streak}日")

    with col_h2:
        # バディ & おしゃべりペット
        buddy = user.get('equipped_pet', '') or ''
        if buddy in MONSTERS:
            b_data = MONSTERS[buddy]
            c_b1, c_b2 = st.columns([1, 4])
            c_b1.image(get_monster_url(b_data['seed'], b_data['rarity']), width=70)
            pet_says = get_pet_message(buddy, d_cnt, yesterday_cnt)
            st.markdown(f"<div class='pet-speech'><strong>{buddy}</strong>「{pet_says}」</div>", unsafe_allow_html=True)
            skill_desc = b_data.get('skill_desc', b_data.get('skill_name', b_data['skill']))
            st.caption(f"効果: {skill_desc}")
        else:
            st.info("Buddy: なし (ショップで召喚しよう。相棒がいると励ましてくれるよ)")

    st.markdown("---")

    # --- 2. アクション (タスク) ---
    rec_task = random.choice(list(TASKS.keys())) if TASKS else ""
    st.markdown(f"""
    <div class="rpg-window" style="margin-bottom: 12px;">
        <h3 style="margin: 0 0 8px 0;">⚔️ クエストボード ― 行動を選べ</h3>
        <p style="margin: 0; color: #c9b896; font-size: 0.9em;">タスクを完了してゴールドと経験値を得よう</p>
        <p style="margin: 8px 0 0 0; color: #8b7355; font-size: 0.85em;">💡 今日は1つだけでもOK！ 脳のご褒美、ひとつずつ貰おう。今日のおすすめ: {rec_task}</p>
    </div>
    """, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    cols = [c1, c2, c3]
    
    for i, (t_name, t_data) in enumerate(TASKS.items()):
        # 基本報酬を計算（ボーナス前）
        base_reward = t_data['reward']
        btn_label = f"{t_name}\n💰 {base_reward}G"
        if cols[i%3].button(btn_label, use_container_width=True, help=f"{t_data['desc']} - 基本報酬: {base_reward}G"):
            # 計算ロジック
            base = t_data['reward']
            bonus = 1.0
            logs = []
            
            # ジョブ
            if job_info['bonus'] == "ALL_RANDOM":
                if random.random() < 0.5: bonus = 2.0; logs.append("🎰 JACKPOT!")
                else: bonus = 0.1; logs.append("💀 失敗...")
            elif job_info['bonus'] == t_data['type']:
                bonus = 1.5; logs.append("⚔️ 職適正!")
            
            # ペット
            if buddy in MONSTERS:
                pskill = MONSTERS[buddy]['skill']
                if pskill == 'gold_up': bonus *= 1.1; logs.append("💰 金運")
                if pskill == 'xp_up': bonus *= 1.1; logs.append("✨ 応援")
            
            val = int(base * bonus)
            if val < 1: val = 1
            
            # 今日の最初のタスクボーナス（ADHD向け：始めるご褒美）
            is_first_today = (d_cnt == 0)
            if is_first_today:
                val = max(1, int(val * 1.5))
                logs.append("🌟初タスク!")
            
            # 転生ボーナス（永久）
            rebirth_count = int(user.get('rebirth_count') or 0)
            if rebirth_count > 0:
                rebirth_bonus = 1 + 0.1 * rebirth_count
                val = max(1, int(val * rebirth_bonus))
                logs.append("✨転生")
            
            # ボス
            w_boss = get_weekly_boss()
            is_weak = (t_data['type'] == w_boss['weak'])
            dmg = val * 2 if is_weak else val
            if is_weak: logs.append("🔥 弱点!")
            
            # 更新（100階でキャップ）
            u_gold = _int(user.get('gold'))
            u_cur_xp = _int(user.get('current_xp'))
            u_nxt_xp = _int(user.get('next_level_xp'), 100)
            u_lv = _int(user.get('level'), 1)
            new_gold = u_gold + val
            new_xp = u_cur_xp + val
            new_boss_dmg = _int(user.get('weekly_boss_damage')) + dmg
            current_floor = _int(user.get('dungeon_floor'))
            new_floor = min(MAX_FLOOR, current_floor + 1)
            
            # レベルアップ
            if new_xp >= u_nxt_xp:
                ws_u.update_cell(u_idx, 3, u_lv + 1)
                ws_u.update_cell(u_idx, 5, int(((u_lv + 1) ** 1.5) * 100))
                new_xp = 0
                st.balloons()
                logs.append("🆙 LEVEL UP!!")

            # 階層ミニイベント（宝箱・何もない・トラップ）
            event_msg, event_gold = roll_floor_event()
            final_gold = max(0, new_gold + event_gold)
            if event_gold != 0:
                logs.append(event_msg.split("!")[0] if "!" in event_msg else event_msg)

            ws_u.update_cell(u_idx, 6, final_gold)
            ws_u.update_cell(u_idx, 4, new_xp)
            ws_u.update_cell(u_idx, 8, new_floor)
            ws_u.update_cell(u_idx, 19, new_boss_dmg)
            ws_t.append_row([str(uuid.uuid4()), 'u001', t_name, t_data['type'], 1, 'Completed', str(datetime.now())])
            
            ts = datetime.now().strftime('%H:%M')
            st.session_state.battle_log.insert(0, f"[{ts}] {t_name}: {val}G " + " ".join(logs))
            st.toast(f"やったね！ +{val} G")
            if is_first_today:
                st.toast("🌟 今日の最初の1つ、クリア！ その調子！")
            if event_gold != 0:
                st.toast(f"{event_msg} {'+' if event_gold > 0 else ''}{event_gold} G")
            time.sleep(0.5); st.rerun()

    # --- 3. ダンジョン & ボス ---
    floor = min(MAX_FLOOR, max(1, _int(user.get('dungeon_floor'))))
    b_class, b_name = get_biome_html(floor)
    dungeon_flavor = random.choice([
        "奥から冷たい風が流れてくる……", "足元の石がきしむ。", "どこかで水が滴っている。",
        "松明の光が壁を揺らす。", "深く潜るほど、空気が重くなる。",
    ])
    st.markdown(f"""
    <div class="{b_class}">
        <h3>📍 {b_name} (階層 {floor}/{MAX_FLOOR})</h3>
        <p style="margin: 4px 0 0 0; font-size: 0.9em; opacity: 0.9;">{dungeon_flavor}</p>
    </div>
    """, unsafe_allow_html=True)
    
    # 100階到達: 転生パネル（rebirth_count は G列(7), title は U列(21) に書き込みます）
    rebirth_count = int(user.get('rebirth_count') or 0)
    if floor >= MAX_FLOOR:
        st.markdown("""
        <div class="rpg-window" style="border-color: #c9a227; background: rgba(40,32,24,0.95);">
            <h3 style="color: #ffecd2;">👑 100階到達 ― 転生</h3>
            <p style="color: #c9b896;">転生すると1階から再スタート。永久ボーナス（報酬+10%×転生回数）と称号を獲得できる。</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🔄 転生する（1階へ・称号獲得）", type="primary"):
            try:
                new_rebirth = rebirth_count + 1
                title_text = get_rebirth_title(new_rebirth)
                ws_u.update_cell(u_idx, 8, 1)
                ws_u.update_cell(u_idx, 7, new_rebirth)  # G列: rebirth_count
                ws_u.update_cell(u_idx, 21, title_text)  # U列: title
                st.balloons()
                st.success(f"転生完了！ 「{title_text}」を獲得。報酬がさらにアップ！")
                time.sleep(1.5)
                st.rerun()
            except Exception as e:
                st.error("転生の保存に失敗しました。スプレッドシートに列G(7)=rebirth_count・列U(21)=title があるか確認してください。")
    
    with st.container():
        # HTMLの終了タグではなく、コンテナ内で背景色を引き継ぐのは難しいので
        # ここはシンプルにボス画像などを表示
        
        w_boss = get_weekly_boss()
        boss_max = w_boss['hp']
        boss_cur = max(0, boss_max - _int(user.get('weekly_boss_damage')))
        boss_pct = (boss_cur / boss_max) * 100
        
        c_boss1, c_boss2 = st.columns([1, 2])
        with c_boss1:
            st.image(get_monster_url(w_boss['seed'], "UR"), width=120)
        with c_boss2:
            st.markdown(f"**☠️ WANTED: {w_boss['name']}**")
            st.markdown(f"""<div class="bar-bg"><div class="bar-fill-hp" style="width:{boss_pct}%;"></div></div>""", unsafe_allow_html=True)
            st.caption(f"HP: {boss_cur}/{boss_max} (弱点: {w_boss['desc']})")
            if boss_cur == 0: st.success("🎉 討伐完了！")

    st.markdown("---")

    # --- 4. タブ機能 ---
    tab1, tab2, tab3, tab4 = st.tabs(["📋 ギルド", "💎 ショップ", "📊 記録", "🎒 倉庫"])

    with tab1:
        c_g1, c_g2 = st.columns(2)
        with c_g1:
            st.subheader("📋 デイリー・ウィークリークエスト")
            # デイリークエストカード
            d_done = d_cnt >= 3
            d_class = "quest-card-done" if d_done and d_claim else "quest-card"
            st.markdown(f"""
            <div class="{d_class}">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span>🌞 デイリークエスト</span>
                    <span class="reward-big">報酬: 200G</span>
                </div>
                <p style="margin: 8px 0 4px 0; color: #c9b896;">タスクを<strong>3回</strong>クリアで達成</p>
                <div class="bar-bg" style="height: 10px;"><div class="bar-fill-xp" style="width: {min(100, d_cnt/3*100)}%; height: 100%;"></div></div>
                <p style="margin: 4px 0 0 0; font-size: 0.9em;">進捗 {d_cnt}/3</p>
                {"<p style='margin:4px 0 0 0; color:#2ECC40; font-weight:bold;'>🎯 あと1つでデイリー達成！</p>" if d_cnt == 2 and not d_claim else ""}
            </div>
            """, unsafe_allow_html=True)
            if d_done and not d_claim:
                if st.button("🎁 200G を受け取る", key="daily_claim"):
                    ws_u.update_cell(u_idx, 6, _int(user.get('gold')) + 200)
                    ws_u.update_cell(u_idx, 14, str(today))
                    st.success("200G 獲得！"); time.sleep(0.5); st.rerun()
            elif d_claim:
                st.caption("✅ 本日分は受取済み")

            # ウィークリークエストカード
            w_done = w_cnt >= 15
            w_class = "quest-card-done" if w_done and w_claim else "quest-card"
            st.markdown(f"""
            <div class="{w_class}">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span>📅 ウィークリークエスト</span>
                    <span class="reward-big">報酬: 500G</span>
                </div>
                <p style="margin: 8px 0 4px 0; color: #c9b896;">今週中にタスクを<strong>15回</strong>クリアで達成</p>
                <div class="bar-bg" style="height: 10px;"><div class="bar-fill-xp" style="width: {min(100, w_cnt/15*100)}%; height: 100%;"></div></div>
                <p style="margin: 4px 0 0 0; font-size: 0.9em;">進捗 {w_cnt}/15</p>
            </div>
            """, unsafe_allow_html=True)
            if w_done and not w_claim:
                if st.button("🎁 500G を受け取る", key="weekly_claim"):
                    ws_u.update_cell(u_idx, 6, _int(user.get('gold')) + 500)
                    ws_u.update_cell(u_idx, 15, wk_id)
                    st.success("500G 獲得！"); time.sleep(0.5); st.rerun()
            elif w_claim:
                st.caption("✅ 今週分は受取済み")

        with c_g2:
            st.subheader("⚔️ 職業と転職")
            st.caption("職業によって相性の良いタスクで報酬がアップします")
            for k, v in JOBS.items():
                is_current = (k == (user.get('job_class') or ''))
                border = "2px solid #c9a227" if is_current else "1px solid #555"
                st.markdown(f"""
                <div style="background: rgba(30,28,24,0.9); border: {border}; border-radius: 8px; padding: 10px; margin: 6px 0;">
                    <strong>{v['name']}</strong> {" ← 現在" if is_current else ""}<br>
                    <span style="color: #c9b896; font-size: 0.9em;">{v['desc']}</span><br>
                    <span style="color: #8b7355; font-size: 0.85em;">適正: {v['good_at']} ｜ {v['bonus_text']}</span>
                </div>
                """, unsafe_allow_html=True)
                if not is_current and st.button(f"転職する (100G)", key=f"job_{k}"):
                    if _int(user.get('gold')) >= 100:
                        ws_u.update_cell(u_idx, 11, k)
                        ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 100)
                        st.success(f"{v['name']}に転職した"); time.sleep(0.5); st.rerun()
                    else:
                        st.error("金貨が足りません")

    with tab2:  # ショップ
        st.subheader("💎 ショップ")
        # ガチャ確率表示（UR 0.2% 等）
        st.markdown("""
        <div class="rpg-window" style="margin-bottom: 16px;">
            <h4 style="margin: 0 0 8px 0;">📜 通常召喚確率</h4>
            <p style="margin: 0; color: #c9b896;">N 68% ｜ R 25.8% ｜ SR 5% ｜ SSR 1% ｜ UR 0.2%</p>
        </div>
        """, unsafe_allow_html=True)

        # 週1回・月1回限定（列V(22), W(23) に last_weekly_ticket, last_monthly_sr_ticket があると保存されます）
        month_id = f"{today.year}-{today.month:02d}"
        can_weekly_ticket = (str(user.get('last_weekly_ticket') or '') != wk_id)
        can_monthly_sr = (str(user.get('last_monthly_sr_ticket') or '') != month_id)

        st.markdown("#### 🏷️ 週・月限定（お得）")
        lim1, lim2 = st.columns(2)
        with lim1:
            st.markdown("**🎫 ガチャチケ10枚セット** — 800G")
            st.caption("週1回のみ！定価1000G相当（20%OFF）")
            if st.button("購入（今週分）", key="weekly_ticket", disabled=not can_weekly_ticket):
                if can_weekly_ticket and _int(user.get('gold')) >= 800:
                    results = [gacha_draw() for _ in range(10)]
                    for m_key in results:
                        m_data = MONSTERS[m_key]
                        ws_i.append_row(['u001', m_key, m_data['rarity'], 1, str(datetime.now())])
                    ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 800)
                    try: ws_u.update_cell(u_idx, 22, wk_id)
                    except: pass
                    st.session_state.last_gacha_10 = results
                    st.success("10連召喚！"); time.sleep(0.8); st.rerun()
                elif not can_weekly_ticket: st.warning("今週は購入済み")
                else: st.error("金貨不足")
            if not can_weekly_ticket: st.caption("✅ 今週は購入済み")
        with lim2:
            st.markdown("**✨ SR以上確定チケット** — 600G")
            st.caption("月1回のみ！SR 80% / SSR 19% / UR 1%")
            if st.button("購入（今月分）", key="monthly_sr", disabled=not can_monthly_sr):
                if can_monthly_sr and _int(user.get('gold')) >= 600:
                    m_key = gacha_draw_sr_guaranteed()
                    m_data = MONSTERS[m_key]
                    ws_i.append_row(['u001', m_key, m_data['rarity'], 1, str(datetime.now())])
                    ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 600)
                    try: ws_u.update_cell(u_idx, 23, month_id)
                    except: pass
                    st.session_state.last_gacha_result = (m_key, m_data['rarity'])
                    st.success(f"{m_key} GET!"); time.sleep(0.8); st.rerun()
                elif not can_monthly_sr: st.warning("今月は購入済み")
                else: st.error("金貨不足")
            if not can_monthly_sr: st.caption("✅ 今月は購入済み")

        st.markdown("#### 🌟 通常召喚")
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            st.markdown("**🌟 1回召喚**")
            is_free = (str(today) != str(user.get('last_free_gacha')))
            cost = "無料" if is_free else "100G"
            if st.button(f"召喚する ({cost})", key="gacha1", use_container_width=True):
                if not is_free and _int(user.get('gold')) < 100:
                    st.error("金貨が足りません")
                else:
                    m_key = gacha_draw()
                    m_data = MONSTERS[m_key]
                    ws_i.append_row(['u001', m_key, m_data['rarity'], 1, str(datetime.now())])
                    if is_free: ws_u.update_cell(u_idx, 13, str(today))
                    else: ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 100)
                    r = m_data['rarity']
                    st.session_state.last_gacha_result = (m_key, r)
                    st.rerun()
            if st.session_state.get('last_gacha_result'):
                mk, r = st.session_state.last_gacha_result
                md = MONSTERS[mk]
                skill_desc = md.get('skill_desc', md.get('skill_name', md['skill']))
                st.markdown(f'<span class="rarity-{r}">★ {r} ★</span> {mk}', unsafe_allow_html=True)
                st.image(get_monster_url(md['seed'], r), width=80)
                st.caption(f"効果: {skill_desc}")

        with col_g2:
            st.markdown("**✨ 10連召喚（お得）**")
            st.caption("900Gで10回分！1回あたり90G")
            if st.button("10連召喚 (900G)", key="gacha10", use_container_width=True):
                if _int(user.get('gold')) < 900:
                    st.error("金貨が足りません（900G必要）")
                else:
                    results = [gacha_draw() for _ in range(10)]
                    for m_key in results:
                        m_data = MONSTERS[m_key]
                        ws_i.append_row(['u001', m_key, m_data['rarity'], 1, str(datetime.now())])
                    ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 900)
                    st.session_state.last_gacha_10 = results
                    st.rerun()
            if st.session_state.get('last_gacha_10'):
                res = st.session_state.last_gacha_10
                ur_c = sum(1 for mk in res if MONSTERS[mk]['rarity']=='UR')
                ssr_c = sum(1 for mk in res if MONSTERS[mk]['rarity']=='SSR')
                sr_c = sum(1 for mk in res if MONSTERS[mk]['rarity']=='SR')
                r_c = sum(1 for mk in res if MONSTERS[mk]['rarity']=='R')
                n_c = 10 - ur_c - ssr_c - sr_c - r_c
                st.success(f"10連 — UR:{ur_c} SSR:{ssr_c} SR:{sr_c} R:{r_c} N:{n_c}")
                cols = st.columns(5)
                for i, m_key in enumerate(res):
                    with cols[i % 5]:
                        md = MONSTERS[m_key]
                        r = md['rarity']
                        st.markdown(f'<span class="rarity-{r}">{r}</span>', unsafe_allow_html=True)
                        st.image(get_monster_url(md['seed'], r), width=60)
                        st.caption(m_key)

        st.divider()
        st.subheader("🎒 相棒編成")
        df_i = pd.DataFrame(ws_i.get_all_records())
        if not df_i.empty:
            my_m = df_i[df_i['user_id']=='u001']['item_name'].unique()
            valid = [m for m in my_m if m in MONSTERS]
            sel = st.selectbox("装備する相棒を選んでください", ["なし"] + valid)
            if st.button("装備する"):
                v = "" if sel == "なし" else sel
                ws_u.update_cell(u_idx, 17, v)
                st.success("装備しました"); time.sleep(0.5); st.rerun()
            st.caption("相棒の効果はタスク報酬に反映されます")
            for m in valid:
                md = MONSTERS[m]
                r = md["rarity"]
                skill_desc = md.get('skill_desc', md.get('skill_name', md['skill']))
                st.markdown(f"- **{m}** <span class='rarity-{r}'>{r}</span><br>効果: {skill_desc}", unsafe_allow_html=True)
        else:
            st.info("召喚で仲間を増やそう！")

        st.divider()
        st.markdown("#### 🛒 便利アイテム")
        st.markdown("**📜 経験値アイテム**")
        xp1, xp2, xp3 = st.columns(3)
        with xp1:
            st.caption("経験値の書 100G → 150 XP")
            if st.button("購入", key="item_xp"):
                if _int(user.get('gold')) >= 100:
                    u_cur_xp, u_nxt_xp = _int(user.get('current_xp')), _int(user.get('next_level_xp'), 100)
                    u_lv = _int(user.get('level'), 1)
                    new_xp = u_cur_xp + 150
                    ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 100)
                    _apply_xp_gain(ws_u, u_idx, new_xp, u_nxt_xp, u_lv)
                    st.success("150 XP 獲得！"); time.sleep(0.5); st.rerun()
                else: st.error("金貨不足")
        with xp2:
            st.caption("冒険の証 300G → 500 XP")
            if st.button("購入", key="item_xp2"):
                if _int(user.get('gold')) >= 300:
                    u_cur_xp, u_nxt_xp = _int(user.get('current_xp')), _int(user.get('next_level_xp'), 100)
                    u_lv = _int(user.get('level'), 1)
                    new_xp = u_cur_xp + 500
                    ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 300)
                    _apply_xp_gain(ws_u, u_idx, new_xp, u_nxt_xp, u_lv)
                    st.success("500 XP 獲得！"); time.sleep(0.5); st.rerun()
                else: st.error("金貨不足")
        with xp3:
            st.caption("伝説の書 800G → 1500 XP")
            if st.button("購入", key="item_xp3"):
                if _int(user.get('gold')) >= 800:
                    u_cur_xp, u_nxt_xp = _int(user.get('current_xp')), _int(user.get('next_level_xp'), 100)
                    u_lv = _int(user.get('level'), 1)
                    new_xp = u_cur_xp + 1500
                    ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 800)
                    _apply_xp_gain(ws_u, u_idx, new_xp, u_nxt_xp, u_lv)
                    st.success("1500 XP 獲得！"); time.sleep(0.5); st.rerun()
                else: st.error("金貨不足")

    with tab3: # 記録
        if not df_t.empty:
            daily = df_t.groupby(df_t['dt'].dt.date).size().reset_index(name='Actions')
            c = alt.Chart(daily).mark_bar().encode(x='dt:T', y='Actions:Q')
            st.altair_chart(c, use_container_width=True)

    with tab4: # 倉庫
        if not df_i.empty:
            cnt = df_i[df_i['user_id']=='u001']['item_name'].value_counts()
            for n, c in cnt.items(): st.write(f"- {n} x{c}")

if __name__ == "__main__":
    main()