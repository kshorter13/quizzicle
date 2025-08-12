import streamlit as st
import time
import random
import string
import io
import qrcode
from PIL import Image
from google.cloud import firestore
from streamlit_autorefresh import st_autorefresh
import math

# --- App Branding and Configuration ---
APP_NAME = "Quizzicle"
LOGO_URL = "Loading image.jpeg"
PLAYER_MODE_URL = "https://blank-app-s5sx65i2mng.streamlit.app/" # REMINDER: Change this URL

st.set_page_config(page_title=APP_NAME, page_icon="🏆", layout="wide")

# --- Custom CSS for Styling ---
def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"Could not find {file_name}. A default style will be used.")

with open("style.css", "w") as f:
    f.write("""
    /* General Styles */
    body { font-family: 'Poppins', sans-serif; color: #31333F; }
    [data-testid="stAppViewContainer"] { background-color: #f0f2f6; }
    .st-emotion-cache-1cypcdp { background-image: linear-gradient(to top, #d9addd 0%, #f6e6f7 100%); }
    [data-testid="stSidebar"] { background-color: rgba(255, 255, 255, 0.5); backdrop-filter: blur(10px); }
    .stButton > button { border: 2px solid #ffffff; border-radius: 10px; color: #ffffff; background-color: #c96b99; padding: 10px 20px; font-weight: bold; transition: all 0.3s ease; }
    .stButton > button:hover { background-color: #ffffff; color: #c96b99; border-color: #c96b99; }
    .stTextInput > div > div > input { border-radius: 10px; border: 2px solid #d9addd; background-color: #f0f2f6; }
    h1, h2, h3 { color: #31333F; }
    .game-pin-display { font-size: 3rem; font-weight: bold; color: #e59954; text-align: center; background-color: #ffffff; padding: 1rem; border-radius: 10px; letter-spacing: 0.5rem; border: 3px dashed #d9addd; }
    @media (max-width: 768px) { .game-pin-display { font-size: 2rem; letter-spacing: 0.2rem; } [data-testid="stSidebar"] { display: none; } }
    """)
local_css("style.css")

# --- Firebase Authentication ---
try:
    if "db" not in st.session_state:
        st.session_state.db = firestore.Client.from_service_account_info(st.secrets["FIRESTORE_CREDENTIALS"])
except Exception as e:
    st.error("🔥 Firebase connection failed. Have you set up your Streamlit secrets correctly?")
    st.stop()

# --- Helper & Firestore Functions ---
def parse_text_quiz(text_contents):
    quiz_data, current_question = [], None
    for line in text_contents.strip().split('\n'):
        line = line.strip()
        if not line and current_question:
            if all(k in current_question for k in ['question', 'options', 'answer']): quiz_data.append(current_question)
            current_question = None
        elif line.startswith("Q:") and not current_question:
            current_question = {"options": []}
            current_question["question"] = line[2:].strip()
        elif line.startswith("O:") and current_question: current_question["options"].append(line[2:].strip())
        elif line.startswith("A:") and current_question: current_question["answer"] = line[2:].strip()
    if current_question and all(k in current_question for k in ['question', 'options', 'answer']):
        quiz_data.append(current_question)
    return quiz_data

def get_game_state(game_pin):
    if not game_pin: return None
    return st.session_state.db.collection("games").document(game_pin).get().to_dict()

def update_game_state(game_pin, new_state):
    st.session_state.db.collection("games").document(game_pin).update(new_state)

def calculate_final_scores(game_state):
    """Calculates scores for all players based on their stored answers."""
    questions = game_state.get('questions', [])
    players = game_state.get('players', {})
    for player_name, player_data in players.items():
        score = 0
        player_answers = player_data.get('answers', {})
        for q_idx, answer in player_answers.items():
            try:
                if answer == questions[int(q_idx)]['answer']:
                    score += 1
            except (IndexError, KeyError):
                continue # Skip if question index is invalid
        players[player_name]['score'] = score
    return players

def create_game_session(host_name, quiz_data, quiz_mode, time_per_question):
    game_pin = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    game_ref = st.session_state.db.collection("games").document(game_pin)
    game_data = {
        "host": host_name, "players": {}, "questions": random.sample(quiz_data, len(quiz_data)),
        "current_question_index": -1, "status": "waiting", "created_at": firestore.SERVER_TIMESTAMP,
        "quiz_mode": quiz_mode, "time_per_question": int(time_per_question) if time_per_question else None,
        "question_start_time": None
    }
    game_ref.set(game_data)
    return game_pin

