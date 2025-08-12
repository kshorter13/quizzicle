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

# --- Helper function to parse the text file ---
def parse_text_quiz(text_contents):
    """Parses a plain text file into a list of quiz question dictionaries."""
    quiz_data = []
    current_question = None
    lines = text_contents.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            if current_question and 'question' in current_question and 'answer' in current_question and current_question.get('options'):
                quiz_data.append(current_question)
            current_question = None
            continue
        if current_question is None:
            current_question = {"options": []}
        if line.startswith("Q:"):
            current_question["question"] = line[2:].strip()
        elif line.startswith("O:"):
            current_question["options"].append(line[2:].strip())
        elif line.startswith("A:"):
            current_question["answer"] = line[2:].strip()
    if current_question and 'question' in current_question and 'answer' in current_question and current_question.get('options'):
        quiz_data.append(current_question)
    return quiz_data

# --- Firestore Functions ---
def generate_game_pin():
    """Generates a random 4-character alphanumeric game pin."""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))

def create_game_session(host_name, quiz_data, quiz_mode, time_per_question):
    """Creates a new game session in Firestore."""
    game_pin = generate_game_pin()
    game_ref = st.session_state.db.collection("games").document(game_pin)
    shuffled_questions = random.sample(quiz_data, len(quiz_data))
    game_data = {
        "host": host_name, "players": {}, "questions": shuffled_questions,
        "current_question_index": -1, "status": "waiting",
        "created_at": firestore.SERVER_TIMESTAMP,
        "quiz_mode": quiz_mode,
        "time_per_question": int(time_per_question) if time_per_question else None,
        "question_start_time": None
    }
    game_ref.set(game_data)
    return game_pin

def get_game_state(game_pin):
    """Fetches the current game state from Firestore."""
    if not game_pin: return None
    game_ref = st.session_state.db.collection("games").document(game_pin)
    game_doc = game_ref.get()
    return game_doc.to_dict() if game_doc.exists else None

def join_game(game_pin, player_name):
    """Adds a new player to a game session."""
    game_ref = st.session_state.db.collection("games").document(game_pin)
    @firestore.transactional
    def update_in_transaction(transaction, game_ref, player_name):
        snapshot = game_ref.get(transaction=transaction)
        if not snapshot.exists:
            return False, "Game not found."
        players = snapshot.get("players")
        if player_name in players:
            return False, "This name is already taken."
        players[player_name] = {"score": 0, "last_answered_q": -1}
        transaction.update(game_ref, {"players": players})
        return True, "Success."
    
    success, message = update_in_transaction(st.session_state.db.transaction(), game_ref, player_name)
    return success, message

def update_game_state(game_pin, new_state):
    """Updates the game state in Firestore."""
    game_ref = st.session_state.db.collection("games").document(game_pin)
    game_ref.update(new_state)

# --- UI Components ---
def show_leaderboard(players):
    """Displays the leaderboard in the sidebar."""
    st.sidebar.header("🏆 Leaderboard")
    if not players:
        st.sidebar.write("No players yet...")
        return
    
    sorted_players = sorted(players.items(), key=lambda item: (item[1].get('score', 0) if isinstance(item[1], dict) else item[1]), reverse=True)
    
    for i, (name, score_data) in enumerate(sorted_players):
        medal = ""
        if i == 0: medal = "🥇"
        elif i == 1: medal = "🥈"
        elif i == 2: medal = "🥉"
        score = score_data.get('score', 0) if isinstance(score_data, dict) else score_data
        st.sidebar.markdown(f"**{medal} {name}**: {score}")

def show_game_logo_host():
    """Displays the Quizzicle logo for the host page."""
    with st.container():
        try:
            st.image(LOGO_URL, width=100, use_container_width=False)
        except Exception:
            st.write(f"_{APP_NAME}_") # Fallback if image not found
        st.write(" ")

# --- Callbacks ---
def next_question_callback():
    """Advances the quiz to the next question."""
    game_state = get_game_state(st.session_state.game_pin)
    current_q_index = game_state.get("current_question_index", -1)
    if current_q_index + 1 < len(game_state["questions"]):
        update_game_state(st.session_state.game_pin, {"current_question_index": current_q_index + 1})
        st.session_state[f"show_answer_{current_q_index+1}"] = False
    else:
        update_game_state(st.session_state.game_pin, {"status": "finished"})

