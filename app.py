import os
import re
import time
import random
import threading

import requests
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", os.urandom(32))
socketio = SocketIO(app, async_mode="threading")

WIKI_LANG = os.environ.get("WIKI_LANG", "fr")
WIKI_RANDOM_URL = f"https://{WIKI_LANG}.wikipedia.org/api/rest_v1/page/random/summary"
HEADERS = {"User-Agent": "WikiQuizLive/1.0 (educational quiz game)"}

ROUND_DURATION = 15   # secondes pour répondre
REVEAL_DURATION = 6   # secondes d'affichage du résultat entre deux manches

# ---------------- ÉTAT DU JEU (en mémoire, une seule partie globale) ----------------
game_lock = threading.Lock()
state = {
    "round_id": 0,
    "question": None,      # {"snippet", "choices", "correct", "url"}
    "round_start": None,
    "answers": {},          # sid -> {"choice", "elapsed"}
    "scores": {},            # nom -> score
    "sid_names": {},          # sid -> nom
}
game_started = False
game_started_lock = threading.Lock()


# ---------------- WIKIPÉDIA ----------------
def fetch_summary():
    try:
        r = requests.get(WIKI_RANDOM_URL, headers=HEADERS, timeout=6)
        if r.status_code != 200:
            return None
        data = r.json()
        extract = data.get("extract", "")
        title = data.get("title", "")
        if len(extract) < 100 or "peut faire référence" in extract.lower():
            return None
        if data.get("type") == "disambiguation":
            return None
        return {
            "title": title,
            "extract": extract,
            "url": data.get("content_urls", {}).get("desktop", {}).get("page",
                    f"https://{WIKI_LANG}.wikipedia.org/wiki/{title}"),
        }
    except requests.RequestException:
        return None


def redact(text, title):
    words = [w for w in re.split(r"\s+", title) if len(w) > 2]
    parts = [re.escape(title)] + [re.escape(w) for w in words]
    pattern = re.compile("|".join(parts), re.IGNORECASE)
    return pattern.sub("█████", text)


def build_question(max_tries=8):
    correct = None
    for _ in range(max_tries):
        correct = fetch_summary()
        if correct:
            break
    if not correct:
        return None

    distractor_titles = set()
    attempts = 0
    while len(distractor_titles) < 3 and attempts < 12:
        attempts += 1
        d = fetch_summary()
        if d and d["title"] != correct["title"]:
            distractor_titles.add(d["title"])

    while len(distractor_titles) < 3:
        distractor_titles.add(f"Sujet mystère #{random.randint(100,999)}")

    choices = list(distractor_titles) + [correct["title"]]
    random.shuffle(choices)

    snippet = redact(correct["extract"], correct["title"])[:420]

    return {
        "snippet": snippet,
        "choices": choices,
        "correct": correct["title"],
        "url": correct["url"],
    }


def leaderboard_snapshot():
    ranked = sorted(state["scores"].items(), key=lambda kv: -kv[1])[:10]
    return [{"name": n, "score": s} for n, s in ranked]


# ---------------- BOUCLE DE JEU ----------------
def game_loop():
    while True:
        q = build_question()
        if not q:
            socketio.sleep(3)
            continue

        with game_lock:
            state["round_id"] += 1
            state["question"] = q
            state["round_start"] = time.time()
            state["answers"] = {}
            rid = state["round_id"]

        socketio.emit("new_question", {
            "round_id": rid,
            "snippet": q["snippet"],
            "choices": q["choices"],
            "duration": ROUND_DURATION,
        })

        socketio.sleep(ROUND_DURATION)

        with game_lock:
            correct = state["question"]["correct"]
            url = state["question"]["url"]
            for sid, ans in state["answers"].items():
                name = state["sid_names"].get(sid)
                if not name:
                    continue
                if ans["choice"] == correct:
                    bonus_ratio = max(0.0, (ROUND_DURATION - ans["elapsed"]) / ROUND_DURATION)
                    points = int(500 + 500 * bonus_ratio)
                    state["scores"][name] = state["scores"].get(name, 0) + points
            board = leaderboard_snapshot()

        socketio.emit("round_result", {
            "round_id": rid,
            "correct": correct,
            "url": url,
            "leaderboard": board,
        })

        socketio.sleep(REVEAL_DURATION)


def ensure_game_started():
    global game_started
    with game_started_lock:
        if not game_started:
            game_started = True
            socketio.start_background_task(game_loop)


# ---------------- ROUTES ----------------
@app.route("/")
def index():
    return render_template("game.html")


# ---------------- SOCKET ----------------
@socketio.on("connect")
def handle_connect():
    ensure_game_started()
    with game_lock:
        if state["question"] and state["round_start"]:
            elapsed = time.time() - state["round_start"]
            remaining = max(0, ROUND_DURATION - elapsed)
            if remaining > 0:
                emit("new_question", {
                    "round_id": state["round_id"],
                    "snippet": state["question"]["snippet"],
                    "choices": state["question"]["choices"],
                    "duration": remaining,
                })
        emit("leaderboard", {"leaderboard": leaderboard_snapshot()})


@socketio.on("join")
def handle_join(data):
    name = str((data or {}).get("name", "")).strip()[:20] or "Anonyme"
    with game_lock:
        state["sid_names"][request.sid] = name
        state["scores"].setdefault(name, 0)
    emit("joined", {"name": name})


@socketio.on("answer")
def handle_answer(data):
    sid = request.sid
    with game_lock:
        if state["round_start"] is None:
            return
        rid = (data or {}).get("round_id")
        if rid != state["round_id"]:
            return
        if sid in state["answers"]:
            return
        elapsed = time.time() - state["round_start"]
        if elapsed > ROUND_DURATION:
            return
        state["answers"][sid] = {"choice": (data or {}).get("choice"), "elapsed": elapsed}
    emit("answer_locked", {"choice": (data or {}).get("choice")})


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    with game_lock:
        state["sid_names"].pop(sid, None)
        state["answers"].pop(sid, None)


# ---------------- RUN ----------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    socketio.run(app, host="0.0.0.0", port=port)