def join_game(game_pin, player_name):
    game_ref = st.session_state.db.collection("games").document(game_pin)
    @firestore.transactional
    def update_in_transaction(transaction, game_ref, player_name):
        snapshot = game_ref.get(transaction=transaction)
        if not snapshot.exists: return False, "Game not found."
        players = snapshot.get("players")
        if player_name in players: return False, "This name is already taken."
        players[player_name] = {"score": 0}
        transaction.update(game_ref, {"players": players})
        return True, "Success."
    return update_in_transaction(st.session_state.db.transaction(), game_ref, player_name)

# --- UI Components ---
def show_leaderboard(players):
    st.sidebar.header("🏆 Leaderboard")
    if not players:
        st.sidebar.write("No players yet...")
        return
    sorted_players = sorted(players.items(), key=lambda item: item[1].get('score', 0), reverse=True)
    for i, (name, data) in enumerate(sorted_players):
        medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else ""
        st.sidebar.markdown(f"**{medal} {name}**: {data.get('score', 0)}")

def show_game_logo():
    try:
        st.image(LOGO_URL, width=100, use_container_width=False)
    except:
        st.write(f"_{APP_NAME}_")

# --- Screen Definitions ---
def main_selection_screen():
    with st.container(border=True):
        st.header("👋 Welcome! Are you a Host or a Player?")
        c1, c2 = st.columns(2)
        if c1.button("👩‍🏫 I am the Host", use_container_width=True):
            st.session_state.show_host_password_prompt = True
            st.rerun()
        if c2.button("🧑‍🎓 I am a Player", use_container_width=True, type="secondary"):
            st.session_state.role = "player"
            st.rerun()

def host_login_screen():
    with st.container(border=True):
        st.header("🔑 Host Login")
        password = st.text_input("Enter Host Password:", type="password")
        if st.button("Login", use_container_width=True):
            if st.secrets.get("HOST_PASSWORD") and password == st.secrets["HOST_PASSWORD"]:
                st.session_state.role, st.session_state.show_host_password_prompt = "host", False
                st.rerun()
            else:
                st.error("Incorrect password.")
        if st.button("Back", use_container_width=True):
            st.session_state.show_host_password_prompt = False
            st.rerun()

def host_create_game_screen():
    with st.container(border=True):
        st.header("✨ Create a New Game")
        host_name = st.text_input("Enter your name as Host:")
        uploaded_file = st.file_uploader("Upload Quiz TXT file", type="txt")
        quiz_mode = st.radio("Select Quiz Mode:", ("Instructor-Paced", "Timed Questions (Instructor-Led)"), horizontal=True)
        time_per_q = 60 if quiz_mode == "Timed Questions (Instructor-Led)" else None
        if quiz_mode == "Timed Questions (Instructor-Led)":
            time_per_q = st.number_input("Time per question (seconds):", 10, 300, 60, 10)
        with st.expander("See TXT format example"):
            st.code("Q: What is 2+2?\nO: 3\nO: 4\nO: 5\nA: 4", language="text")
        if 'create_game_error' in st.session_state: st.error(st.session_state.create_game_error)
        if st.button("Create New Game", use_container_width=True):
            if not host_name or not uploaded_file:
                st.session_state.create_game_error = "Please enter your name and upload a quiz file."
            else:
                try:
                    quiz_data = parse_text_quiz(io.StringIO(uploaded_file.getvalue().decode("utf-8")).read())
                    if quiz_data:
                        mode_map = {"Instructor-Paced": "instructor_paced", "Timed Questions (Instructor-Led)": "timed_paced"}
                        st.session_state.game_pin = create_game_session(host_name, quiz_data, mode_map[quiz_mode], time_per_q)
                        if 'create_game_error' in st.session_state: del st.session_state.create_game_error
                    else:
                        st.session_state.create_game_error = "Invalid TXT format or empty file."
                except Exception as e:
                    st.session_state.create_game_error = f"An unexpected error: {e}"
            st.rerun()