# --- Screen Definitions ---
def main_selection_screen():
    """Initial screen for selecting Host or Player role."""
    with st.container(border=True):
        st.header("👋 Welcome! Are you a Host or a Player?")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("👩‍🏫 I am the Host", use_container_width=True, key="host_btn"):
                st.session_state.show_host_password_prompt = True
                st.rerun()
        with col2:
            if st.button("🧑‍🎓 I am a Player", use_container_width=True, type="secondary", key="player_btn"):
                st.session_state.role = "player"
                st.rerun()

def host_login_screen():
    """Screen for the host to enter their password."""
    with st.container(border=True):
        st.header("🔑 Host Login")
        password = st.text_input("Enter Host Password:", type="password", key="host_login_pwd")
        if st.button("Login", use_container_width=True, key="host_login_btn"):
            if "HOST_PASSWORD" in st.secrets and password == st.secrets["HOST_PASSWORD"]:
                st.session_state.role = "host"
                st.session_state.show_host_password_prompt = False
                st.rerun()
            else:
                st.error("Incorrect password.")
        if st.button("Back", use_container_width=True, key="back_from_login_btn"):
            st.session_state.show_host_password_prompt = False
            st.rerun()

def host_create_game_screen():
    """Screen for the host to create a new game."""
    with st.container(border=True):
        st.header("✨ Create a New Game")
        host_name = st.text_input("Enter your name as Host:", key="host_name_input")
        uploaded_file = st.file_uploader("Upload Quiz TXT file", type="txt", key="quiz_uploader")
        st.subheader("Quiz Settings")
        quiz_mode = st.radio(
            "Select Quiz Mode:",
            ("Instructor-Paced", "Participant-Paced with Timer"),
            horizontal=True, key="quiz_mode_select"
        )
        time_per_question = None
        if quiz_mode == "Participant-Paced with Timer":
            time_per_question = st.number_input(
                "Time per question (in seconds):",
                min_value=10, max_value=300, value=60, step=10,
                key="time_per_question_input"
            )
        with st.expander("Click to see TXT format example"):
            st.code("Q: What is 2+2?\nO: 3\nO: 4\nO: 5\nA: 4", language="text")

        if st.session_state.get('create_game_error'):
            st.error(st.session_state.create_game_error)

        if st.button("Create New Game", use_container_width=True, key="create_game_btn"):
            if not host_name:
                st.session_state.create_game_error = "Please enter your name as the host."
            elif not uploaded_file:
                st.session_state.create_game_error = "Please upload a quiz file."
            else:
                try:
                    stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
                    quiz_data = parse_text_quiz(stringio.read())
                    if quiz_data:
                        game_pin = create_game_session(host_name, quiz_data, quiz_mode.replace("-", "_").lower(), time_per_question)
                        st.session_state.game_pin = game_pin
                        st.session_state.create_game_error = None
                    else:
                        st.session_state.create_game_error = "Invalid TXT format or empty file."
                except Exception as e:
                    st.session_state.create_game_error = f"An unexpected error occurred: {e}"
            st.rerun()

