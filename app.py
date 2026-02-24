import streamlit as st
import json
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
    # 主人公用: adventurerスタイルでRPG風に
    return f"https://api.dicebear.com/9.x/adventurer/png?seed={seed}&size=96&backgroundColor=2d2d44"

# モンスターの絵文字マッピング（イラストの代替案）
MONSTER_EMOJIS = {
    "スライム": "🟢",
    "ゴブリン": "👹",
    "コボルト": "🐺",
    "ミミック": "📦",
    "ウィスプ": "✨",
    "ケルベロス": "🐕",
    "フェニックス": "🔥",
    "ヴァルキリー": "⚔️",
    "ドラゴン": "🐉",
    "魔王の影": "👤",
    "ギガントゴーレム": "🗿",
    "深淵のスライム": "💧",
    "紅蓮の魔獣": "🔥",
}

def get_monster_display(monster_name, rarity="N"):
    """モンスターの表示（絵文字 + レアリティカラー）"""
    emoji = MONSTER_EMOJIS.get(monster_name, "👾")
    rarity_colors = {
        "N": "#94a3b8", "R": "#60a5fa", "SR": "#a78bfa", 
        "SSR": "#f97316", "UR": "#fbbf24"
    }
    color = rarity_colors.get(rarity, "#94a3b8")
    return emoji, color

def get_monster_url(seed, rarity="N", monster_name=""):
    """モンスターの表示用（後方互換のため残すが、実際にはget_monster_displayを使用）"""
    # この関数は後方互換のため残すが、実際にはget_monster_displayを使用
    emoji, color = get_monster_display(monster_name, rarity)
    import base64
    svg_content = f'<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128" viewBox="0 0 128 128"><text x="64" y="80" font-size="96" text-anchor="middle" dominant-baseline="central">{emoji}</text></svg>'
    encoded = base64.b64encode(svg_content.encode('utf-8')).decode('utf-8')
    return f"data:image/svg+xml;base64,{encoded}"

# --- マスターデータ（difficulty: easy=報酬0.8倍・始めやすい, normal=1.0倍, hard=1.3倍）---
TASKS = {
    "🏃 偵察任務 (Walk)": {"reward": 30, "type": "physical", "desc": "周辺調査", "difficulty": "easy"},
    "🧹 聖域整地 (Clean)": {"reward": 30, "type": "holy", "desc": "拠点浄化", "difficulty": "easy"},
    "💪 肉体強化 (Train)": {"reward": 40, "type": "physical", "desc": "攻撃力UP", "difficulty": "normal"},
    "⚡ 魔導構築 (Code)": {"reward": 50, "type": "magic", "desc": "世界改変", "difficulty": "hard"},
    "📖 古代魔術 (Study)": {"reward": 50, "type": "magic", "desc": "知識探求", "difficulty": "normal"},
}
DIFFICULTY_MULT = {"easy": 0.9, "normal": 1.0, "hard": 1.2}
DIFFICULTY_LABEL = {"easy": "かんたん", "normal": "ふつう", "hard": "むずかしい"}

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
    {"name": "ギガントゴーレム", "weak": "magic", "hp": 2000, "seed": "boss_golem", "desc": "魔法が弱点", "reward": 1000, "reward_xp": 500},
    {"name": "深淵のスライム", "weak": "holy", "hp": 1500, "seed": "boss_slime", "desc": "浄化が弱点", "reward": 800, "reward_xp": 400},
    {"name": "紅蓮の魔獣", "weak": "physical", "hp": 1800, "seed": "boss_beast", "desc": "物理が弱点", "reward": 900, "reward_xp": 450},
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

# --- 実績システム ---
ACHIEVEMENTS = {
    "first_task": {"name": "初めての一歩", "desc": "初めてタスクを完了", "reward": 50, "icon": "🎯"},
    "task_10": {"name": "継続の力", "desc": "タスクを10回完了", "reward": 200, "icon": "🔥"},
    "task_50": {"name": "努力家", "desc": "タスクを50回完了", "reward": 500, "icon": "⭐"},
    "task_100": {"name": "百戦錬磨", "desc": "タスクを100回完了", "reward": 1000, "icon": "💎"},
    "floor_10": {"name": "10階到達", "desc": "10階層に到達", "reward": 300, "icon": "🏔️"},
    "floor_50": {"name": "中盤突破", "desc": "50階層に到達", "reward": 800, "icon": "⛰️"},
    "floor_100": {"name": "最下層到達", "desc": "100階層に到達", "reward": 2000, "icon": "👑"},
    "rebirth_1": {"name": "転生者", "desc": "1回転生", "reward": 1500, "icon": "🔄"},
    "rebirth_5": {"name": "輪廻の達人", "desc": "5回転生", "reward": 5000, "icon": "🌟"},
    "level_10": {"name": "レベル10", "desc": "レベル10に到達", "reward": 400, "icon": "📈"},
    "level_20": {"name": "レベル20", "desc": "レベル20に到達", "reward": 1000, "icon": "📊"},
    "gacha_ur": {"name": "UR獲得", "desc": "URモンスターを獲得", "reward": 2000, "icon": "✨"},
    "streak_7": {"name": "1週間継続", "desc": "7日連続でタスク完了", "reward": 500, "icon": "🔥"},
    "streak_30": {"name": "1ヶ月継続", "desc": "30日連続でタスク完了", "reward": 3000, "icon": "💪"},
}

# --- ログインボーナス（連続ログイン報酬） ---
LOGIN_BONUS = {
    1: 50, 2: 100, 3: 150, 4: 200, 5: 250, 6: 300, 7: 500,
    14: 1000, 21: 1500, 30: 2000
}

# 季節限定ミッション（18）：月ごとの条件と報酬
SEASONAL_MISSIONS = {
    2: {"name": "冬の偵察", "desc": "今月「偵察任務」を5回", "task_key": "偵察", "target": 5, "reward": 150},
    3: {"name": "春の学び", "desc": "今月「古代魔術」を5回", "task_key": "古代魔術", "target": 5, "reward": 150},
    4: {"name": "春の整頓", "desc": "今月「聖域整地」を5回", "task_key": "聖域", "target": 5, "reward": 150},
    5: {"name": "体を動かす", "desc": "今月「肉体強化」を5回", "task_key": "肉体強化", "target": 5, "reward": 150},
    6: {"name": "夏の魔導", "desc": "今月「魔導構築」を5回", "task_key": "魔導", "target": 5, "reward": 150},
}
# 限定称号（5）：解除条件とボーナス
EXTRA_TITLES = [
    {"id": "streak_7", "name": "7日連続", "condition": "streak_7", "bonus": "task_gold_5"},
    {"id": "streak_30", "name": "30日連続", "condition": "streak_30", "bonus": "task_gold_10"},
    {"id": "monthly_50", "name": "今月50タスク", "condition": "monthly_50", "bonus": "task_gold_5"},
]

# --- ミッション（短期目標） ---
MISSIONS = {
    "daily_1": {"name": "今日1つ", "desc": "今日中にタスク1回", "reward": 30, "type": "daily", "target": 1},
    "daily_2": {"name": "今日2つ", "desc": "今日中にタスク2回", "reward": 60, "type": "daily", "target": 2},
    "daily_3": {"name": "今日3つ", "desc": "今日中にタスク3回", "reward": 100, "type": "daily", "target": 3},
    "weekly_5": {"name": "週5回", "desc": "今週中にタスク5回", "reward": 200, "type": "weekly", "target": 5},
    "weekly_10": {"name": "週10回", "desc": "今週中にタスク10回", "reward": 400, "type": "weekly", "target": 10},
}

# --- ランダム報酬ボックス（サプライズ要素） ---
RANDOM_BOX_REWARDS = [
    ("gold", 50, "💰 ゴールド50G"),
    ("gold", 100, "💰 ゴールド100G"),
    ("gold", 200, "💰 ゴールド200G"),
    ("xp", 50, "✨ 経験値50XP"),
    ("xp", 100, "✨ 経験値100XP"),
    ("gacha", 1, "🎫 ガチャチケット1枚"),
]

# --- ADHD向け・定期的に開きたくなる仕組み ---
def calc_task_streak(df_t, user=None):
    """連続でタスクを1回以上やった日数（今日から遡る）"""
    if df_t.empty or 'dt' not in df_t.columns:
        return 0
    today = date.today()
    streak = 0
    d = today
    
    # ストリーク保護チェック
    streak_protected = False
    if user:
        streak_protect_date = user.get('streak_protect_date') or ''
        if str(streak_protect_date) == str(today):
            streak_protected = True
    
    while True:
        cnt = len(df_t[df_t['dt'].dt.date == d])
        if cnt >= 1:
            streak += 1
            d -= timedelta(days=1)
        else:
            # 今日でタスクが0でも、ストリーク保護が有効ならカウント
            if d == today and streak_protected:
                streak += 1
                d -= timedelta(days=1)
            else:
                break
    return streak

# --- ペットのセリフ（励まし・昨日比・ADHD向け責めない言い回し） ---
PET_MESSAGES = [
    "今日も一緒に頑張ろう！",
    "少しずつで大丈夫だよ。",
    "君ならできる！",
    "休むのも大事だよ。",
    "いい調子だね！",
    "ダンジョン、深く潜ってるね。",
    "いつでも1つだけ、待ってるよ。",
    "無理しなくていいんだよ。",
]
PET_MESSAGES_ZERO = [
    "今日はまだクエストしてないね。1つだけやってみよう！ 小さく始めよう。",
    "いつでも始めていいよ。今日は1つだけでOK。",
    "やる気がなくても大丈夫。1つだけ、でいいんだよ。",
]
def get_pet_message(buddy_name, today_count, yesterday_count, task_streak=0, rest_today=False):
    if rest_today:
        return "今日は休息日だね。ゆっくりして。また明日、待ってるよ。"
    if today_count >= 3:
        return "デイリー達成！ すごい！ 今日はもう十分頑張ったね。"
    if today_count > yesterday_count and yesterday_count >= 0:
        return f"昨日は{yesterday_count}回だったけど、今日はもう{today_count}回！ すごい進んでる！"
    if today_count == 2:
        return "あと1つでデイリーだね！ でも2つでも十分頑張ってるよ。"
    if today_count == 1:
        return "1つできた！ それだけで今日はOKだよ。もうやらなくていいんだよ。"
    if today_count > 0:
        return random.choice(PET_MESSAGES)
    if task_streak > 0:
        return random.choice(["今日1つやれば連続キープだよ。無理しない範囲でね。", "連続記録、続いてるね。今日は1つだけ、どう？"]) + " " + random.choice(PET_MESSAGES_ZERO)
    return random.choice(PET_MESSAGES_ZERO)

# --- CSS: 確実に適用させるスタイル ---
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DotGothic16&display=swap');

