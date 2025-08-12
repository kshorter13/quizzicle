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
# Make sure "Loading image.jpeg" is in the same directory as this script.
LOGO_URL = "Loading image.jpeg"
# REMINDER: Change this to your deployed app's URL
PLAYER_MODE_URL = "https://blank-app-s5sx65i2mng.streamlit.app/"

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🏆",
    layout="wide",
)

# --- Custom CSS for Styling ---
def local_css(file_name):
    """Loads a custom CSS file."""
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        st.error(f"Could not find {file_name}. A default style will be used.")

# Create a dummy style.css file to avoid errors if it doesn't exist
with open("style.css", "w") as f:
    f.write("""
    /* General Body Styles */
    body {
        font-family: 'Poppins', sans-serif;
        color: #31333F;
    }
    /* Main App Container */
    [data-testid="stAppViewContainer"] {
        background-color: #f0f2f6;
    }
    /* Streamlit's main content area */
    .st-emotion-cache-1cypcdp {
        background-image: linear-gradient(to top, #d9addd 0%, #f6e6f7 100%);
    }
    /* Sidebar Styling */
    [data-testid="stSidebar"] {
        background-color: rgba(255, 255, 255, 0.5);
        backdrop-filter: blur(10px);
    }
    /* Main Content Styling for containers */
    .main-content {
        background-color: rgba(255, 255, 255, 0.7);
        padding: 2rem;
        border-radius: 15px;
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.18);
        box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
        height: 100%;
    }
    /* Button Styling */
    .stButton > button {
        border: 2px solid #ffffff;
        border-radius: 10px;
        color: #ffffff;
        background-color: #c96b99;
        padding: 10px 20px;
        font-weight: bold;
        transition: all 0.3s ease;
    }
    .stButton > button:hover {
        background-color: #ffffff;
        color: #c96b99;
        border-color: #c96b99;
    }
    /* Special button for answers */
    .stButton > button[kind="secondary"] {
        background-color: #e59954;
    }
    .stButton > button[kind="secondary"]:hover {
        color: #e59954;
        border-color: #e59954;
    }
    /* Small buttons for navigation on mobile */
    .stButton > button[data-testid="baseButton-secondary"] {
        background-color: #e59954;
    }
    /* Text Input Styling */
    .stTextInput > div > div > input {
        border-radius: 10px;
        border: 2px solid #d9addd;
        background-color: #f0f2f6;
    }
    /* Title Styling */
    h1, h2, h3 {
        color: #31333F;
    }
    /* Game PIN Display */
    .game-pin-display {
        font-size: 3rem;
        font-weight: bold;
        color: #e59954;
        text-align: center;
        background-color: #ffffff;
        padding: 1rem;
        border-radius: 10px;
        letter-spacing: 0.5rem;
        border: 3px dashed #d9addd;
    }
    /* Mobile-specific adjustments */
    @media (max-width: 768px) {
        .main-content {
            padding: 1rem;
        }
        .game-pin-display {
            font-size: 2rem;
            letter-spacing: 0.2rem;
        }
        [data-testid="stSidebar"] {
            display: none; /* Hide sidebar on mobile */
        }
        .stButton > button {
            padding: 8px 16px;
        }
    }
    """)
local_css("style.css")

# --- Firebase Authentication ---
try:
    if "db" not in st.session_state:
        st.session_state.db = firestore.Client.from_service_account_info(
            st.secrets["FIRESTORE_CREDENTIALS"]
        )
except Exception as e:
    st.error("🔥 Firebase connection failed. Have you set up your Streamlit secrets correctly?")
    st.stop()

# --- Helper Functions ---
def parse_text_quiz(text_contents):
    """Parses a plain text file into a list of quiz question dictionaries."""
    quiz_data, current_question = [], None
    for line in text_contents.strip().split('\n'):
        line = line.strip()
        if not line and current_question:
            if all(k in current_question for k in ['question', 'options', 'answer']):
                quiz_data.append(current_question)
            current_question = None
        elif line.startswith("Q:") and not current_question:
            current_question = {"options": []}
            current_question["question"] = line[2:].strip()
        elif line.startswith("O:") and current_question:
            current_question["options"].append(line[2:].strip())
        elif line.startswith("A:") and current_question:
            current_question["answer"] = line[2:].strip()
    if current_question and all(k in current_question for k in ['question', 'options', 'answer']):
        quiz_data.append(current_question)
    return quiz_data