def host_game_screen():
    game_pin = st.session_state.game_pin
    game_state = get_game_state(game_pin)
    if not game_state:
        st.error("Game not found."); del st.session_state.game_pin; st.rerun()
    
    if game_state['status'] != 'finished':
        st_autorefresh(interval=2000, key="host_refresher")

    c1, c2 = st.columns([1, 2])
    with c1:
        show_game_logo()
        with st.container(border=True):
            st.header("🎮 Game Info")
            st.markdown(f"<div class='game-pin-display'>{game_pin}</div>", unsafe_allow_html=True)
            qr = qrcode.make(f"{PLAYER_MODE_URL}?pin={game_pin}"); buf = io.BytesIO(); qr.save(buf, "PNG"); st.image(buf)
        with st.container(border=True):
            show_leaderboard(game_state.get("players", {}))

    with c2, st.container(border=True):
        status = game_state["status"]
        if status == "waiting":
            st.subheader("Waiting for players...")
            st.info(f"Current Players: {len(game_state.get('players', {}))}")
            if st.button("Start Game", disabled=not game_state.get("players"), use_container_width=True):
                update_data = {"status": "in_progress", "current_question_index": 0}
                if game_state.get("quiz_mode") == "timed_paced":
                    update_data["question_start_time"] = firestore.SERVER_TIMESTAMP
                update_game_state(game_pin, update_data)
                st.rerun()

        elif status == "in_progress":
            q_idx = game_state['current_question_index']
            questions = game_state['questions']
            question = questions[q_idx]
            is_last_question = q_idx == len(questions) - 1

            st.subheader(f"Question {q_idx + 1}/{len(questions)}")
            st.title(question["question"])
            
            if game_state['quiz_mode'] == 'timed_paced':
                time_per_q = game_state.get("time_per_question", 60)
                start_time = game_state.get("question_start_time")
                time_left = time_per_q if not start_time else max(0, time_per_q - (time.time() - start_time.timestamp()))
                st.progress(time_left / time_per_q, text=f":alarm_clock: {math.ceil(time_left)}s")
                if is_last_question and time_left == 0 and not game_state.get('calculating'):
                    update_game_state(game_pin, {"calculating": True})
                    final_scores = calculate_final_scores(get_game_state(game_pin))
                    update_game_state(game_pin, {"status": "finished", "players": final_scores, "calculating": firestore.DELETE_FIELD})
                    st.rerun()
            
            st.markdown("---")
            for i, opt in enumerate(question["options"]): st.markdown(f"{['🟥', '🔷', '🟡', '💚'][i]} {opt}")
            st.markdown("---")
            if st.toggle("Show Correct Answer"): st.success(f"**Answer:** {question['answer']}")
            
            if st.button("Next Question" if not is_last_question else "Finish Quiz", use_container_width=True, type="primary"):
                if not is_last_question:
                    update_data = {"current_question_index": q_idx + 1}
                    if game_state['quiz_mode'] == 'timed_paced':
                        update_data["question_start_time"] = firestore.SERVER_TIMESTAMP
                    update_game_state(game_pin, update_data)
                else:
                    final_scores = calculate_final_scores(game_state)
                    update_game_state(game_pin, {"status": "finished", "players": final_scores})
                st.rerun()
        
        elif status == "finished":
            st.balloons(); st.header("🎉 Quiz Finished! 🎉")
            with st.expander("See Question Summary"):
                for i, q in enumerate(game_state['questions']):
                    st.markdown(f"**Q{i+1}:** {q['question']} -> **Answer:** {q['answer']}")
                    st.markdown("---")

def player_join_screen():
    with st.container(border=True):
        st.header("🧑‍🎓 Join a Game")
        pin = st.text_input("Enter Game PIN:", max_chars=4).upper()
        name = st.text_input("Enter Your Name:")
        if st.button("Join Game", use_container_width=True):
            if pin and name:
                success, msg = join_game(pin, name)
                if success: st.session_state.game_pin, st.session_state.player_name = pin, name; st.rerun()
                else: st.error(msg)
            else: st.error("Please enter a Game PIN and your name.")