/* 全体：ドット絵RPG風（メイン画面のデフォルト背景・ダンジョンでは上書き） */
.stApp {
    color: #e8e0d5 !important;
    font-family: 'DotGothic16', sans-serif;
    image-rendering: pixelated;
    image-rendering: -moz-crisp-edges;
    image-rendering: crisp-edges;
    /* メイン・ショップ等で常に表示する背景（薄いグリッド＋グラデ） */
    background: linear-gradient(180deg, #1a1a2e 0%, #2d2d44 50%, #1a1a2e 100%) !important;
    background-image:
        repeating-linear-gradient(0deg, transparent 0px, transparent 20px, rgba(139, 115, 85, 0.06) 20px, rgba(139, 115, 85, 0.06) 21px),
        repeating-linear-gradient(90deg, transparent 0px, transparent 20px, rgba(139, 115, 85, 0.06) 20px, rgba(139, 115, 85, 0.06) 21px),
        linear-gradient(180deg, #1a1a2e 0%, #2d2d44 50%, #1a1a2e 100%) !important;
    min-height: 100vh;
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

def _invalidate_sheet_cache():
    """シート更新後に呼ぶ（次回読みで再取得）"""
    if 'sheet_dirty' in st.session_state:
        st.session_state.sheet_dirty = True

def _int(val, default=0):
    """スプレッドシートから読み取った値を int に変換（文字列で来ても安全）"""
    if val is None or (isinstance(val, str) and str(val).strip() == ''):
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default

def _save_monthly_sr_claimed(ws_u, u_idx, month_id):
    """月1回SR確定チケット購入済みを記録（列W(23)）。失敗時はエラー表示。"""
    try:
        ws_u.update_cell(u_idx, 23, month_id)
    except Exception:
        st.error("SR確定チケットの購入記録に失敗しました。users の列W(23)に「last_monthly_sr_ticket」を追加してください。")
        st.stop()

def get_weekly_boss():
    week_num = datetime.now().isocalendar()[1]
    return WEEKLY_BOSSES[week_num % len(WEEKLY_BOSSES)]

def get_today_weak():
    """ボス弱点サイクル：日替わり（月=physical, 火=magic, 水=holy, 木=physical...）"""
    weak_list = ["physical", "magic", "holy"]
    return weak_list[date.today().weekday() % 3]

def get_today_weak_label():
    return {"physical": "物理", "magic": "魔法", "holy": "浄化"}.get(get_today_weak(), "?")

def get_biome_html(floor):
    # 100階層: 10階層ごとに背景が変わる
    f = min(max(1, int(floor)), MAX_FLOOR)
    biome_num = ((f - 1) // 10) + 1  # 1-10階=1, 11-20階=2, ...
    
    biomes = {
        1: ("biome-entrance", "🚪 入口の洞窟", "#1a1a2e", "#2d2d44"),
        2: ("biome-dark", "🌑 暗闇の回廊", "#0f0f1a", "#1a1a2e"),
        3: ("biome-stone", "🪨 石の迷宮", "#2a2a3a", "#3a3a4a"),
        4: ("biome-crystal", "💎 水晶の洞", "#1a1a3e", "#2a2a4e"),
        5: ("biome-lava", "🌋 溶岩の道", "#3a1a1a", "#4a2a2a"),
        6: ("biome-ice", "❄️ 氷の回廊", "#1a2a3a", "#2a3a4a"),
        7: ("biome-shadow", "👻 影の領域", "#0a0a1a", "#1a1a2a"),
        8: ("biome-magic", "✨ 魔法の間", "#2a1a3a", "#3a2a4a"),
        9: ("biome-abyss", "🌊 深淵の底", "#0a1a2a", "#1a2a3a"),
        10: ("biome-throne", "👑 王座の間", "#3a2a1a", "#4a3a2a"),
    }
    
    biome_data = biomes.get(biome_num, biomes[10])
    return biome_data[0], biome_data[1], biome_data[2], biome_data[3]

# ミニストーリー・フレーバーテキスト（4）
FLAVOR_BY_FLOOR = {
    1: "冒険の入口。一歩踏み出した。",
    10: "洞窟の奥に光が見えた。まだ続く。",
    25: "迷宮の中心。相棒が背中を押してくれる。",
    50: "半分を超えた。ここからが本当の試練だ。",
    75: "深淵が近い。でも、もう戻れない。",
    100: "最下層。王座の間。君はここまで来た。",
}
FLAVOR_BY_REBIRTH = {1: "初めての転生。世界が少し違って見える。", 5: "輪廻を重ねた者だけが知る、静かな力。"}

def get_flavor_text(floor, rebirth_count, total_tasks):
    """階層・転生・タスク数に応じた短いフレーバー"""
    f = min(max(1, int(floor)), 100)
    lines = []
    if f in FLAVOR_BY_FLOOR:
        lines.append(FLAVOR_BY_FLOOR[f])
    if rebirth_count in FLAVOR_BY_REBIRTH:
        lines.append(FLAVOR_BY_REBIRTH[rebirth_count])
    if total_tasks >= 100 and not lines:
        lines.append("百のクエストを超えた。君はもう、立派な冒険者だ。")
    return " ".join(lines) if lines else None

def check_achievements(user, df_t, df_i, ws_u, u_idx):
    """実績をチェックして未達成のものを返す（既に受取済みのものは除外）"""
    total_tasks = len(df_t[df_t['user_id']=='u001']) if not df_t.empty else 0
    floor = _int(user.get('dungeon_floor'))
    rebirth = _int(user.get('rebirth_count'))
    level = _int(user.get('level'), 1)
    streak = calc_task_streak(df_t, user)
    has_ur = False
    if not df_i.empty:
        user_items = df_i[df_i['user_id']=='u001']
        if not user_items.empty:
            has_ur = len(user_items[user_items['rarity']=='UR']) > 0
    
    # 既に受取済みの実績を取得
    achieved_str = user.get('achievements', '') or ''
    achieved_set = set([a.strip() for a in achieved_str.split(',') if a.strip()])
    new_achievements = []
    rewards = 0
    
    checks = [
        ("first_task", total_tasks >= 1),
        ("task_10", total_tasks >= 10),
        ("task_50", total_tasks >= 50),
        ("task_100", total_tasks >= 100),
        ("floor_10", floor >= 10),
        ("floor_50", floor >= 50),
        ("floor_100", floor >= 100),
        ("rebirth_1", rebirth >= 1),
        ("rebirth_5", rebirth >= 5),
        ("level_10", level >= 10),
        ("level_20", level >= 20),
        ("gacha_ur", has_ur),
        ("streak_7", streak >= 7),
        ("streak_30", streak >= 30),
    ]
    
    for ach_id, condition in checks:
        # 条件を満たしていて、かつまだ受取っていない場合のみ追加
        if condition and ach_id not in achieved_set:
            new_achievements.append(ach_id)
            if ach_id in ACHIEVEMENTS:
                rewards += ACHIEVEMENTS[ach_id]['reward']
    
    return new_achievements, rewards

def get_next_rewards(user, df_t, today_date):
    """次に獲得できる報酬を予告"""
    total_tasks = len(df_t[df_t['user_id']=='u001']) if not df_t.empty else 0
    floor = _int(user.get('dungeon_floor'))
    cur_xp = _int(user.get('current_xp'))
    nxt_xp = _int(user.get('next_level_xp'), 100)
    level = _int(user.get('level'), 1)
    d_cnt = len(df_t[df_t['dt'].dt.date == today_date]) if not df_t.empty else 0
    
    hints = []
    if cur_xp > 0 and nxt_xp > cur_xp:
        needed = nxt_xp - cur_xp
        hints.append(f"あと{needed} XPでレベルアップ！")
    if d_cnt < 3:
        hints.append(f"あと{3-d_cnt}タスクでデイリー達成（200G）")
    if floor < MAX_FLOOR:
        hints.append(f"あと{MAX_FLOOR-floor}階で転生可能")
    if total_tasks < 10:
        hints.append(f"あと{10-total_tasks}タスクで実績「継続の力」")
    return hints

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
    if not st.session_state.get('sheet_dirty', True) and 'cached_df_t' in st.session_state and 'cached_df_i' in st.session_state:
        df_t = st.session_state.cached_df_t.copy()
        df_i = st.session_state.cached_df_i.copy()
    else:
        df_t = pd.DataFrame(ws_t.get_all_records())
        df_i = pd.DataFrame(ws_i.get_all_records())
        st.session_state.cached_df_t = df_t
        st.session_state.cached_df_i = df_i
        st.session_state.sheet_dirty = False
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
    task_streak = calc_task_streak(df_t, user)
    month_start = today.replace(day=1)
    month_tasks_count = len(df_t[(df_t['user_id']=='u001') & (df_t['dt'].dt.date >= month_start)]) if not df_t.empty and 'dt' in df_t.columns else 0
    unlocked_str = (user.get('unlocked_titles') or '').strip()
    unlocked_set = set(x.strip() for x in unlocked_str.split(',') if x.strip())
    if task_streak >= 7 and 'streak_7' not in unlocked_set:
        unlocked_set.add('streak_7')
    if task_streak >= 30 and 'streak_30' not in unlocked_set:
        unlocked_set.add('streak_30')
    if month_tasks_count >= 50 and 'monthly_50' not in unlocked_set:
        unlocked_set.add('monthly_50')
    new_unlocked_str = ','.join(sorted(unlocked_set))
    if new_unlocked_str != unlocked_str:
        try:
            ws_u.update_cell(u_idx, 30, new_unlocked_str)
            _invalidate_sheet_cache()
        except Exception:
            pass
    
    # ログインボーナスチェック
    login_streak = _int(user.get('login_streak'))
    last_login = user.get('last_login') or user.get('_login') or ''
    is_new_login = (str(last_login) != str(today))
    login_bonus_gold = LOGIN_BONUS.get(login_streak + 1, 0) if is_new_login else 0
    
    # 実績チェック
    new_achievements, achievement_rewards = check_achievements(user, df_t, df_i, ws_u, u_idx)
    
    # 報酬予告
    reward_hints = get_next_rewards(user, df_t, today)
    
    # 期間限定イベント（例：週末ボーナス）
    is_weekend = today.weekday() >= 5  # 土日
    event_active = False
    event_name = ""
    event_desc = ""
    if is_weekend:
        event_active = True
        event_name = "週末ボーナスイベント"
        event_desc = "週末はタスク報酬が+20%アップ！"
    
    # 今日のタスク履歴（ハイライト用）
    today_tasks = []
    if not df_t.empty:
        today_tasks = df_t[df_t['dt'].dt.date == today]['task_name'].tolist()
    
    # 保留中のガチャチケット（ランダムボックスで獲得）
    pending_ticket = st.session_state.get('pending_gacha_ticket', False)
    if pending_ticket:
        st.markdown("""
        <div class="rpg-window" style="border-color: #fbbf24; background: rgba(50,40,20,0.95);">
            <h4 style="color: #ffecd2; margin: 0 0 8px 0;">🎫 ガチャチケット獲得！</h4>
            <p style="margin: 0; color: #c9b896;">ランダムボックスからガチャチケットを獲得しました！ ショップで使用できます。</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button("🎫 今すぐ使用する", key="use_pending_ticket"):
            m_key = gacha_draw()
            m_data = MONSTERS[m_key]
            df_i_check = pd.DataFrame(ws_i.get_all_records())
            already_has = not df_i_check.empty and len(df_i_check[(df_i_check['user_id']=='u001') & (df_i_check['item_name']==m_key)]) > 0
            if already_has:
                piece_gold = {"N": 10, "R": 30, "SR": 100, "SSR": 300, "UR": 1000}.get(m_data['rarity'], 10)
                new_gold = _int(user.get('gold')) + piece_gold
                ws_u.update_cell(u_idx, 6, new_gold)
                st.session_state.last_gacha_result = (m_key, m_data['rarity'], True, piece_gold)
                st.warning(f"重複！{m_key} → ピース変換で {piece_gold}G 獲得"); time.sleep(0.8); st.rerun()
            else:
                ws_i.append_row(['u001', m_key, m_data['rarity'], 1, str(datetime.now())])
                st.session_state.last_gacha_result = (m_key, m_data['rarity'], False, 0)
                st.session_state.pending_gacha_ticket = False
                st.success(f"{m_key} GET!"); time.sleep(0.8); st.rerun()

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
        login_streak = _int(user.get('login_streak'))
        # ADHD向け：今日の数字に集中
        st.markdown(f"""
        <div style="background: rgba(201, 162, 39, 0.25); border: 2px solid #c9a227; border-radius: 8px; padding: 8px; margin: 4px 0;">
            <p style="margin: 0; color: #ffecd2; font-size: 1rem; font-weight: bold;">📅 今日</p>
            <p style="margin: 0; color: #ffd700;">デイリー {d_cnt}/3 ｜ ウィークリー {w_cnt}/15</p>
            <p style="margin: 4px 0 0 0; color: #c9b896; font-size: 0.9em;">🔥 連続 {task_streak}日 ｜ ログイン {login_streak}日</p>
        </div>
        """, unsafe_allow_html=True)

    with col_h2:
        # バディ & おしゃべりペット
        buddy = user.get('equipped_pet', '') or ''
        if buddy in MONSTERS:
            b_data = MONSTERS[buddy]
            # モンスターのレベルを取得
            buddy_level = 1
            if not df_i.empty:
                buddy_items = df_i[(df_i['user_id']=='u001') & (df_i['item_name']==buddy)]
                if not buddy_items.empty:
                    buddy_level = _int(buddy_items.iloc[0].get('quantity', 1))
            
            c_b1, c_b2 = st.columns([1, 4])
            emoji, color = get_monster_display(buddy, b_data['rarity'])
            c_b1.markdown(f'<div style="font-size: 64px; text-align: center; background: {color}20; border-radius: 8px; padding: 8px;">{emoji}</div>', unsafe_allow_html=True)
            rest_today = (str(user.get('streak_protect_date')) == str(today) and d_cnt == 0)
            pet_says = get_pet_message(buddy, d_cnt, yesterday_cnt, task_streak, rest_today)
            st.markdown(f"<div class='pet-speech'><strong>{buddy}</strong> (Lv.{buddy_level})「{pet_says}」</div>", unsafe_allow_html=True)
            skill_desc = b_data.get('skill_desc', b_data.get('skill_name', b_data['skill']))
            level_bonus = f" (レベル{buddy_level}で効果+{(buddy_level-1)*5}%)" if buddy_level > 1 else ""
            st.caption(f"効果: {skill_desc}{level_bonus}")
            # おでかけ・放置報酬（2）
            outing_start_raw = (user.get('outing_start') or '').strip()
            try:
                outing_start_dt = datetime.fromisoformat(outing_start_raw) if outing_start_raw else None
            except Exception:
                outing_start_dt = None
            if outing_start_dt is None:
                if st.button("🔄 相棒をおでかけに出す", key="outing_start"):
                    try:
                        ws_u.update_cell(u_idx, 35, datetime.now().isoformat())
                        _invalidate_sheet_cache()
                        st.success("おでかけに出した。しばらくしたら迎えにいこう。"); st.rerun()
                    except Exception:
                        st.caption("outing_start列(35)を追加すると使えます")
            else:
                elapsed = (datetime.now() - outing_start_dt).total_seconds() / 3600
                reward = min(60, int(elapsed * 2))
                if st.button("🏠 迎えに行く", key="outing_end"):
                    try:
                        ws_u.update_cell(u_idx, 35, "")
                        ws_u.update_cell(u_idx, 6, _int(user.get('gold')) + reward)
                        _invalidate_sheet_cache()
                        st.success(f"おかえり！ {reward}G おみやげ"); time.sleep(1); st.rerun()
                    except Exception:
                        st.caption("列35を空にすると戻ります")
                st.caption(f"おでかけ中（約{int(elapsed*60)}分経過・最大{reward}G）")
        else:
            st.info("Buddy: なし (ショップで召喚しよう。相棒がいると励ましてくれるよ)")

    # ストリーク保護：今月の使用状況（ADHD向け）
    streak_protect_used_this_month = False
    if user.get('streak_protect_date'):
        try:
            spd = str(user.get('streak_protect_date'))[:7]  # YYYY-MM
            streak_protect_used_this_month = (spd == f"{today.year}-{today.month:02d}")
        except Exception:
            pass
    st.caption(f"🛡️ ストリーク保護: {'今月使用済み' if streak_protect_used_this_month else '未使用（ショップで購入可）'}")

    # ストリーク保護警告（連続タスクが途切れそうな時）
    if task_streak > 0 and d_cnt == 0:
        st.markdown(f"""
        <div class="rpg-window" style="border-color: #f59e0b; background: rgba(50,40,20,0.95);">
            <h4 style="color: #ffecd2; margin: 0 0 8px 0;">⚠️ ストリーク保護</h4>
            <p style="margin: 0; color: #c9b896;">現在{task_streak}日連続中！ 今日1つでもタスクを完了すれば継続できます。</p>
        </div>
        """, unsafe_allow_html=True)
    
    # ログインボーナス表示・受取
    if is_new_login and login_bonus_gold > 0:
        st.markdown(f"""
        <div class="rpg-window" style="border-color: #c9a227; background: rgba(40,32,24,0.95);">
            <h3 style="color: #ffecd2; margin: 0 0 8px 0;">🎁 ログインボーナス Day {login_streak + 1}</h3>
            <p style="margin: 0; color: #c9b896;">連続ログイン {login_streak + 1}日目！ {login_bonus_gold}G 獲得！</p>
        </div>
        """, unsafe_allow_html=True)
        if st.button(f"🎁 {login_bonus_gold}G を受け取る", key="login_bonus"):
            try:
                # 先にlast_loginを更新してから報酬を追加（重複防止）
                ws_u.update_cell(u_idx, 9, login_streak + 1)  # login_streak
                ws_u.update_cell(u_idx, 10, str(today))  # last_loginを先に更新
                new_gold = _int(user.get('gold')) + login_bonus_gold
                ws_u.update_cell(u_idx, 6, new_gold)
                st.success(f"{login_bonus_gold}G 獲得！"); _invalidate_sheet_cache(); time.sleep(0.2); st.rerun()
            except Exception as e:
                st.error(f"ログインボーナスの保存に失敗しました。スプレッドシートの列I(9)に「login_streak」、列J(10)に「last_login」列があるか確認してください。エラー: {str(e)}")
                st.stop()
    
    # 実績達成通知（コンパクトに）
    # スプレッドシートから既に受取済みの実績を取得
    achieved_str = user.get('achievements', '') or ''
    achieved_set = set([a.strip() for a in achieved_str.split(',') if a.strip()])
    # new_achievementsから既に受取済みのものを除外
    unclaimed_achievements = [a for a in new_achievements if a not in achieved_set]
    
    if unclaimed_achievements:
        unclaimed_rewards = sum(ACHIEVEMENTS.get(a, {}).get('reward', 0) for a in unclaimed_achievements if a in ACHIEVEMENTS)
        if unclaimed_rewards > 0:
            st.markdown(f"""
            <div class="rpg-window" style="border-color: #fbbf24; background: rgba(50,40,20,0.95); margin-bottom: 8px;">
                <h4 style="color: #ffecd2; margin: 0 0 4px 0;">🏆 実績達成！</h4>
                <p style="margin: 0; color: #c9b896; font-size: 0.9em;">{', '.join([ACHIEVEMENTS.get(a, {}).get('name', a) for a in unclaimed_achievements[:3]])}{'...' if len(unclaimed_achievements) > 3 else ''}</p>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"🎁 実績報酬 {unclaimed_rewards}G を受け取る", key="achievement_reward"):
                # まずスプレッドシートを更新してから報酬を追加（重複防止）
                new_achieved_str = ','.join(list(achieved_set) + unclaimed_achievements).strip(',')
                try:
                    ws_u.update_cell(u_idx, 25, new_achieved_str)  # achievements列を先に更新
                    # 更新が成功したことを確認
                    new_gold = _int(user.get('gold')) + unclaimed_rewards
                    ws_u.update_cell(u_idx, 6, new_gold)
                    st.success(f"{unclaimed_rewards}G 獲得！"); _invalidate_sheet_cache(); time.sleep(0.2); st.rerun()
                except Exception as e:
                    st.error(f"実績報酬の保存に失敗しました。スプレッドシートの列Y(25)に「achievements」列があるか確認してください。エラー: {str(e)}")
                    st.stop()
    
    # ADHD向け：報酬予告を常に1行で（あと〇で〇〇）
    next_reward_lines = []
    if d_cnt < 3:
        next_reward_lines.append(f"あと{3-d_cnt}タスクでデイリー200G")
    if w_cnt < 15:
        next_reward_lines.append(f"あと{15-w_cnt}でウィークリー500G")
    if reward_hints:
        next_reward_lines.extend(reward_hints[:2])
    if next_reward_lines:
        st.markdown(f"""
        <div class="rpg-window" style="margin-bottom: 8px; border-color: #60a5fa; padding: 10px;">
            <p style="margin: 0; color: #ffecd2; font-weight: bold;">💡 今やるとお得 — {' ｜ '.join(next_reward_lines[:3])}</p>
        </div>
        """, unsafe_allow_html=True)
    
    # 期間限定イベント表示
    if event_active:
        st.markdown(f"""
        <div class="rpg-window" style="border-color: #fbbf24; background: rgba(50,40,20,0.95); margin-bottom: 12px;">
            <h4 style="color: #ffecd2; margin: 0 0 8px 0;">🎉 {event_name}</h4>
            <p style="margin: 0; color: #c9b896;">{event_desc}</p>
        </div>
        """, unsafe_allow_html=True)
    
    # 今日のハイライト（小さな成功の可視化 - ADHD向け）
    if today_tasks:
        st.markdown("""
        <div class="rpg-window" style="margin-bottom: 12px; border-color: #2ECC40;">
            <h4 style="margin: 0 0 8px 0; color: #2ECC40;">✨ 今日やったこと（小さな成功の記録）</h4>
        </div>
        """, unsafe_allow_html=True)
        for task in today_tasks:
            st.markdown(f"""
            <div style="background: rgba(46, 204, 64, 0.1); border-left: 4px solid #2ECC40; padding: 8px; margin: 4px 0; border-radius: 4px;">
                <p style="margin: 0; color: #fff;">✅ {task}</p>
            </div>
            """, unsafe_allow_html=True)
        if d_cnt > 0:
            st.markdown(f"""
            <div style="background: rgba(255, 215, 0, 0.2); border: 2px solid #ffd700; border-radius: 8px; padding: 12px; margin: 8px 0; text-align: center;">
                <p style="margin: 0; color: #ffd700; font-size: 1.2rem; font-weight: bold;">🎉 今日は{d_cnt}つもクリアした！ すごい！</p>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("---")

    # --- 2. アクション (タスク) ---
    # ADHD向け：今やること1つ（ピン留め or おすすめ）
    if "adhd_pinned_task" not in st.session_state or st.session_state.adhd_pinned_task not in TASKS:
        st.session_state.adhd_pinned_task = random.choice(list(TASKS.keys())) if TASKS else ""
    rec_task = st.session_state.adhd_pinned_task
    task_list = list(TASKS.keys())
    week_rot = (today.isocalendar()[1]) % 5  # 週替わりローテーション
    motivation_sets = [
        ["💪 1つだけでも大丈夫！ 小さく始めよう", "🎯 今日は1つだけ。それだけで十分だよ"],
        ["🌟 完璧を目指さなくてOK。1つできたらそれでOK！", "✨ 5分だけでもいい。始めることが大切"],
        ["💫 小さな一歩が大きな変化につながる", "いつでも1つだけ、待ってるよ"],
        ["今日はこれだけやればOK。決めよう。", "1つやったら、今日は終わりにしてもいいよ"],
        ["始めることが一番えらい。", "無理しないで。1つでいいんだよ"],
    ]
    motivation = motivation_sets[week_rot][today.day % 2] if motivation_sets else "1つだけやってみよう"
    
    st.markdown(f"""
    <div class="rpg-window" style="margin-bottom: 12px; border-color: #2ECC40;">
        <h3 style="margin: 0 0 8px 0; color: #2ECC40;">🎯 今日のこれだけ（1つやればOK）</h3>
        <p style="margin: 0; color: #ffecd2; font-size: 1.2rem; font-weight: bold;">{rec_task}</p>
        <p style="margin: 4px 0 0 0; color: #c9b896; font-size: 0.9em;">{motivation}</p>
    </div>
    """, unsafe_allow_html=True)
    if st.button("🔄 おすすめを別のタスクに変える", key="change_pinned_task"):
        st.session_state.adhd_pinned_task = random.choice(list(TASKS.keys())) if TASKS else rec_task
        st.rerun()
    
    # ボディダブリング風：相棒もいま〇〇をやってるよ
    body_double_task = random.choice(task_list) if task_list else "偵察任務"
    st.caption(f"👥 相棒もいま「{body_double_task}」に取り組んでるよ。一緒にやっている気分で。")
    
    st.markdown(f"""
    <div class="rpg-window" style="margin-bottom: 12px; border-color: #60a5fa;">
        <h3 style="margin: 0 0 8px 0;">⚔️ クエストボード ― 行動を選べ</h3>
        <p style="margin: 0; color: #c9b896; font-size: 0.9em;">タスクを完了してゴールドと経験値を得よう</p>
        <p style="margin: 8px 0 0 0; color: #8b7355; font-size: 0.85em;">💡 かんたんタスクは始めやすい。むずかしいは報酬多め。</p>
    </div>
    """, unsafe_allow_html=True)
    
    # デイリー進捗の視覚化（ADHD向け）
    if d_cnt < 3:
        remaining = 3 - d_cnt
        first_bonus_note = "（最初の1つは初動ボーナス1.5倍！）" if d_cnt == 0 else ""
        st.markdown(f"""
        <div style="background: rgba(201, 162, 39, 0.2); border: 2px solid #c9a227; border-radius: 8px; padding: 12px; margin-bottom: 12px;">
            <p style="margin: 0; color: #ffecd2; font-size: 1.1rem; font-weight: bold;">
                🎯 デイリー達成まで あと{remaining}タスク！ {first_bonus_note}
            </p>
            <div class="bar-bg" style="height: 16px; margin-top: 8px;">
                <div class="bar-fill-xp" style="width: {min(100, d_cnt/3*100)}%; height: 100%; background: linear-gradient(90deg, #c9a227, #fbbf24);"></div>
            </div>
            <p style="margin: 4px 0 0 0; color: #c9b896; font-size: 0.9em;">進捗: {d_cnt}/3 ({int(d_cnt/3*100)}%)</p>
        </div>
        """, unsafe_allow_html=True)
    if d_cnt == 0:
        st.markdown("""
        <div style="background: rgba(255, 215, 0, 0.2); border: 2px solid #ffd700; border-radius: 8px; padding: 10px; margin-bottom: 12px; text-align: center;">
            <p style="margin: 0; color: #ffd700; font-weight: bold;">🌟 初動ボーナス — あと1タスクでゲット！ 最初の1つで報酬1.5倍</p>
        </div>
        """, unsafe_allow_html=True)
    c1, c2, c3 = st.columns(3)
    cols = [c1, c2, c3]
    
    # タスク見た目カスタム（14）：列33 task_custom (JSON)
    task_custom = {}
    try:
        tc_raw = (user.get('task_custom') or '').strip()
        if tc_raw:
            task_custom = json.loads(tc_raw) if isinstance(tc_raw, str) else tc_raw
    except Exception:
        pass
    for i, (t_name, t_data) in enumerate(TASKS.items()):
        display_name = task_custom.get(t_name, t_name)
        diff = t_data.get("difficulty", "normal")
        mult = DIFFICULTY_MULT.get(diff, 1.0)
        base_reward = int(t_data['reward'] * mult)
        diff_label = DIFFICULTY_LABEL.get(diff, "")
        btn_label = f"{display_name}\n💰 {base_reward}G [{diff_label}]"
        if cols[i%3].button(btn_label, use_container_width=True, key=f"task_btn_{i}", help=f"{t_data['desc']} - {diff_label} 報酬: {base_reward}G"):
            # 計算ロジック（難易度倍率を先に適用）
            diff_mult = DIFFICULTY_MULT.get(t_data.get('difficulty', 'normal'), 1.0)
            base = int(t_data['reward'] * diff_mult)
            bonus = 1.0
            logs = []
            
            # ジョブ
            if job_info['bonus'] == "ALL_RANDOM":
                if random.random() < 0.5: bonus = 2.0; logs.append("🎰 JACKPOT!")
                else: bonus = 0.1; logs.append("💀 失敗...")
            elif job_info['bonus'] == t_data['type']:
                bonus = 1.5; logs.append("⚔️ 職適正!")
            
            # ペット（レベルアップ効果を適用）
            if buddy in MONSTERS:
                pskill = MONSTERS[buddy]['skill']
                # モンスターのレベルを取得
                buddy_level = 1
                if not df_i.empty:
                    buddy_items = df_i[(df_i['user_id']=='u001') & (df_i['item_name']==buddy)]
                    if not buddy_items.empty:
                        buddy_level = _int(buddy_items.iloc[0].get('quantity', 1))
                # レベルに応じた効果（レベル1で1.1倍、最大レベル10で1.5倍）
                level_multiplier = 1.0 + (buddy_level - 1) * 0.05
                if pskill == 'gold_up': 
                    bonus *= (1.1 * level_multiplier)
                    logs.append(f"💰 金運 Lv.{buddy_level}")
                if pskill == 'xp_up': 
                    bonus *= (1.1 * level_multiplier)
                    logs.append(f"✨ 応援 Lv.{buddy_level}")
            
            val = int(base * bonus)
            if val < 1: val = 1
            
            # 今日の最初のタスクボーナス（ADHD向け：始めるご褒美）
            is_first_today = (d_cnt == 0)
            if is_first_today:
                val = max(1, int(val * 1.5))
                logs.append("🌟初タスク!")
            # 連続クリアボーナス（同日2つ目+10G、3つ目+20G）
            if d_cnt == 1:
                val += 10
                logs.append("🔥2つ目+10G")
            elif d_cnt == 2:
                val += 20
                logs.append("🔥3つ目+20G")
            
            # 転生ボーナス（永久）
            rebirth_count = int(user.get('rebirth_count') or 0)
            if rebirth_count > 0:
                rebirth_bonus = 1 + 0.1 * rebirth_count
                val = max(1, int(val * rebirth_bonus))
                logs.append("✨転生")
            # 限定称号ボーナス（5）
            if 'streak_7' in unlocked_set:
                val = max(1, int(val * 1.05))
                logs.append("🏅7日連続")
            if 'streak_30' in unlocked_set:
                val = max(1, int(val * 1.10))
                logs.append("🏅30日連続")
            if 'monthly_50' in unlocked_set:
                val = max(1, int(val * 1.05))
                logs.append("🏅今月50")
            
            # 週末イベントボーナス
            if event_active:
                val = max(1, int(val * 1.2))
                logs.append("🎉 週末ボーナス!")
            
            # 天気・曜日ボーナス（3）
            weekday_bonus = 1.0
            if today.weekday() == 0:  # 月曜
                weekday_bonus = 1.1
                logs.append("📅 月曜ボーナス!")
            elif today.weekday() == 4:  # 金曜
                weekday_bonus = 1.05
                logs.append("📅 金曜ボーナス!")
            val = max(1, int(val * weekday_bonus))
            # 擬似天気（ランダム）：室内=magic/holy 室外=physical
            weather_today = random.choice(["sunny", "rainy", "cloudy"])
            if weather_today == "rainy" and t_data['type'] in ("magic", "holy"):
                val = max(1, int(val * 1.05))
                logs.append("🌧 雨の日室内ボーナス!")
            elif weather_today == "sunny" and t_data['type'] == "physical":
                val = max(1, int(val * 1.05))
                logs.append("☀ 晴れ外出ボーナス!")
            
            # ボス（弱点サイクル：日替わり）（6）
            w_boss = get_weekly_boss()
            today_weak = ["physical", "magic", "holy"][today.weekday() % 3]
            is_weak = (t_data['type'] == today_weak)
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

            # ランダム報酬ボックス（5%の確率）
            random_box_reward = None
            if random.random() < 0.05:
                box_type, box_amount, box_msg = random.choice(RANDOM_BOX_REWARDS)
                random_box_reward = (box_type, box_amount, box_msg)
                if box_type == "gold":
                    final_gold += box_amount
                elif box_type == "xp":
                    new_xp += box_amount
                elif box_type == "gacha":
                    # ガチャチケットは後で処理（セッション状態に保存）
                    st.session_state.pending_gacha_ticket = True
            
            ws_u.update_cell(u_idx, 6, final_gold)
            ws_u.update_cell(u_idx, 4, new_xp)
            ws_u.update_cell(u_idx, 8, new_floor)
            ws_u.update_cell(u_idx, 19, new_boss_dmg)
            ws_t.append_row([str(uuid.uuid4()), 'u001', t_name, t_data['type'], 1, 'Completed', str(datetime.now())])
            _invalidate_sheet_cache()
            ts = datetime.now().strftime('%H:%M')
            st.session_state.battle_log.insert(0, f"[{ts}] {t_name}: {val}G " + " ".join(logs))
            
            # ADHD向け：大きなフィードバックと達成感
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 16px; padding: 32px; text-align: center; margin: 20px 0; box-shadow: 0 8px 32px rgba(102, 126, 234, 0.4);">
                <h1 style="font-size: 3rem; margin: 0; color: #fff; text-shadow: 2px 2px 4px rgba(0,0,0,0.5);">🎉 タスク完了！</h1>
                <p style="font-size: 2rem; margin: 16px 0; color: #ffd700; font-weight: bold;">+{val} G 獲得！</p>
                <p style="font-size: 1.2rem; margin: 8px 0; color: #fff;">{" ".join(logs)}</p>
            </div>
            """, unsafe_allow_html=True)
            st.balloons()
            st.toast(f"✨ +{val} G 獲得！", icon="💰")
            if is_first_today:
                st.markdown("""
                <div style="background: rgba(255, 215, 0, 0.2); border: 2px solid #ffd700; border-radius: 8px; padding: 16px; margin: 16px 0; text-align: center;">
                    <h3 style="color: #ffd700; margin: 0;">🌟 今日の最初の1つ、クリア！</h3>
                    <p style="color: #fff; margin: 8px 0 0 0;">その調子！ あと2つでデイリー達成だよ！</p>
                </div>
                """, unsafe_allow_html=True)
                st.toast("🌟 今日の最初の1つ、クリア！ その調子！", icon="⭐")
            if event_gold != 0:
                st.toast(f"{event_msg} {'+' if event_gold > 0 else ''}{event_gold} G", icon="📦" if event_gold > 0 else "⚠️")
            if random_box_reward:
                st.markdown(f"""
                <div style="background: rgba(255, 192, 203, 0.3); border: 2px solid #ff69b4; border-radius: 8px; padding: 16px; margin: 16px 0; text-align: center;">
                    <h3 style="color: #ff69b4; margin: 0;">🎁 サプライズボックス！</h3>
                    <p style="color: #fff; margin: 8px 0 0 0;">{random_box_reward[2]}</p>
                </div>
                """, unsafe_allow_html=True)
                st.toast(f"🎁 サプライズボックス！ {random_box_reward[2]}", icon="🎁")
            
            # ミッション進捗チェック（セッション状態に保存して次回表示）
            new_d_cnt = d_cnt + 1
            st.session_state.mission_check = {
                "daily_count": new_d_cnt,
                "weekly_count": w_cnt + 1,
                "today": str(today)
            }
            
            # 小さな成功の可視化（ADHD向け）
            if new_d_cnt == 1:
                st.info("💪 **1つ完了！** あと2つでデイリー達成！")
            elif new_d_cnt == 2:
                st.warning("🔥 **2つ完了！** あと1つでデイリー達成！ もう少し！")
            elif new_d_cnt >= 3:
                st.success("🎯 **デイリー達成！** すごい！ 報酬を受け取ろう！")
            
            # ADHD向け：次のタスクへの動機付け + 「もう1つ」or「今日はここまで」
            if new_d_cnt < 3:
                st.markdown(f"""
                <div style="background: rgba(102, 126, 234, 0.2); border: 2px solid #667eea; border-radius: 8px; padding: 16px; margin: 16px 0; text-align: center;">
                    <p style="color: #fff; margin: 0; font-size: 1.1rem;">💪 すごい！ あと{3-new_d_cnt}つでデイリー達成だよ！</p>
                    <p style="color: #c9b896; margin: 8px 0 0 0; font-size: 0.9em;">でも、今やめたって全然OK。無理しないでね。</p>
                </div>
                """, unsafe_allow_html=True)
            st.markdown("**次はどうする？**")
            c_again, c_done = st.columns(2)
            with c_again:
                if st.button("もう1つやる", key="one_more_task"):
                    _invalidate_sheet_cache()
                    st.rerun()
            with c_done:
                if st.button("今日はここまでにする", key="done_for_today"):
                    st.success("よく頑張った！ また明日。無理しないでね。")
                    time.sleep(1.2)
                    _invalidate_sheet_cache()
                    st.rerun()
            st.stop()

    # ADHD向け：優しいリマインダー（責めない文言）
    reminder_messages = []
    if d_cnt < 3:
        reminder_messages.append(f"デイリーあと{3-d_cnt}つで200Gだよ。")
    if w_cnt < 15:
        reminder_messages.append(f"あと{15-w_cnt}でウィークリー500G。")
    reminder_messages.extend(["ログイン続けてるとボーナスもらえるよ。", "相棒が待ってるよ。1つだけ、どう？"])
    gentle_msg = random.choice(reminder_messages) if reminder_messages else "また明日、待ってるよ。"
    st.markdown(f"""
    <div style="background: rgba(96, 165, 250, 0.15); border-left: 4px solid #60a5fa; padding: 10px; margin: 12px 0; border-radius: 4px;">
        <p style="margin: 0; color: #c9b896; font-size: 0.9em;">💬 {gentle_msg}</p>
    </div>
    """, unsafe_allow_html=True)

    # 「今日は休息にする」（週1回・ストリーク保護と同じ効果）
    last_rest_week = (str(user.get('last_rest_week') or '')).strip()
    can_rest_today = (last_rest_week != wk_id)
    if can_rest_today and d_cnt == 0:
        if st.button("😌 今日は休息にする（週1回・連続記録キープ）", key="rest_day_btn"):
            try:
                ws_u.update_cell(u_idx, 29, wk_id)   # last_rest_week
                ws_u.update_cell(u_idx, 28, str(today))  # streak_protect_date
                st.success("お疲れさま。今日はゆっくり休んで。また明日、待ってるよ。"); _invalidate_sheet_cache(); time.sleep(1.5); st.rerun()
            except Exception:
                st.info("休息日は今週すでに使用済みか、保存できませんでした。列AC(29)に last_rest_week を追加してください。")
    # ゾーンタイム（10）：集中開始・終了で記録
    zone_start_raw = (user.get('zone_start') or '').strip()
    zone_log_raw = (user.get('zone_log') or '').strip()
    try:
        zone_start_dt = datetime.fromisoformat(zone_start_raw) if zone_start_raw else None
    except Exception:
        zone_start_dt = None
    zone_col1, zone_col2 = st.columns(2)
    with zone_col1:
        if zone_start_dt is None:
            if st.button("⏱️ 集中開始", key="zone_start_btn"):
                try:
                    ws_u.update_cell(u_idx, 31, datetime.now().isoformat())
                    _invalidate_sheet_cache()
                    st.rerun()
                except Exception:
                    st.caption("zone_start列(31)を追加すると使えます")
        else:
            if st.button("⏱️ 集中終了", key="zone_end_btn"):
                try:
                    end = datetime.now()
                    mins = max(0, int((end - zone_start_dt).total_seconds() // 60))
                    new_log = (zone_log_raw + "," if zone_log_raw else "") + f"{end.date()}:{mins}"
                    ws_u.update_cell(u_idx, 31, "")  # clear start
                    ws_u.update_cell(u_idx, 32, new_log[:500])  # cap length
                    _invalidate_sheet_cache()
                    st.success(f"今回 {mins} 分集中しました"); time.sleep(1); st.rerun()
                except Exception:
                    st.caption("zone_start(31)/zone_log(32)列を追加すると使えます")
    with zone_col2:
        if zone_log_raw:
            parts = [p for p in zone_log_raw.split(",") if ":" in p]
            today_parts = [p for p in parts if p.startswith(str(today))]
            today_mins = sum(int(p.split(":")[-1]) for p in today_parts if p.split(":")[-1].isdigit())
            st.caption(f"今日の集中: {today_mins} 分")
        elif zone_start_dt:
            st.caption("集中中… 終了ボタンで記録")

    # 「今日はやめる」逃げ道
    if st.button("🏁 今日はここまでにする（また明日）", key="done_today_no_task"):
        st.balloons()
        st.success(f"また明日。ストリーク{task_streak}日キープ中。無理しないでね。")
        _invalidate_sheet_cache()
        time.sleep(1.5)
        st.rerun()
    # 25分チャレンジ（やったら押す→小さな報酬・1日1回）
    if st.button("⏱️ 25分集中した！ 報酬を受け取る（10G）", key="pomodoro_claim"):
        try:
            already = st.session_state.get("pomodoro_date") == str(today)
            if not already:
                st.session_state["pomodoro_date"] = str(today)
                ws_u.update_cell(u_idx, 6, _int(user.get('gold')) + 10)
                st.success("25分集中お疲れさま！ +10G"); _invalidate_sheet_cache(); time.sleep(0.8); st.rerun()
            else:
                st.info("今日はすでに受け取り済みです。また明日！")
        except Exception:
            st.info("受け取れませんでした。")

    # --- 3. ダンジョン & ボス ---
    floor = min(MAX_FLOOR, max(1, _int(user.get('dungeon_floor'))))
    b_class, b_name, bg_color1, bg_color2 = get_biome_html(floor)
    
    # 階層に応じたダンジョンの雰囲気テキスト
    biome_flavors = {
        1: ["入口の洞窟が広がる", "薄暗い光が差し込む", "足音が響く"],
        2: ["暗闇が深まる", "何かが動く気配が", "冷たい空気が流れる"],
        3: ["石の壁が続く", "迷宮のような構造", "どこかで水が滴る"],
        4: ["水晶が輝いている", "神秘的な光が満ちる", "静寂が支配する"],
        5: ["熱気が立ち込める", "溶岩の音が響く", "危険な雰囲気"],
        6: ["氷が張りつめている", "冷気が肌を刺す", "白い世界が広がる"],
        7: ["影が蠢いている", "不気味な静けさ", "闇が深まる"],
        8: ["魔法の光が舞う", "不思議な力が満ちる", "幻想的な空間"],
        9: ["深淵の底へ", "圧迫感が増す", "未知の領域"],
        10: ["王座の間へ", "最終領域", "魔王が待つ"],
    }
    biome_num = ((floor - 1) // 10) + 1
    flavors = biome_flavors.get(biome_num, biome_flavors[10])
    dungeon_flavor = random.choice(flavors)
    
    # 動的に背景を設定（RPGダンジョン風 - より本格的）
    st.markdown(f"""
    <style>
    .stApp {{
        background: linear-gradient(180deg, {bg_color1} 0%, {bg_color2} 100%) !important;
        background-image:
            /* レンガ・石の壁の質感（縦横の線） */
            repeating-linear-gradient(90deg, 
                rgba(0,0,0,0.15) 0px, rgba(0,0,0,0.15) 1px,
                transparent 1px, transparent 4px,
                rgba(0,0,0,0.08) 4px, rgba(0,0,0,0.08) 5px,
                transparent 5px, transparent 8px,
                rgba(0,0,0,0.12) 8px, rgba(0,0,0,0.12) 9px,
                transparent 9px, transparent 12px
            ),
            repeating-linear-gradient(0deg, 
                rgba(0,0,0,0.15) 0px, rgba(0,0,0,0.15) 1px,
                transparent 1px, transparent 4px,
                rgba(0,0,0,0.08) 4px, rgba(0,0,0,0.08) 5px,
                transparent 5px, transparent 8px,
                rgba(0,0,0,0.12) 8px, rgba(0,0,0,0.12) 9px,
                transparent 9px, transparent 12px
            ),
            /* レンガのブロックパターン（斜めの線） */
            repeating-linear-gradient(45deg, 
                transparent 0px, transparent 24px,
                rgba(0,0,0,0.05) 24px, rgba(0,0,0,0.05) 25px,
                transparent 25px, transparent 48px
            ),
            repeating-linear-gradient(-45deg, 
                transparent 0px, transparent 24px,
                rgba(0,0,0,0.05) 24px, rgba(0,0,0,0.05) 25px,
                transparent 25px, transparent 48px
            ),
            /* 暗闇の雰囲気（控えめに・コンテンツを隠さない） */
            radial-gradient(ellipse at 20% 15%, rgba(0,0,0,0.25) 0%, transparent 60%),
            radial-gradient(ellipse at 80% 85%, rgba(0,0,0,0.2) 0%, transparent 60%),
            radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0.15) 0%, transparent 80%),
            /* 松明・光の効果（ダンジョンらしさ） */
            radial-gradient(circle at 15% 25%, rgba(139, 115, 85, 0.25) 0%, transparent 35%),
            radial-gradient(circle at 85% 75%, rgba(201, 162, 39, 0.2) 0%, transparent 35%),
            radial-gradient(circle at 50% 10%, rgba(139, 115, 85, 0.15) 0%, transparent 30%),
            /* 床の石の質感 */
            repeating-linear-gradient(0deg, 
                rgba(0,0,0,0.2) 0px, rgba(0,0,0,0.2) 1px,
                transparent 1px, transparent 16px,
                rgba(0,0,0,0.1) 16px, rgba(0,0,0,0.1) 17px,
                transparent 17px, transparent 32px
            ),
            repeating-linear-gradient(90deg, 
                rgba(0,0,0,0.15) 0px, rgba(0,0,0,0.15) 1px,
                transparent 1px, transparent 16px,
                rgba(0,0,0,0.08) 16px, rgba(0,0,0,0.08) 17px,
                transparent 17px, transparent 32px
            ),
            /* 壁のひび割れ風 */
            repeating-linear-gradient(30deg, 
                transparent 0px, transparent 40px,
                rgba(0,0,0,0.03) 40px, rgba(0,0,0,0.03) 41px,
                transparent 41px, transparent 80px
            ),
            repeating-linear-gradient(-30deg, 
                transparent 0px, transparent 40px,
                rgba(0,0,0,0.03) 40px, rgba(0,0,0,0.03) 41px,
                transparent 41px, transparent 80px
            ) !important;
        position: relative;
    }}
    /* 背景レイヤーは背面に（コンテンツを隠さない） */
    .stApp::before {{
        content: '';
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: repeating-linear-gradient(45deg, transparent 0px, transparent 48px, rgba(139, 115, 85, 0.03) 48px, rgba(139, 115, 85, 0.03) 49px, transparent 49px, transparent 96px);
        pointer-events: none;
        z-index: -1;
    }}
    .stApp::after {{
        content: '';
        position: fixed;
        top: 0; left: 0; right: 0; bottom: 0;
        background: radial-gradient(circle at 25% 30%, rgba(201, 162, 39, 0.08) 0%, transparent 25%), radial-gradient(circle at 75% 70%, rgba(139, 115, 85, 0.06) 0%, transparent 25%);
        pointer-events: none;
        z-index: -1;
    }}
    /* 本文エリアを前面に */
    .stApp [data-testid="stAppViewContainer"],
    .stApp .main .block-container {{ position: relative; z-index: 1; }}
    </style>
    """, unsafe_allow_html=True)
    
    rebirth_count = int(user.get('rebirth_count') or 0)
    total_tasks = len(df_t[df_t['user_id']=='u001']) if not df_t.empty else 0
    flavor_line = get_flavor_text(floor, rebirth_count, total_tasks)
    flavor_html = f'<p style="margin: 8px 0 0 0; font-size: 0.85em; color: #c9a227; font-style: italic;">📜 {flavor_line}</p>' if flavor_line else ""
    st.markdown(f"""
    <div class="{b_class}">
        <h3>📍 {b_name} (階層 {floor}/{MAX_FLOOR})</h3>
        <p style="margin: 4px 0 0 0; font-size: 0.9em; opacity: 0.9;">{dungeon_flavor}</p>
        {flavor_html}
    </div>
    """, unsafe_allow_html=True)
    
    # 100階到達: 転生パネル（rebirth_count は G列(7), title は U列(21) に書き込みます）
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
        boss_dmg = _int(user.get('weekly_boss_damage'))
        boss_cur = max(0, boss_max - boss_dmg)
        boss_pct = (boss_cur / boss_max) * 100
        boss_defeated = (boss_cur == 0)
        boss_claimed = (str(user.get('boss_claimed')) == wk_id)
        
        c_boss1, c_boss2 = st.columns([1, 2])
        with c_boss1:
            emoji, color = get_monster_display(w_boss['name'], "UR")
            st.markdown(f'<div style="font-size: 96px; text-align: center; background: {color}20; border-radius: 8px; padding: 16px;">{emoji}</div>', unsafe_allow_html=True)
        with c_boss2:
            st.markdown(f"**☠️ WANTED: {w_boss['name']}**")
            st.markdown(f"""<div class="bar-bg"><div class="bar-fill-hp" style="width:{boss_pct}%;"></div></div>""", unsafe_allow_html=True)
            st.caption(f"HP: {boss_cur}/{boss_max} ｜ 今日の弱点: **{get_today_weak_label()}**")
            if boss_defeated:
                st.success("🎉 討伐完了！")
                st.markdown(f"""
                <div style="background: rgba(40,32,24,0.95); border: 2px solid #c9a227; border-radius: 8px; padding: 10px; margin: 8px 0;">
                    <strong>💰 討伐報酬</strong><br>
                    <span style="color: #c9b896;">ゴールド: {w_boss.get('reward', 1000)}G</span><br>
                    <span style="color: #c9b896;">経験値: {w_boss.get('reward_xp', 500)}XP</span>
                </div>
                """, unsafe_allow_html=True)
                if not boss_claimed:
                    if st.button(f"🎁 討伐報酬を受け取る ({w_boss.get('reward', 1000)}G + {w_boss.get('reward_xp', 500)}XP)", key="boss_reward"):
                        try:
                            # 先にboss_claimedを更新してから報酬を追加（重複防止）
                            ws_u.update_cell(u_idx, 27, wk_id)  # boss_claimed列を先に更新
                            new_gold = _int(user.get('gold')) + w_boss.get('reward', 1000)
                            new_xp = _int(user.get('current_xp')) + w_boss.get('reward_xp', 500)
                            u_nxt_xp = _int(user.get('next_level_xp'), 100)
                            u_lv = _int(user.get('level'), 1)
                            ws_u.update_cell(u_idx, 6, new_gold)
                            _apply_xp_gain(ws_u, u_idx, new_xp, u_nxt_xp, u_lv)
                            st.success(f"{w_boss.get('reward', 1000)}G + {w_boss.get('reward_xp', 500)}XP 獲得！"); _invalidate_sheet_cache(); time.sleep(0.2); st.rerun()
                        except Exception as e:
                            st.error(f"ボス討伐報酬の保存に失敗しました。スプレッドシートの列AA(27)に「boss_claimed」列があるか確認してください。エラー: {str(e)}")
                            st.stop()
                else:
                    st.caption("✅ 今週の討伐報酬は受取済み")
            else:
                st.caption(f"💡 討伐すると {w_boss.get('reward', 1000)}G + {w_boss.get('reward_xp', 500)}XP 獲得！")

    st.markdown("---")

    # --- 4. タブ機能 ---
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs(["📋 ギルド", "💎 ショップ", "🏆 実績", "📚 図鑑", "📊 統計", "📊 記録", "🎒 倉庫", "📜 思い出"])

    with tab1:
        c_g1, c_g2 = st.columns(2)
        with c_g1:
            st.subheader("📋 デイリー・ウィークリークエスト")
            
            # ミッション（短期目標）
            st.markdown("#### 🎯 ミッション")
            mission_claimed = user.get('mission_claimed', '').split(',') if user.get('mission_claimed') else []
            mission_claimed_set = set([m.strip() for m in mission_claimed if m.strip()])
            
            for mission_id, mission_data in MISSIONS.items():
                if mission_data['type'] == 'daily':
                    progress = d_cnt
                    target = mission_data['target']
                    is_done = progress >= target
                    is_claimed = mission_id in mission_claimed_set
                else:  # weekly
                    progress = w_cnt
                    target = mission_data['target']
                    is_done = progress >= target
                    is_claimed = mission_id in mission_claimed_set
                
                border_color = "#c9a227" if is_done and not is_claimed else "#555" if is_done else "#333"
                st.markdown(f"""
                <div style="background: rgba(30,28,24,0.9); border: 2px solid {border_color}; border-radius: 8px; padding: 10px; margin: 6px 0;">
                    <div style="display:flex; justify-content:space-between;">
                        <strong>{mission_data['name']}</strong>
                        <span style="color: #c9a227;">{mission_data['reward']}G</span>
                    </div>
                    <p style="margin: 4px 0; color: #c9b896; font-size: 0.9em;">{mission_data['desc']}</p>
                    <div class="bar-bg" style="height: 8px; margin: 4px 0;"><div class="bar-fill-xp" style="width: {min(100, progress/target*100)}%; height: 100%;"></div></div>
                    <p style="margin: 0; font-size: 0.85em;">進捗 {progress}/{target}</p>
                </div>
                """, unsafe_allow_html=True)
                
                if is_done and not is_claimed:
                    if st.button(f"🎁 {mission_data['reward']}G を受け取る", key=f"mission_{mission_id}"):
                        try:
                            # 先にmission_claimedを更新してから報酬を追加（重複防止）
                            new_claimed = ','.join(list(mission_claimed_set) + [mission_id]).strip(',')
                            ws_u.update_cell(u_idx, 26, new_claimed)  # mission_claimed列を先に更新
                            new_gold = _int(user.get('gold')) + mission_data['reward']
                            ws_u.update_cell(u_idx, 6, new_gold)
                            st.success(f"{mission_data['reward']}G 獲得！"); _invalidate_sheet_cache(); time.sleep(0.2); st.rerun()
                        except Exception as e:
                            st.error(f"ミッション報酬の保存に失敗しました。スプレッドシートの列Z(26)に「mission_claimed」列があるか確認してください。エラー: {str(e)}")
                            st.stop()
            
            st.markdown("---")
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
                    try:
                        # 先にdaily_claimedを更新してから報酬を追加（重複防止）
                        ws_u.update_cell(u_idx, 14, str(today))  # daily_claimed列を先に更新
                        new_gold = _int(user.get('gold')) + 200
                        ws_u.update_cell(u_idx, 6, new_gold)
                        st.success("200G 獲得！"); _invalidate_sheet_cache(); time.sleep(0.2); st.rerun()
                    except Exception as e:
                        st.error(f"デイリー報酬の保存に失敗しました。スプレッドシートの列N(14)に「daily_claimed」列があるか確認してください。エラー: {str(e)}")
                        st.stop()
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
                    try:
                        # 先にweekly_claimedを更新してから報酬を追加（重複防止）
                        ws_u.update_cell(u_idx, 15, wk_id)  # weekly_claimed列を先に更新
                        new_gold = _int(user.get('gold')) + 500
                        ws_u.update_cell(u_idx, 6, new_gold)
                        st.success("500G 獲得！"); _invalidate_sheet_cache(); time.sleep(0.2); st.rerun()
                    except Exception as e:
                        st.error(f"ウィークリー報酬の保存に失敗しました。スプレッドシートの列O(15)に「weekly_claimed」列があるか確認してください。エラー: {str(e)}")
                        st.stop()
            elif w_claim:
                st.caption("✅ 今週分は受取済み")
            st.markdown("#### 🌸 季節限定ミッション")
            month_id = f"{today.year}-{today.month:02d}"
            seasonal = SEASONAL_MISSIONS.get(today.month)
            seasonal_claimed = (str(user.get('seasonal_claimed') or '')).strip() == month_id
            if seasonal:
                user_tasks_m = df_t[df_t['user_id']=='u001'] if not df_t.empty else pd.DataFrame()
                if not user_tasks_m.empty and 'created_at' in user_tasks_m.columns:
                    user_tasks_m = user_tasks_m.copy()
                    user_tasks_m['dt'] = pd.to_datetime(user_tasks_m['created_at'])
                month_start = today.replace(day=1)
                month_tasks = user_tasks_m[(user_tasks_m['dt'].dt.date >= month_start)] if not user_tasks_m.empty and 'dt' in user_tasks_m.columns else pd.DataFrame()
                count = sum(1 for _, r in month_tasks.iterrows() if seasonal['task_key'] in str(r.get('task_name', ''))) if not month_tasks.empty else 0
                done = count >= seasonal['target']
                if not seasonal_claimed and done:
                    if st.button(f"🎁 季節報酬 {seasonal['reward']}G", key="seasonal_claim"):
                        try:
                            ws_u.update_cell(u_idx, 34, month_id)
                            ws_u.update_cell(u_idx, 6, _int(user.get('gold')) + seasonal['reward'])
                            _invalidate_sheet_cache()
                            st.success(f"{seasonal['reward']}G 獲得！"); st.rerun()
                        except Exception:
                            st.caption("列AD(34) seasonal_claimed を追加")
                st.caption(f"{seasonal['name']}: {count}/{seasonal['target']}" + (" 受取済" if seasonal_claimed else ""))

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
        last_weekly = (str(user.get('last_weekly_ticket') or '')).strip()
        last_monthly_sr = (str(user.get('last_monthly_sr_ticket') or '')).strip()
        # 週: "2025-W8" 形式で保存。列に日付(YYYY-MM-DD)が入っていても、その日が今週なら購入済みと判定
        if last_weekly == wk_id:
            can_weekly_ticket = False
        elif len(last_weekly) >= 10 and last_weekly[4] == '-' and last_weekly[7] == '-':
            try:
                d = datetime.strptime(last_weekly[:10], "%Y-%m-%d").date()
                can_weekly_ticket = (d.isocalendar()[0], d.isocalendar()[1]) != (today.isocalendar()[0], today.isocalendar()[1])
            except Exception:
                can_weekly_ticket = (last_weekly != wk_id)
        else:
            can_weekly_ticket = (last_weekly != wk_id)
        # 月: "2025-02" 形式で比較（"2025-02-17" など日付が入っていても先頭一致で今月購入済みと判定）
        can_monthly_sr = not (last_monthly_sr.startswith(month_id) if last_monthly_sr else False)

        st.markdown("#### 🏷️ 週・月限定（お得）")
        lim1, lim2 = st.columns(2)
        with lim1:
            st.markdown("**🎫 ガチャチケ10枚セット** — 800G")
            st.caption("週1回のみ！定価1000G相当（20%OFF）")
            if st.button("購入（今週分）", key="weekly_ticket", disabled=not can_weekly_ticket):
                if can_weekly_ticket and _int(user.get('gold')) >= 800:
                    # ガチャ演出
                    st.markdown("### 🎰 10連召喚中...")
                    st.progress(1.0)
                    
                    results = [gacha_draw() for _ in range(10)]
                    df_i_check = pd.DataFrame(ws_i.get_all_records())
                    total_piece_gold = 0
                    new_monsters = []
                    rarity_counts = {"N": 0, "R": 0, "SR": 0, "SSR": 0, "UR": 0}
                    
                    for m_key in results:
                        m_data = MONSTERS[m_key]
                        rarity = m_data['rarity']
                        rarity_counts[rarity] = rarity_counts.get(rarity, 0) + 1
                        already_has = not df_i_check.empty and len(df_i_check[(df_i_check['user_id']=='u001') & (df_i_check['item_name']==m_key)]) > 0
                        if already_has:
                            # 重複時は自動的にレベルアップに使用
                            monster_row = df_i_check[(df_i_check['user_id']=='u001') & (df_i_check['item_name']==m_key)]
                            if not monster_row.empty:
                                current_level = _int(monster_row.iloc[0].get('quantity', 1))
                                if current_level < 10:
                                    new_level = current_level + 1
                                    monster_idx = monster_row.index[0] + 2
                                    ws_i.update_cell(monster_idx, 4, new_level)
                                    new_monsters.append(f"{m_key} Lv.{new_level}↑")
                                else:
                                    # 最大レベル時はゴールドに変換
                                    piece_gold = {"N": 10, "R": 30, "SR": 100, "SSR": 300, "UR": 1000}.get(rarity, 10)
                                    total_piece_gold += piece_gold
                            df_i_check = pd.DataFrame(ws_i.get_all_records())
                        else:
                            ws_i.append_row(['u001', m_key, rarity, 1, str(datetime.now())])
                            new_monsters.append(m_key)
                            df_i_check = pd.DataFrame(ws_i.get_all_records())
                    
                    # 先に週次購入済みを記録してから報酬（重複防止）
                    try:
                        ws_u.update_cell(u_idx, 22, wk_id)  # last_weekly_ticket
                    except Exception as e:
                        st.error(f"週1回チケットの保存に失敗しました。users の列V(22)に「last_weekly_ticket」を追加してください。")
                        st.stop()
                    new_gold = _int(user.get('gold')) - 800 + total_piece_gold
                    ws_u.update_cell(u_idx, 6, new_gold)
                    st.session_state.last_gacha_10 = results
                    st.session_state.last_gacha_10_info = {"new": new_monsters, "pieces": total_piece_gold, "rarity_counts": rarity_counts}
                    
                    # 演出
                    st.balloons()
                    st.success("🎉 10連召喚完了！")
                    rarity_display = " ".join([f"{r}: {c}" for r, c in rarity_counts.items() if c > 0])
                    st.info(f"結果: {rarity_display}")
                    if new_monsters:
                        st.success(f"獲得: {', '.join(new_monsters[:5])}{'...' if len(new_monsters) > 5 else ''}")
                    if total_piece_gold > 0:
                        st.info(f"最大レベル変換: {total_piece_gold}G")
                    time.sleep(2.0); st.rerun()
                elif not can_weekly_ticket: st.warning("今週は購入済み")
                else: st.error("金貨不足")
            if not can_weekly_ticket: st.caption("✅ 今週は購入済み")
        with lim2:
            st.markdown("**✨ SR以上確定チケット** — 600G")
            st.caption("月1回のみ！SR 80% / SSR 19% / UR 1%")
            monthly_sr_key = f"monthly_sr_claimed_{month_id}"
            monthly_sr_claimed = monthly_sr_key in st.session_state
            if st.button("購入（今月分）", key="monthly_sr", disabled=(not can_monthly_sr or monthly_sr_claimed)):
                if can_monthly_sr and not monthly_sr_claimed and _int(user.get('gold')) >= 600:
                    # 重複防止：先にシートに「今月購入済み」と金貨を反映してからガチャ処理
                    _save_monthly_sr_claimed(ws_u, u_idx, month_id)
                    ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 600)
                    st.session_state[monthly_sr_key] = True
                    _invalidate_sheet_cache()

                    st.markdown("### ✨ SR以上確定召喚中...")
                    m_key = gacha_draw_sr_guaranteed()
                    m_data = MONSTERS[m_key]
                    rarity = m_data['rarity']

                    if rarity == "UR":
                        st.balloons()
                        st.success("🌟✨ **URレア獲得！** ✨🌟")
                    elif rarity == "SSR":
                        st.success("💎 **SSRレア獲得！** 💎")
                    else:
                        st.info("⭐ **SRレア獲得！** ⭐")

                    df_i_check = pd.DataFrame(ws_i.get_all_records())
                    already_has = not df_i_check.empty and len(df_i_check[(df_i_check['user_id']=='u001') & (df_i_check['item_name']==m_key)]) > 0
                    if already_has:
                        monster_row = df_i_check[(df_i_check['user_id']=='u001') & (df_i_check['item_name']==m_key)]
                        if not monster_row.empty:
                            current_level = _int(monster_row.iloc[0].get('quantity', 1))
                            if current_level < 10:
                                new_level = current_level + 1
                                monster_idx = monster_row.index[0] + 2
                                ws_i.update_cell(monster_idx, 4, new_level)
                                st.success(f"重複！{m_key} がレベル{new_level}に上がった！")
                            else:
                                piece_gold = {"N": 10, "R": 30, "SR": 100, "SSR": 300, "UR": 1000}.get(rarity, 100)
                                new_gold = _int(user.get('gold')) - 600 + piece_gold
                                ws_u.update_cell(u_idx, 6, new_gold)
                                st.info(f"重複！{m_key}は最大レベルなので {piece_gold}G に変換")
                        time.sleep(1.0); st.rerun()
                    else:
                        ws_i.append_row(['u001', m_key, rarity, 1, str(datetime.now())])
                        st.session_state.last_gacha_result = (m_key, rarity, False, 0)
                        st.success(f"🎉 {m_key} GET!")
                        time.sleep(1.0); st.rerun()
                elif monthly_sr_claimed: st.warning("今月は購入済み")
                elif not can_monthly_sr: st.warning("今月は購入済み")
                else: st.error("金貨不足")
            if not can_monthly_sr or monthly_sr_claimed: st.caption("✅ 今月は購入済み")

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
                    # ガチャ演出
                    st.markdown("### ✨ 召喚中...")
                    st.progress(1.0)
                    
                    m_key = gacha_draw()
                    m_data = MONSTERS[m_key]
                    rarity = m_data['rarity']
                    
                    # レアリティに応じた演出
                    if rarity == "UR":
                        st.balloons()
                        st.success("🌟✨ **URレア獲得！** ✨🌟")
                    elif rarity == "SSR":
                        st.success("💎 **SSRレア獲得！** 💎")
                    elif rarity == "SR":
                        st.info("⭐ **SRレア獲得！** ⭐")
                    
                    # 重複チェック
                    df_i_check = pd.DataFrame(ws_i.get_all_records())
                    already_has = not df_i_check.empty and len(df_i_check[(df_i_check['user_id']=='u001') & (df_i_check['item_name']==m_key)]) > 0
                    
                    if already_has:
                        # 重複時は自動的にレベルアップに使用
                        monster_row = df_i_check[(df_i_check['user_id']=='u001') & (df_i_check['item_name']==m_key)]
                        if not monster_row.empty:
                            current_level = _int(monster_row.iloc[0].get('quantity', 1))
                            if current_level < 10:
                                new_level = current_level + 1
                                monster_idx = monster_row.index[0] + 2
                                ws_i.update_cell(monster_idx, 4, new_level)
                                if not is_free: ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 100)
                                if is_free: ws_u.update_cell(u_idx, 13, str(today))
                                st.success(f"重複！{m_key} がレベル{new_level}に上がった！")
                            else:
                                # 最大レベル時はゴールドに変換
                                piece_gold = {"N": 10, "R": 30, "SR": 100, "SSR": 300, "UR": 1000}.get(rarity, 10)
                                new_gold = _int(user.get('gold')) + piece_gold
                                if not is_free: new_gold -= 100
                                ws_u.update_cell(u_idx, 6, new_gold)
                                if is_free: ws_u.update_cell(u_idx, 13, str(today))
                                st.info(f"重複！{m_key}は最大レベルなので {piece_gold}G に変換")
                        time.sleep(1.0); st.rerun()
                    else:
                        # 新規：通常追加
                        ws_i.append_row(['u001', m_key, rarity, 1, str(datetime.now())])
                        if is_free: ws_u.update_cell(u_idx, 13, str(today))
                        else: ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 100)
                        st.session_state.last_gacha_result = (m_key, rarity, False, 0)
                        st.success(f"🎉 {m_key} GET!")
                        time.sleep(1.0); st.rerun()
            if st.session_state.get('last_gacha_result'):
                result = st.session_state.last_gacha_result
                if len(result) == 4:  # 重複処理あり
                    mk, r, is_dupe, piece_gold = result
                    md = MONSTERS[mk]
                    if is_dupe:
                        st.warning(f"重複！{mk} → ピース変換で {piece_gold}G 獲得")
                        emoji, color = get_monster_display(mk, r)
                        st.markdown(f'<div style="font-size: 48px; text-align: center; background: {color}20; border-radius: 8px; padding: 8px;">{emoji}</div>', unsafe_allow_html=True)
                    else:
                        skill_desc = md.get('skill_desc', md.get('skill_name', md['skill']))
                        st.markdown(f'<span class="rarity-{r}">★ {r} ★</span> {mk}', unsafe_allow_html=True)
                        emoji, color = get_monster_display(mk, r)
                        st.markdown(f'<div style="font-size: 48px; text-align: center; background: {color}20; border-radius: 8px; padding: 8px;">{emoji}</div>', unsafe_allow_html=True)
                        st.caption(f"効果: {skill_desc}")
                else:  # 旧形式（後方互換）
                    mk, r = result
                    md = MONSTERS[mk]
                    skill_desc = md.get('skill_desc', md.get('skill_name', md['skill']))
                    st.markdown(f'<span class="rarity-{r}">★ {r} ★</span> {mk}', unsafe_allow_html=True)
                    st.image(get_monster_url(md['seed'], r, mk), width=80)
                    st.caption(f"効果: {skill_desc}")

        with col_g2:
            st.markdown("**✨ 10連召喚（お得）**")
            st.caption("900Gで10回分！1回あたり90G")
            if st.button("10連召喚 (900G)", key="gacha10", use_container_width=True):
                if _int(user.get('gold')) < 900:
                    st.error("金貨が足りません（900G必要）")
                else:
                    results = [gacha_draw() for _ in range(10)]
                    df_i_check = pd.DataFrame(ws_i.get_all_records())
                    total_piece_gold = 0
                    new_monsters = []
                    for m_key in results:
                        m_data = MONSTERS[m_key]
                        already_has = not df_i_check.empty and len(df_i_check[(df_i_check['user_id']=='u001') & (df_i_check['item_name']==m_key)]) > 0
                        if already_has:
                            piece_gold = {"N": 10, "R": 30, "SR": 100, "SSR": 300, "UR": 1000}.get(m_data['rarity'], 10)
                            total_piece_gold += piece_gold
                        else:
                            ws_i.append_row(['u001', m_key, m_data['rarity'], 1, str(datetime.now())])
                            new_monsters.append(m_key)
                            df_i_check = pd.DataFrame(ws_i.get_all_records())  # 更新
                    new_gold = _int(user.get('gold')) - 900 + total_piece_gold
                    ws_u.update_cell(u_idx, 6, new_gold)
                    st.session_state.last_gacha_10 = results
                    st.session_state.last_gacha_10_info = {"new": new_monsters, "pieces": total_piece_gold}
                    st.rerun()
            if st.session_state.get('last_gacha_10'):
                res = st.session_state.last_gacha_10
                info = st.session_state.get('last_gacha_10_info', {"new": res, "pieces": 0})
                ur_c = sum(1 for mk in res if MONSTERS[mk]['rarity']=='UR')
                ssr_c = sum(1 for mk in res if MONSTERS[mk]['rarity']=='SSR')
                sr_c = sum(1 for mk in res if MONSTERS[mk]['rarity']=='SR')
                r_c = sum(1 for mk in res if MONSTERS[mk]['rarity']=='R')
                n_c = 10 - ur_c - ssr_c - sr_c - r_c
                piece_msg = f" ピース: {info['pieces']}G" if info['pieces'] > 0 else ""
                st.success(f"10連 — UR:{ur_c} SSR:{ssr_c} SR:{sr_c} R:{r_c} N:{n_c}{piece_msg}")
                cols = st.columns(5)
                for i, m_key in enumerate(res):
                    with cols[i % 5]:
                        md = MONSTERS[m_key]
                        r = md['rarity']
                        is_new = m_key in info.get('new', [])
                        label = f'<span class="rarity-{r}">{r}</span>' + (" ✨" if is_new else " 🔄")
                        st.markdown(label, unsafe_allow_html=True)
                        emoji, color = get_monster_display(m_key, r)
                        st.markdown(f'<div style="font-size: 36px; text-align: center; background: {color}20; border-radius: 8px; padding: 4px;">{emoji}</div>', unsafe_allow_html=True)
                        st.caption(m_key + (" (新規)" if is_new else " (重複→ピース)"))

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
        it1, it2, it3 = st.columns(3)
        with it1:
            st.markdown("**⚡ スタミナポーション** — 150G")
            st.caption("デイリークエスト進捗+1（最大3まで）")
            if st.button("購入", key="item_stamina"):
                if _int(user.get('gold')) >= 150:
                    if d_cnt < 3:
                        fake_task_id = str(uuid.uuid4())
                        ws_t.append_row([fake_task_id, 'u001', 'スタミナポーション使用', 'item', 1, 'Completed', str(datetime.now())])
                        ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 150)
                        st.success("デイリー進捗+1！"); time.sleep(0.5); st.rerun()
                    else:
                        st.warning("デイリーは既に達成済み")
                else: st.error("金貨不足")
        with it2:
            st.markdown("**🔥 ボス討伐の書** — 200G")
            st.caption("週間ボスダメージ+500")
            if st.button("購入", key="item_boss_dmg"):
                if _int(user.get('gold')) >= 200:
                    current_dmg = _int(user.get('weekly_boss_damage'))
                    ws_u.update_cell(u_idx, 19, current_dmg + 500)
                    ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 200)
                    st.success("ボスダメージ+500！"); time.sleep(0.5); st.rerun()
                else: st.error("金貨不足")
        with it3:
            st.markdown("**📈 階層スキップ** — 300G")
            st.caption("階層+5（最大100階まで）")
            if st.button("購入", key="item_floor_skip"):
                if _int(user.get('gold')) >= 300:
                    current_floor = _int(user.get('dungeon_floor'))
                    new_floor = min(MAX_FLOOR, current_floor + 5)
                    ws_u.update_cell(u_idx, 8, new_floor)
                    ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 300)
                    st.success(f"階層 {current_floor} → {new_floor}！"); time.sleep(0.5); st.rerun()
                else: st.error("金貨不足")
        
        st.markdown("#### 💎 実用的アイテム（リアルでプラスになる）")
        util1, util2, util3 = st.columns(3)
        with util1:
            st.markdown("**🛡️ ストリーク保護** — 250G")
            st.caption("今日タスクをしなくても連続記録が途切れない（1回のみ）")
            if st.button("購入", key="item_streak_protect"):
                if _int(user.get('gold')) >= 250:
                    # ストリーク保護フラグを設定（列28に保存）
                    try:
                        ws_u.update_cell(u_idx, 28, str(today))  # streak_protect_date列
                        ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 250)
                        st.success("ストリーク保護が有効になりました！"); time.sleep(0.5); st.rerun()
                    except:
                        st.error("保存に失敗（列AB(28)にstreak_protect_date列を追加してください）")
                else: st.error("金貨不足")
        with util2:
            st.markdown("**📝 タスクメモ** — 100G")
            st.caption("今日のタスクをメモできる（最大5つまで）")
            if st.button("購入", key="item_task_memo"):
                if _int(user.get('gold')) >= 100:
                    st.info("タスクメモ機能は準備中です")
                    # 将来的に実装：タスクメモ機能
                else: st.error("金貨不足")
        with util3:
            st.markdown("**⏰ リマインダー設定** — 150G")
            st.caption("タスクリマインダーを設定できる（1週間有効）")
            if st.button("購入", key="item_reminder"):
                if _int(user.get('gold')) >= 150:
                    st.info("リマインダー機能は準備中です")
                    # 将来的に実装：リマインダー機能
                else: st.error("金貨不足")
        
        st.markdown("#### ✨ 限定バフ")
        buf1, buf2, buf3 = st.columns(3)
        with buf1:
            st.caption("ゴールドバフ 400G（次の3タスクで報酬+50%）")
            if st.button("購入", key="item_gold_buff"):
                if _int(user.get('gold')) >= 400:
                    buff_data = f"gold_50_3_{datetime.now().isoformat()}"
                    try:
                        ws_u.update_cell(u_idx, 24, buff_data)
                        ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 400)
                        st.success("次の3タスクで報酬+50%！"); time.sleep(0.5); st.rerun()
                    except:
                        st.error("バフ保存に失敗（列X(24)にbuff_data列を追加してください）")
                else: st.error("金貨不足")
        with buf2:
            st.caption("経験値バフ 400G（次の3タスクで経験値+50%）")
            if st.button("購入", key="item_xp_buff"):
                if _int(user.get('gold')) >= 400:
                    buff_data = f"xp_50_3_{datetime.now().isoformat()}"
                    try:
                        ws_u.update_cell(u_idx, 24, buff_data)
                        ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 400)
                        st.success("次の3タスクで経験値+50%！"); time.sleep(0.5); st.rerun()
                    except:
                        st.error("バフ保存に失敗（列X(24)にbuff_data列を追加してください）")
                else: st.error("金貨不足")
        with buf3:
            st.caption("🎯 実績ブースト 500G（実績達成が2倍速になる）")
            if st.button("購入", key="item_achievement_boost"):
                if _int(user.get('gold')) >= 500:
                    buff_data = f"achievement_2x_{datetime.now().isoformat()}"
                    try:
                        ws_u.update_cell(u_idx, 24, buff_data)
                        ws_u.update_cell(u_idx, 6, _int(user.get('gold')) - 500)
                        st.success("実績達成が2倍速になります！"); time.sleep(0.5); st.rerun()
                    except:
                        st.error("バフ保存に失敗（列X(24)にbuff_data列を追加してください）")
                else: st.error("金貨不足")

    with tab3:  # 実績
        st.subheader("🏆 実績一覧")
        achieved_list = user.get('achievements', '').split(',') if user.get('achievements') else []
        achieved_set = set([a.strip() for a in achieved_list if a.strip()])
        
        total_tasks = len(df_t[df_t['user_id']=='u001']) if not df_t.empty else 0
        floor = _int(user.get('dungeon_floor'))
        rebirth = _int(user.get('rebirth_count'))
        level = _int(user.get('level'), 1)
        streak = calc_task_streak(df_t, user)
        has_ur = False
        if not df_i.empty:
            user_items = df_i[df_i['user_id']=='u001']
            if not user_items.empty:
                has_ur = len(user_items[user_items['rarity']=='UR']) > 0
        
        for ach_id, ach_data in ACHIEVEMENTS.items():
            is_done = ach_id in achieved_set
            border_color = "#c9a227" if is_done else "#555"
            bg_color = "rgba(40,32,24,0.95)" if is_done else "rgba(20,20,20,0.7)"
            check = "✅" if is_done else "⭕"
            
            # 進捗チェック
            progress = ""
            if ach_id == "first_task": progress = f" ({total_tasks}/1)" if total_tasks < 1 else ""
            elif ach_id == "task_10": progress = f" ({total_tasks}/10)" if total_tasks < 10 else ""
            elif ach_id == "task_50": progress = f" ({total_tasks}/50)" if total_tasks < 50 else ""
            elif ach_id == "task_100": progress = f" ({total_tasks}/100)" if total_tasks < 100 else ""
            elif ach_id == "floor_10": progress = f" ({floor}/10)" if floor < 10 else ""
            elif ach_id == "floor_50": progress = f" ({floor}/50)" if floor < 50 else ""
            elif ach_id == "floor_100": progress = f" ({floor}/100)" if floor < 100 else ""
            elif ach_id == "rebirth_1": progress = f" ({rebirth}/1)" if rebirth < 1 else ""
            elif ach_id == "rebirth_5": progress = f" ({rebirth}/5)" if rebirth < 5 else ""
            elif ach_id == "level_10": progress = f" ({level}/10)" if level < 10 else ""
            elif ach_id == "level_20": progress = f" ({level}/20)" if level < 20 else ""
            elif ach_id == "gacha_ur": progress = " (未獲得)" if not has_ur else ""
            elif ach_id == "streak_7": progress = f" ({streak}/7)" if streak < 7 else ""
            elif ach_id == "streak_30": progress = f" ({streak}/30)" if streak < 30 else ""
            
            st.markdown(f"""
            <div style="background: {bg_color}; border: 2px solid {border_color}; border-radius: 8px; padding: 12px; margin: 8px 0;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <span><strong>{check} {ach_data['icon']} {ach_data['name']}</strong></span>
                    <span style="color: #c9a227;">報酬: {ach_data['reward']}G</span>
                </div>
                <p style="margin: 4px 0; color: #c9b896;">{ach_data['desc']}{progress}</p>
            </div>
            """, unsafe_allow_html=True)
        
        st.caption(f"達成率: {len(achieved_set)}/{len(ACHIEVEMENTS)} ({len(achieved_set)*100//len(ACHIEVEMENTS)}%)")

    with tab4:  # 図鑑
        st.subheader("📚 モンスター図鑑")
        if not df_i.empty:
            owned = set(df_i[df_i['user_id']=='u001']['item_name'].unique())
        else:
            owned = set()
        
        # レアリティ順に表示
        rarity_order = ["UR", "SSR", "SR", "R", "N"]
        for rarity in rarity_order:
            st.markdown(f"### {rarity}レアリティ")
            monsters_in_rarity = {k: v for k, v in MONSTERS.items() if v['rarity'] == rarity}
            cols = st.columns(3)
            for idx, (m_name, m_data) in enumerate(monsters_in_rarity.items()):
                col = cols[idx % 3]
                with col:
                    is_owned = m_name in owned
                    opacity = "1.0" if is_owned else "0.3"
                    border = "2px solid #c9a227" if is_owned else "1px solid #555"
                    emoji, color = get_monster_display(m_name, rarity)
                    st.markdown(f"""
                    <div style="background: rgba(30,28,24,0.9); border: {border}; border-radius: 8px; padding: 8px; margin: 4px 0; text-align: center; opacity: {opacity};">
                        <div style="font-size: 64px; background: {color}20; border-radius: 8px; padding: 8px; margin-bottom: 8px;">{emoji}</div>
                        <p style="margin: 4px 0; font-weight: bold;">{m_name}</p>
                        <p style="margin: 0; font-size: 0.85em; color: #c9b896;">{m_data.get('skill_desc', m_data.get('skill_name', m_data['skill']))}</p>
                        {"✅ 獲得済み" if is_owned else "❌ 未獲得"}
                    </div>
                    """, unsafe_allow_html=True)
        st.caption(f"コレクション進捗: {len(owned)}/{len(MONSTERS)} ({len(owned)*100//len(MONSTERS)}%)")

    with tab5:  # 統計
        st.subheader("📊 統計・分析")
        
        # 基本統計
        st.markdown("#### 📈 基本統計")
        total_tasks = len(df_t[df_t['user_id']=='u001']) if not df_t.empty else 0
        total_gold = _int(user.get('total_gold_earned', 0))
        total_xp = _int(user.get('total_xp_earned', 0))
        level = _int(user.get('level'), 1)
        floor = _int(user.get('dungeon_floor'))
        rebirth = _int(user.get('rebirth_count'))
        streak = calc_task_streak(df_t, user)
        login_streak = _int(user.get('login_streak'))
        
        # 所持モンスター数
        owned_count = 0
        if not df_i.empty:
            owned_count = len(df_i[df_i['user_id']=='u001']['item_name'].unique())
        
        stat_cols = st.columns(3)
        with stat_cols[0]:
            st.metric("総タスク数", total_tasks)
            st.metric("現在のレベル", level)
            st.metric("現在の階層", floor)
        with stat_cols[1]:
            st.metric("総獲得ゴールド", f"{total_gold:,}G" if total_gold > 0 else "0G")
            st.metric("転生回数", rebirth)
            st.metric("タスク連続日数", f"{streak}日")
        with stat_cols[2]:
            st.metric("総獲得経験値", f"{total_xp:,}XP" if total_xp > 0 else "0XP")
            st.metric("ログイン連続日数", f"{login_streak}日")
            st.metric("所持モンスター数", owned_count)
        
        # 日別タスク数グラフ
        if not df_t.empty:
            st.markdown("#### 📅 日別タスク数")
            daily = df_t.groupby(df_t['dt'].dt.date).size().reset_index(name='Actions')
            c = alt.Chart(daily).mark_bar(color='#c9a227').encode(
                x='dt:T',
                y='Actions:Q'
            ).properties(height=300)
            st.altair_chart(c, use_container_width=True)
        
        # タスクタイプ別統計
        if not df_t.empty:
            st.markdown("#### 🎯 タスクタイプ別")
            task_types = df_t['task_name'].value_counts()
            type_cols = st.columns(2)
            with type_cols[0]:
                for task_name, count in task_types.head(5).items():
                    st.write(f"- {task_name}: {count}回")
            with type_cols[1]:
                if len(task_types) > 5:
                    for task_name, count in task_types.tail(len(task_types)-5).items():
                        st.write(f"- {task_name}: {count}回")
        
        # カスタマイズ要素
        st.markdown("#### 🎨 カスタマイズ")
        st.caption("アバターの見た目を変更できます（現在は実装中）")
        custom_cols = st.columns(3)
        with custom_cols[0]:
            st.caption("アバタースタイル")
            if st.button("変更（準備中）", disabled=True, key="custom_avatar_btn"):
                pass
        with custom_cols[1]:
            st.caption("テーマカラー")
            if st.button("変更（準備中）", disabled=True, key="custom_theme_btn"):
                pass
        with custom_cols[2]:
            st.caption("称号表示")
            current_title = get_user_title(user)
            st.text_input("カスタム称号", value=current_title, key="custom_title", disabled=True, help="準備中")

    with tab6:  # 記録
        if not df_t.empty:
            daily = df_t.groupby(df_t['dt'].dt.date).size().reset_index(name='Actions')
            c = alt.Chart(daily).mark_bar().encode(x='dt:T', y='Actions:Q')
            st.altair_chart(c, use_container_width=True)

    with tab7:  # 倉庫
        st.subheader("🎒 倉庫")
        if not df_i.empty:
            user_items = df_i[df_i['user_id']=='u001']
            if not user_items.empty:
                st.markdown("#### 🐾 モンスター")
                for idx, row in user_items.iterrows():
                    monster_name = row['item_name']
                    monster_level = _int(row.get('quantity', 1))
                    monster_rarity = row.get('rarity', 'N')
                    if monster_name in MONSTERS:
                        m_data = MONSTERS[monster_name]
                        col1, col2, col3 = st.columns([1, 3, 2])
                        with col1:
                            emoji, color = get_monster_display(monster_name, monster_rarity)
                            st.markdown(f'<div style="font-size: 36px; text-align: center; background: {color}20; border-radius: 8px; padding: 4px;">{emoji}</div>', unsafe_allow_html=True)
                        with col2:
                            st.write(f"**{monster_name}** (Lv.{monster_level})")
                            st.caption(f"{m_data.get('skill_desc', m_data.get('skill_name', m_data['skill']))}")
                        with col3:
                            if monster_level < 10:
                                st.caption(f"レベルアップ: 同じモンスターを1体必要")
                            else:
                                st.caption("最大レベル到達")
                st.markdown("#### 📦 アイテム")
                # アイテム表示（モンスター以外）
                items_only = user_items[~user_items['item_name'].isin(MONSTERS.keys())]
                if not items_only.empty:
                    for idx, row in items_only.iterrows():
                        st.write(f"- {row['item_name']} x{row.get('quantity', 1)}")
                else:
                    st.caption("アイテムなし")
            else:
                st.info("倉庫が空です")
        else:
            st.info("倉庫が空です")

    with tab8:  # 思い出アルバム（8）
        st.subheader("📜 思い出アルバム")
        user_tasks = df_t[df_t['user_id']=='u001'] if not df_t.empty else pd.DataFrame()
        if not user_tasks.empty and 'dt' in user_tasks.columns:
            first_date = user_tasks['dt'].min()
            if pd.notna(first_date):
                first_str = first_date.strftime('%Y年%m月%d日') if hasattr(first_date, 'strftime') else str(first_date)[:10]
                st.markdown(f"**初クエスト** — {first_str}")
            st.markdown(f"**累計タスク数** — {len(user_tasks)} 回")
            start_wk = today - timedelta(days=today.weekday())
            week_tasks = user_tasks[user_tasks['dt'].dt.date >= start_wk] if 'dt' in user_tasks.columns else pd.DataFrame()
            st.markdown(f"**今週** — {len(week_tasks)} 回")
            if not week_tasks.empty and 'task_name' in week_tasks.columns:
                st.caption("今週やったこと:")
                for _, r in week_tasks.head(10).iterrows():
                    tn = r.get('task_name', '')
                    dt_val = r.get('dt', r.get('created_at', ''))
                    st.caption(f" ・ {tn} ({str(dt_val)[:10]})")
        else:
            st.caption("タスクをすると思い出が増えます")
        st.markdown(f"**現在の階層** — {_int(user.get('dungeon_floor'))} 階")
        st.markdown(f"**転生回数** — {_int(user.get('rebirth_count'))} 回")
        st.markdown(f"**タスク連続** — {task_streak} 日")

    # データエクスポート（19）
    st.markdown("---")
    st.subheader("📤 データエクスポート")
    try:
        user_dict = user.to_dict() if hasattr(user, 'to_dict') else dict(user)
        export_data = {"user": user_dict, "tasks_count": len(df_t[df_t['user_id']=='u001']) if not df_t.empty else 0, "inventory_count": len(df_i[df_i['user_id']=='u001']) if not df_i.empty else 0, "export_date": str(datetime.now())}
        json_str = json.dumps(export_data, ensure_ascii=False, indent=2)
        st.download_button("📥 データをJSONでエクスポート", data=json_str, file_name=f"lifequest_export_{today}.json", mime="application/json", key="export_json_btn")
    except Exception as e:
        st.caption(f"エクスポート: {e}")

if __name__ == "__main__":
    main()