# --- Firestore Functions ---
def generate_game_pin():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def create_game_session(host_name, quiz_data, quiz_mode, time_per_question):
    game_pin = generate_game_pin()
    game_ref = st.session_state.db.collection("games").document(game_pin)
    game_data = {
        "host": host_name, "players": {}, "questions": random.sample(quiz_data, len(quiz_data)),
        "current_question_index": -1, "status": "waiting", "created_at": firestore.SERVER_TIMESTAMP,
        "quiz_mode": quiz_mode, "time_per_question": int(time_per_question) if time_per_question else None,
        "question_start_time": None
    }
    game_ref.set(game_data)
    return game_pin

def get_game_state(game_pin):
    if not game_pin: return None
    game_doc = st.session_state.db.collection("games").document(game_pin).get()
    return game_doc.to_dict() if game_doc.exists else None

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

def update_game_state(game_pin, new_state):
    st.session_state.db.collection("games").document(game_pin).update(new_state)

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
    except Exception:
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
            if "HOST_PASSWORD" in st.secrets and password == st.secrets["HOST_PASSWORD"]:
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
        time_per_q = None
        if quiz_mode == "Timed Questions (Instructor-Led)":
            time_per_q = st.number_input("Time per question (seconds):", 10, 300, 60, 10)
        with st.expander("Click to see TXT format example"):
            st.code("Q: What is 2+2?\nO: 3\nO: 4\nO: 5\nA: 4", language="text")
        if st.session_state.get('create_game_error'):
            st.error(st.session_state.create_game_error)
        if st.button("Create New Game", use_container_width=True):
            if not host_name or not uploaded_file:
                st.session_state.create_game_error = "Please enter your name and upload a quiz file."
            else:
                try:
                    quiz_data = parse_text_quiz(io.StringIO(uploaded_file.getvalue().decode("utf-8")).read())
                    if quiz_data:
                        mode_map = {"Instructor-Paced": "instructor_paced", "Timed Questions (Instructor-Led)": "timed_paced"}
                        st.session_state.game_pin = create_game_session(host_name, quiz_data, mode_map[quiz_mode], time_per_q)
                        st.session_state.create_game_error = None
                    else:
                        st.session_state.create_game_error = "Invalid TXT format or empty file."
                except Exception as e:
                    st.session_state.create_game_error = f"An unexpected error occurred: {e}"
            st.rerun()

def host_game_screen():
    game_pin = st.session_state.game_pin
    game_state = get_game_state(game_pin)
    if not game_state:
        st.error("Game not found.")
        del st.session_state.game_pin
        st.rerun()
    
    if game_state['status'] != 'finished':
        st_autorefresh(interval=2000, key="host_refresher")

    c1, c2 = st.columns([1, 2])
    with c1:
        show_game_logo()
        with st.container(border=True):
            st.header("🎮 Game Info")
            st.markdown(f"<div class='game-pin-display'>{game_pin}</div>", unsafe_allow_html=True)
            qr_img = qrcode.make(f"{PLAYER_MODE_URL}?pin={game_pin}")
            buf = io.BytesIO()
            qr_img.save(buf, format="PNG")
            st.image(buf, caption="Scan to join", use_container_width=True)
        with st.container(border=True):
            show_leaderboard(game_state.get("players", {}))

    with c2:
        with st.container(border=True):
            if game_state["status"] == "waiting":
                st.subheader("Waiting for players to join...")
                st.info(f"Current Players: {len(game_state.get('players', {}))}")
                if st.button("Start Game", disabled=not game_state.get("players"), use_container_width=True):
                    update_data = {"status": "in_progress", "current_question_index": 0}
                    if game_state.get("quiz_mode") == "timed_paced":
                        update_data["question_start_time"] = firestore.SERVER_TIMESTAMP
                    update_game_state(game_pin, update_data)
                    st.rerun()

            elif game_state["status"] == "in_progress":
                current_q_index = game_state['current_question_index']
                question = game_state["questions"][current_q_index]
                st.subheader(f"Question {current_q_index + 1}/{len(game_state['questions'])}")
                st.title(question["question"])
                
                if game_state['quiz_mode'] == 'timed_paced':
                    time_per_q = game_state.get("time_per_question", 60)
                    start_time = game_state.get("question_start_time")
                    time_left = time_per_q
                    if start_time:
                        time_left = max(0, time_per_q - (time.time() - start_time.timestamp()))
                    st.progress(time_left / time_per_q, text=f":alarm_clock: {math.ceil(time_left)} seconds remaining")

                st.markdown("---")
                for i, option in enumerate(question["options"]):
                    st.markdown(f"{['🟥', '🔷', '🟡', '💚'][i]} {option}")
                st.markdown("---")
                if st.toggle("Show Correct Answer"):
                    st.success(f"**Answer:** {question['answer']}")
                
                if st.button("Next Question", use_container_width=True, type="primary"):
                    next_q = current_q_index + 1
                    if next_q < len(game_state["questions"]):
                        update_data = {"current_question_index": next_q}
                        if game_state['quiz_mode'] == 'timed_paced':
                            update_data["question_start_time"] = firestore.SERVER_TIMESTAMP
                        update_game_state(game_pin, update_data)
                    else:
                        update_game_state(game_pin, {"status": "finished"})
                    st.rerun()

            elif game_state["status"] == "finished":
                st.balloons()
                st.header("🎉 Quiz Finished! 🎉")
                with st.expander("See Question Summary"):
                    for i, q in enumerate(game_state['questions']):
                        st.markdown(f"**Q{i+1}:** {q['question']}")
                        st.success(f"**Answer:** {q['answer']}")
                        st.markdown("---")