def host_game_lobby_screen():
    """Screen for the host to manage the game lobby and questions."""
    game_pin = st.session_state.game_pin
    game_state = get_game_state(game_pin)

    if not game_state:
        st.error("Game not found. You may have to create a new game.")
        if st.button("Create New Game"):
            del st.session_state.game_pin
            st.rerun()
        st.stop()

    if game_state.get('status') == 'waiting':
        st_autorefresh(interval=2000, key="host_lobby_refresher")
    
    col_left, col_right = st.columns([1, 2])
    with col_left:
        show_game_logo_host()
        with st.container(border=True):
            st.header("🎮 Game Info")
            st.markdown(f"<div class='game-pin-display'>{game_pin}</div>", unsafe_allow_html=True)
            st.subheader("📲 Share Link & QR")
            qr_img = qrcode.make(f"{PLAYER_MODE_URL}?pin={game_pin}")
            buf = io.BytesIO()
            qr_img.save(buf, format="PNG")
            st.image(buf, caption="Scan to join", use_container_width=True)
        with st.container(border=True):
            st.subheader("🏆 Live Leaderboard")
            show_leaderboard(game_state.get("players", {}))

    with col_right:
        with st.container(border=True):
            if game_state["status"] == "waiting":
                st.subheader("Waiting for players to join...")
                st.info(f"Current Players: {len(game_state.get('players', {}))}")
                if st.button("Start Game", disabled=not game_state.get("players"), use_container_width=True):
                    update_data = {"status": "in_progress", "current_question_index": 0}
                    if game_state.get("quiz_mode") == "participant_paced_with_timer":
                        update_data["question_start_time"] = firestore.SERVER_TIMESTAMP
                    update_game_state(game_pin, update_data)
                    st.rerun()
            
            elif game_state["status"] == "in_progress":
                quiz_mode = game_state.get("quiz_mode")
                if quiz_mode == "instructor_paced":
                    current_q_index = game_state.get("current_question_index", -1)
                    question = game_state["questions"][current_q_index]
                    st.subheader(f"Question {current_q_index + 1}/{len(game_state['questions'])}")
                    st.title(question["question"])
                    st.markdown("---")
                    answer_icons = ["🟥", "🔷", "🟡", "💚"]
                    for i, option in enumerate(question["options"]):
                        st.markdown(f"{answer_icons[i]} {option}")
                    st.markdown("---")
                    if st.toggle("Show Answer", key=f"show_answer_{current_q_index}"):
                        st.success(f"**Correct Answer:** {question['answer']}")
                    if st.button("Next Question", use_container_width=True, type="primary"):
                        next_question_callback()
                        st.rerun()
                elif quiz_mode == "participant_paced_with_timer":
                    st.subheader("Quiz in Progress (Participant-Paced)")
                    st.info("Players are progressing through the quiz at their own pace.")
                    if st.button("End Quiz Early", use_container_width=True, type="primary"):
                        update_game_state(game_pin, {"status": "finished"})
                        st.rerun()

            elif game_state["status"] == "finished":
                st.balloons()
                st.header("🎉 Quiz Finished! 🎉")

def player_join_screen():
    """Screen for players to enter a game PIN and their name."""
    with st.container(border=True):
        st.header("🧑‍🎓 Join a Game")
        game_pin_input = st.text_input("Enter Game PIN:", key="player_game_pin", max_chars=4)
        player_name_input = st.text_input("Enter Your Name:", key="player_name_input")
        if st.button("Join Game", use_container_width=True):
            if game_pin_input and player_name_input:
                success, message = join_game(game_pin_input.upper(), player_name_input)
                if success:
                    st.session_state.game_pin = game_pin_input.upper()
                    st.session_state.player_name = player_name_input
                    st.rerun()
                else:
                    st.error(message)
            else:
                st.error("Please enter both a Game PIN and your name.")