def player_game_screen():
    game_pin, player_name = st.session_state.game_pin, st.session_state.player_name
    game_state = get_game_state(game_pin)
    if not game_state:
        st.error("Game session ended.")
        if st.button("Return to Join Screen"):
            del st.session_state.game_pin
            del st.session_state.player_name
            st.rerun()
        st.stop()

    if game_state['status'] != 'finished':
        st_autorefresh(interval=2000, key="player_refresher")

    players = game_state.get("players", {})
    st.sidebar.info(f"Playing as: **{player_name}** | Score: **{players.get(player_name, {}).get('score', 0)}**")
    show_leaderboard(players)

    with st.container(border=True):
        status = game_state["status"]
        if status == "waiting":
            st.info("⏳ Waiting for the host to start the game...")
        
        elif status == "in_progress":
            q_idx = game_state['current_question_index']
            question = game_state["questions"][q_idx]
            quiz_mode = game_state['quiz_mode']
            
            if quiz_mode == 'instructor_paced':
                is_answered = f"answered_{q_idx}" in st.session_state
                if is_answered:
                    feedback_message = st.session_state.get(f"feedback_{q_idx}", "")
                    if "Correct" in feedback_message: st.success(feedback_message)
                    else: st.error(feedback_message)
                    st.info("Waiting for the host to show the next question...")
                else:
                    st.subheader(f"Question {q_idx + 1}")
                    st.title(question["question"])
                    for i, option in enumerate(question["options"]):
                        if st.button(f"{['🟥', '🔷', '🟡', '💚'][i]} {option}", use_container_width=True, key=f"opt_{i}"):
                            st.session_state[f"answered_{q_idx}"] = True
                            if option == question["answer"]:
                                st.balloons()
                                st.session_state[f"feedback_{q_idx}"] = "✅ Correct!"
                                update_game_state(game_pin, {f"players.{player_name}.score": firestore.Increment(1)})
                            else:
                                st.session_state[f"feedback_{q_idx}"] = f"❌ Incorrect! The correct answer was: {question['answer']}"
                            st.rerun()

            elif quiz_mode == 'timed_paced':
                is_answered = f"answered_{q_idx}" in st.session_state
                time_per_q = game_state.get("time_per_question", 60)
                start_time = game_state.get("question_start_time")
                time_left = time_per_q if not start_time else max(0, time_per_q - (time.time() - start_time.timestamp()))
                st.progress(time_left / time_per_q, text=f":alarm_clock: {math.ceil(time_left)}s")
                is_time_up = time_left == 0
                
                if is_answered or is_time_up:
                    st.info("Waiting for the next question...")
                    if is_time_up and not is_answered: st.warning("Time's up!")
                else:
                    st.subheader(f"Question {q_idx + 1}")
                    st.title(question["question"])
                    for i, option in enumerate(question["options"]):
                        if st.button(f"{['🟥', '🔷', '🟡', '💚'][i]} {option}", use_container_width=True):
                            st.session_state[f"answered_{q_idx}"] = True
                            update_game_state(game_pin, {f"players.{player_name}.answers.{q_idx}": option})
                            st.info("Your answer has been recorded!")
                            time.sleep(0.5)
                            st.rerun()

        elif status == "finished":
            if 'final_celebration' not in st.session_state:
                st.balloons(); st.session_state.final_celebration = True
            
            st.header("🎉 Quiz Finished! 🎉")
            st.subheader("Your Results")
            sorted_players = sorted(players.items(), key=lambda item: item[1].get('score', 0), reverse=True)
            rank = next((i for i, (name, _) in enumerate(sorted_players) if name == player_name), None)
            
            if rank is not None:
                st.metric("Your Final Score", players.get(player_name, {}).get('score', 0))
                st.metric("Your Rank", f"#{rank + 1} of {len(sorted_players)}")
            
            if game_state['quiz_mode'] == 'timed_paced':
                with st.expander("See your results"):
                    for i, q in enumerate(game_state['questions']):
                        my_ans = players.get(player_name, {}).get('answers', {}).get(str(i))
                        correct_ans = q['answer']
                        st.markdown(f"**Q{i+1}:** {q['question']}")
                        if my_ans:
                            feedback = "✅ Correct" if my_ans == correct_ans else f"❌ Incorrect (Correct: {correct_ans})"
                            st.info(f"You answered: {my_ans} - {feedback}")
                        else:
                            st.warning(f"You did not answer. (Correct: {correct_ans})")
                        st.markdown("---")

# --- Main App Router ---
if 'role' not in st.session_state: st.session_state.role = None
if 'show_host_password_prompt' not in st.session_state: st.session_state.show_host_password_prompt = False

if st.session_state.role is None:
    if st.session_state.show_host_password_prompt: host_login_screen()
    else: main_selection_screen()
elif st.session_state.role == "host":
    if 'game_pin' not in st.session_state: host_create_game_screen()
    else: host_game_screen()
elif st.session_state.role == "player":
    if 'game_pin' not in st.session_state: player_join_screen()
    else: player_game_screen()