def player_join_screen():
    with st.container(border=True):
        st.header("🧑‍🎓 Join a Game")
        pin = st.text_input("Enter Game PIN:", max_chars=4)
        name = st.text_input("Enter Your Name:")
        if st.button("Join Game", use_container_width=True):
            if pin and name:
                success, msg = join_game(pin.upper(), name)
                if success:
                    st.session_state.game_pin, st.session_state.player_name = pin.upper(), name
                    st.rerun()
                else:
                    st.error(msg)
            else:
                st.error("Please enter a Game PIN and your name.")

def player_game_screen():
    game_pin, player_name = st.session_state.game_pin, st.session_state.player_name
    game_state = get_game_state(game_pin)
    if not game_state:
        st.error("Game session ended.")
        del st.session_state.game_pin, st.session_state.player_name
        st.rerun()

    if game_state['status'] != 'finished':
        st_autorefresh(interval=2000, key="player_refresher")

    players = game_state.get("players", {})
    st.sidebar.info(f"Playing as: **{player_name}** | Score: **{players.get(player_name, {}).get('score', 0)}**")
    show_leaderboard(players)

    with st.container(border=True):
        if game_state["status"] == "waiting":
            st.info("⏳ Waiting for the host to start the game...")
        
        elif game_state["status"] == "in_progress":
            current_q_index = game_state['current_question_index']
            question = game_state["questions"][current_q_index]
            
            time_left, time_per_q = None, None
            if game_state['quiz_mode'] == 'timed_paced':
                time_per_q = game_state.get("time_per_question", 60)
                start_time = game_state.get("question_start_time")
                if start_time:
                    time_left = max(0, time_per_q - (time.time() - start_time.timestamp()))
                    st.progress(time_left / time_per_q, text=f":alarm_clock: {math.ceil(time_left)} seconds remaining")

            is_answered = f"answered_{current_q_index}" in st.session_state
            is_time_up = time_left is not None and time_left == 0
            
            if is_answered or is_time_up:
                st.info("Waiting for the host to show the next question...")
                if is_time_up and not is_answered: st.warning("Time's up for that question!")
            else:
                st.subheader(f"Question {current_q_index + 1}")
                st.title(question["question"])
                for i, option in enumerate(question["options"]):
                    if st.button(f"{['🟥', '🔷', '🟡', '💚'][i]} {option}", use_container_width=True, key=f"opt_{i}"):
                        st.session_state[f"answered_{current_q_index}"] = True
                        if option == question["answer"]:
                            st.balloons()
                            st.success("Correct!")
                            st.session_state.db.collection("games").document(game_pin).update({f"players.{player_name}.score": firestore.Increment(1)})
                        else:
                            st.error("Incorrect!")
                        time.sleep(1) # Show feedback briefly
                        st.rerun()

        elif game_state["status"] == "finished":
            st.balloons()
            st.header("🎉 Quiz Finished! 🎉")
            st.subheader("Your Results")
            sorted_players = sorted(players.items(), key=lambda item: item[1].get('score', 0), reverse=True)
            player_rank = next((i for i, (name, _) in enumerate(sorted_players) if name == player_name), None)
            
            if player_rank is not None:
                st.metric("Your Final Score", players.get(player_name, {}).get('score', 0))
                st.metric("Your Rank", f"#{player_rank + 1} of {len(sorted_players)} players")
            st.markdown("---")
            st.subheader("Final Leaderboard")
            for i, (name, data) in enumerate(sorted_players):
                medal = "🥇" if i == 0 else "🥈" if i == 1 else "🥉" if i == 2 else ""
                st.markdown(f"**{medal} {name}**: {data.get('score', 0)}")


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
