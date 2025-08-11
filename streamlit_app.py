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
PLAYER_MODE_URL = "https://your-streamlit-app-url.streamlit.app" # REMINDER: Change this to your deployed app's URL

st.set_page_config(
    page_title=APP_NAME,
    page_icon="🏆",
    layout="wide", # Use wide layout for better desktop experience
)

# --- Custom CSS for Styling ---
def local_css(file_name):
    """Loads a custom CSS file."""
    try:
        with open(file_name) as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except FileNotFoundError:
        # Create a dummy file if it doesn't exist for local development
        st.error(f"Could not find {file_name}. Please ensure it is in the same directory.")
        
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
    st.error("🔥 Firebase connection failed. Did you set up your Streamlit secret correctly?")
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
        "question_start_time": None # For participant-paced mode
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
        
        # Store player progress for participant-paced mode
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
    
    # Sort by score. For participant-paced mode, score is in a dict.
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
        st.image(LOGO_URL, width=100, use_container_width=False)
        st.write(" ")

# --- Main App Logic ---
if 'role' not in st.session_state:
    st.session_state.role = None
if 'show_host_password_prompt' not in st.session_state:
    st.session_state.show_host_password_prompt = False
if 'create_game_error' not in st.session_state:
    st.session_state.create_game_error = None

if st.session_state.get('role') == 'host' and 'game_pin' in st.session_state:
    game_state = get_game_state(st.session_state.game_pin)
    if game_state and game_state.get('status') == 'waiting':
        st_autorefresh(interval=2000, key="host_refresher")

def next_question_callback():
    game_state = get_game_state(st.session_state.game_pin)
    current_q_index = game_state.get("current_question_index", -1)
    if current_q_index + 1 < len(game_state["questions"]):
        update_game_state(st.session_state.game_pin, {
            "current_question_index": current_q_index + 1
        })
        st.session_state[f"show_answer_{current_q_index+1}"] = False
    else:
        update_game_state(st.session_state.game_pin, {"status": "finished"})