def player_game_screen():
    """Main screen for players during the quiz."""
    game_pin = st.session_state.game_pin
    player_name = st.session_state.player_name
    game_state = get_game_state(game_pin)

    # FIX: Auto-refresh if the game is active, regardless of mode.
    if game_state and game_state.get("status") != "finished":
        st_autorefresh(interval=2000, key="player_game_refresher")

    if not game_state:
        st.error("Game session has ended.")
        if st.button("Return to Join Screen"):
            del st.session_state.game_pin
            del st.session_state.player_name
            st.rerun()
        st.stop()
    
    players_data = game_state.get("players", {})
    player_data = players_data.get(player_name, {})
    current_score = player_data.get('score', 0)
    
    st.sidebar.info(f"Playing as: **{player_name}** | Score: **{current_score}**")
    show_leaderboard(players_data)

    with st.container(border=True):
        if game_state["status"] == "waiting":
            st.info("⏳ Waiting for the host to start the game...")
        
        elif game_state["status"] == "in_progress":
            quiz_mode = game_state.get("quiz_mode")
            if quiz_mode == "instructor_paced":
                current_q_index_host = game_state.get("current_question_index", -1)
                if current_q_index_host > -1:
                    if f"answered_{current_q_index_host}" in st.session_state:
                        st.info("You've answered this question. Waiting for the host to move on.")
                    else:
                        question = game_state["questions"][current_q_index_host]
                        st.subheader(f"Question {current_q_index_host + 1}")
                        st.title(question["question"])
                        answer_icons = ["🟥", "🔷", "🟡", "💚"]
                        cols = st.columns(2)
                        for i, option in enumerate(question["options"]):
                            with cols[i % 2]:
                                if st.button(f"{answer_icons[i]} {option}", use_container_width=True, key=f"opt_{i}"):
                                    st.session_state[f"answered_{current_q_index_host}"] = True
                                    if option == question["answer"]:
                                        st.balloons()
                                        st.success("Correct!")
                                        st.session_state.db.collection("games").document(game_pin).update({f"players.{player_name}.score": firestore.Increment(1)})
                                    else:
                                        st.error("Incorrect!")
                                    st.rerun()
                else:
                     st.info("⏳ Waiting for the host to reveal the first question...")
            
            elif quiz_mode == "participant_paced_with_timer":
                player_last_answered_q = player_data.get('last_answered_q', -1)
                current_q_index = player_last_answered_q + 1
                total_questions = len(game_state["questions"])

                if current_q_index < total_questions:
                    question = game_state["questions"][current_q_index]
                    
                    time_per_question = game_state.get("time_per_question", 60)
                    question_start_time = game_state.get("question_start_time")
                    time_left = time_per_question
                    if question_start_time:
                        elapsed_time = time.time() - question_start_time.timestamp()
                        time_left = max(0, time_per_question - elapsed_time)
                    
                    if time_left == 0 and player_last_answered_q < current_q_index:
                        st.error("Time's up for this question!")
                        update_game_state(game_pin, {f"players.{player_name}.last_answered_q": current_q_index})
                        st.rerun()

                    st.markdown(f"**Time Remaining:** :alarm_clock: **{math.ceil(time_left)}** seconds")
                    st.subheader(f"Question {current_q_index + 1}/{total_questions}")
                    st.title(question["question"])
                    
                    answer_icons = ["🟥", "🔷", "🟡", "💚"]
                    cols = st.columns(2)
                    for i, option in enumerate(question["options"]):
                        with cols[i % 2]:
                            if st.button(f"{answer_icons[i]} {option}", use_container_width=True, key=f"paced_opt_{i}"):
                                update_data = {f"players.{player_name}.last_answered_q": current_q_index}
                                if option == question["answer"]:
                                    st.balloons()
                                    st.success("Correct!")
                                    update_data[f"players.{player_name}.score"] = firestore.Increment(1)
                                else:
                                    st.error("Incorrect!")
                                st.session_state.db.collection("games").document(game_pin).update(update_data)
                                st.rerun()
                else:
                    st.header("🎉 You've finished the quiz! 🎉")
                    st.info("Waiting for the host to end the game.")

        elif game_state["status"] == "finished":
            st.balloons()
            st.header("🎉 Quiz Finished! 🎉")
            st.subheader("Your Results")
            sorted_players = sorted(players_data.items(), key=lambda item: item[1].get('score', 0), reverse=True)
            player_rank = next((i for i, (name, _) in enumerate(sorted_players) if name == player_name), None)
            
            if player_rank is not None:
                st.metric(label="Your Final Score", value=current_score)
                st.metric(label="Your Rank", value=f"#{player_rank + 1} of {len(sorted_players)} players")

            st.markdown("---")
            st.subheader("Final Leaderboard")
            for i, (name, score_data) in enumerate(sorted_players):
                medal = ""
                if i == 0: medal = "🥇"
                elif i == 1: medal = "🥈"
                elif i == 2: medal = "🥉"
                st.markdown(f"**{medal} {name}**: {score_data.get('score', 0)}")


# --- Main App Logic ---
# Initialize session state variables
if 'role' not in st.session_state:
    st.session_state.role = None
if 'show_host_password_prompt' not in st.session_state:
    st.session_state.show_host_password_prompt = False
if 'create_game_error' not in st.session_state:
    st.session_state.create_game_error = None

# Main router to display the correct screen
if st.session_state.role is None:
    if st.session_state.show_host_password_prompt:
        host_login_screen()
    else:
        main_selection_screen()
elif st.session_state.role == "host":
    if 'game_pin' not in st.session_state:
        host_create_game_screen()
    else:
        host_game_lobby_screen()
elif st.session_state.role == "player":
    if 'game_pin' not in st.session_state or 'player_name' not in st.session_state:
        player_join_screen()
    else:
        player_game_screen()