def player_game_screen():
    game_pin = st.session_state.game_pin
    player_name = st.session_state.player_name
    game_state = get_game_state(game_pin)
    
    if not game_state: 
        st.error("Game session ended.");
        st.stop()
    
    quiz_mode = game_state.get("quiz_mode")
    
    if quiz_mode == "participant_paced_with_timer":
        st_autorefresh(interval=500, key="player_timer_refresher")

    players_data = game_state.get("players", {})
    player_data = players_data.get(player_name, {})
    current_score = player_data.get('score', 0) if isinstance(player_data, dict) else player_data
    
    st.sidebar.info(f"Playing as: **{player_name}** | Score: **{current_score}**")
    show_leaderboard(players_data)
    
    player_last_answered_q = player_data.get('last_answered_q', -1)
    current_q_index = player_last_answered_q + 1
    total_questions = len(game_state["questions"])
    
    with st.container(border=True):
        if game_state["status"] == "waiting":
            st.info("⏳ Waiting for the host to start the game...")
        
        elif game_state["status"] == "in_progress":
            if quiz_mode == "instructor_paced":
                current_q_index_host = game_state.get("current_question_index", -1)
                if current_q_index_host > -1:
                    if f"answered_{current_q_index_host}" not in st.session_state:
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
                                        game_ref = st.session_state.db.collection("games").document(game_pin)
                                        game_ref.update({f"players.{player_name}.score": firestore.Increment(1)})
                                    else:
                                        st.error("Incorrect!")
                                    st.rerun()
                    else:
                        st.info("You've answered this question. Waiting for the host to move on.")
                else:
                    st.info("⏳ Waiting for the host to start the game...")
        
            elif quiz_mode == "participant_paced_with_timer":
                if current_q_index < total_questions:
                    question = game_state["questions"][current_q_index]
                    
                    time_per_question = game_state.get("time_per_question", 60)
                    question_start_time = game_state.get("question_start_time")
                    
                    if question_start_time and game_state.get("status") == "in_progress":
                        elapsed_time = time.time() - question_start_time.timestamp()
                        time_left = time_per_question - elapsed_time
                    else:
                        time_left = time_per_question

                    if time_left < 0:
                        time_left = 0
                        
                    if time_left == 0 and player_last_answered_q < current_q_index:
                            st.error("Time's up!")
                            update_game_state(game_pin, {f"players.{player_name}.last_answered_q": current_q_index})
                            st.rerun()

                    timer_text = st.empty()
                    timer_text.markdown(f"**Time Remaining:** :alarm_clock: **{math.ceil(time_left)}** seconds")

                    st.subheader(f"Question {current_q_index + 1}/{total_questions}")
                    st.title(question["question"])
                    
                    has_answered = player_data.get('last_answered_q', -1) >= current_q_index
                    
                    if has_answered:
                        st.success("You've already answered this question!")
                    else:
                        answer_icons = ["🟥", "🔷", "🟡", "💚"]
                        cols = st.columns(2)
                        for i, option in enumerate(question["options"]):
                            with cols[i % 2]:
                                if st.button(f"{answer_icons[i]} {option}", use_container_width=True, key=f"paced_opt_{current_q_index}_{i}"):
                                    if option == question["answer"]:
                                        st.balloons()
                                        st.success("Correct!")
                                        game_ref = st.session_state.db.collection("games").document(game_pin)
                                        game_ref.update({
                                            f"players.{player_name}.score": firestore.Increment(1),
                                            f"players.{player_name}.last_answered_q": current_q_index
                                        })
                                    else:
                                        st.error("Incorrect!")
                                        game_ref = st.session_state.db.collection("games").document(game_pin)
                                        game_ref.update({f"players.{player_name}.last_answered_q": current_q_index})
                                    st.rerun()
                    st.markdown("---")
                    nav_cols = st.columns(2)
                    with nav_cols[0]:
                        if st.button("Previous Question", disabled=current_q_index == 0, use_container_width=True):
                            update_game_state(game_pin, {f"players.{player_name}.last_answered_q": player_last_answered_q - 1})
                            st.rerun()
                    with nav_cols[1]:
                        if st.button("Next Question", disabled=player_last_answered_q < current_q_index, use_container_width=True):
                            update_game_state(game_pin, {f"players.{player_name}.last_answered_q": player_last_answered_q + 1})
                            st.rerun()
                else:
                    st.header("🎉 Quiz Finished! 🎉")

            elif game_state["status"] == "finished":
                st.balloons()
                st.header("🎉 Quiz Finished! 🎉")
                st.subheader("Your Results")
                players_data = game_state.get('players', {})
                sorted_players = sorted(players_data.items(), key=lambda item: item[1].get('score', 0), reverse=True)
                player_rank = next((i for i, (name, _) in enumerate(sorted_players) if name == st.session_state.player_name), None)
                if player_rank is not None:
                    player_score_data = players_data.get(st.session_state.player_name, {})
                    st.metric(label="Your Final Score", value=player_score_data.get('score', 0))
                    st.metric(label="Your Rank", value=f"#{player_rank + 1} of {len(sorted_players)} players")
                st.markdown("---")
                st.subheader("Final Leaderboard")
                for i, (name, score_data) in enumerate(sorted_players):
                    medal = ""
                    if i == 0: medal = "🥇"
                    elif i == 1: medal = "🥈"
                    elif i == 2: medal = "🥉"
                    st.markdown(f"**{medal} {name}**: {score_data.get('score', 0)}")
    
    if 'game_pin' not in st.session_state:
        # Initial join form
        with st.container(border=True):
            st.header("👋 Join a Game")
            player_name = st.text_input("Your Name:", key="player_name_join")
            
            query_params = st.query_params
            pin_from_url = query_params.get("pin", [""])[0]
            game_pin_input = st.text_input("Game PIN:", value=pin_from_url, max_chars=4, key="game_pin_join")
            
            if st.button("Join Game", use_container_width=True, type="secondary", key="join_game_btn"):
                game_pin_input = game_pin_input.upper()
                success, message = join_game(game_pin_input, player_name)
                if success:
                    st.session_state.player_name = player_name
                    st.session_state.game_pin = game_pin_input
                    st.session_state.player_answers = {}
                    st.rerun()
                else:
                    st.error(message)
    else:
        player_game_screen()
