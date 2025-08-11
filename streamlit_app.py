import streamlit as st
import time
import random
import string
import io
import qrcode
from PIL import Image
from google.cloud import firestore
import math

# --- App Branding and Configuration ---
APP_NAME = "Quizzicle"
# Make sure "Loading image.jpeg" is in the same directory as this script.
LOGO_URL = "Loading image.jpeg"
PLAYER_MODE_URL = "https://blank-app-s5sx65i2mng.streamlit.app/" # REMINDER: Change this to your deployed app's URL

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

def show_game_logo():
    """Displays the Quizzicle logo."""
    col_logo, col_title = st.columns([1, 4])
    with col_logo:
        # Corrected parameter name from 'use_column_width' to 'use_container_width'
        st.image(LOGO_URL, width=100, use_container_width=True) 
    with col_title:
        st.title(APP_NAME)
    st.markdown("---")


# --- Main App Logic ---
show_game_logo()

if 'role' not in st.session_state:
    st.session_state.role = None
    st.session_state.show_host_password_prompt = False
    
# Initialize a session state variable for validation errors
if 'create_game_error' not in st.session_state:
    st.session_state.create_game_error = None

# Host's view of the next question button is now a callback function
def next_question_callback():
    game_state = get_game_state(st.session_state.game_pin)
    current_q_index = game_state.get("current_question_index", -1)
    if current_q_index + 1 < len(game_state["questions"]):
        update_game_state(st.session_state.game_pin, {
            "current_question_index": current_q_index + 1
        })
        # Reset the show_answer state for the next question
        st.session_state[f"show_answer_{current_q_index+1}"] = False
    else:
        update_game_state(st.session_state.game_pin, {"status": "finished"})

if st.session_state.role is None:
    # --- Role Selection ---
    if st.session_state.show_host_password_prompt:
        with st.container(border=True):
            st.header("🔑 Host Login")
            password = st.text_input("Enter Host Password:", type="password")
            if st.button("Login", use_container_width=True):
                if "HOST_PASSWORD" in st.secrets and password == st.secrets["HOST_PASSWORD"]:
                    st.session_state.role = "host"
                    st.session_state.show_host_password_prompt = False
                    st.rerun()
                else:
                    st.error("Incorrect password.")
            if st.button("Back", use_container_width=True):
                st.session_state.show_host_password_prompt = False
                st.rerun()
    else:
        with st.container(border=True):
            st.header("👋 Welcome! Are you a Host or a Player?")
            col1, col2 = st.columns(2)
            with col1:
                if st.button("👩‍🏫 I am the Host", use_container_width=True):
                    st.session_state.role = "host"
                    st.rerun()
            with col2:
                if st.button("🧑‍🎓 I am a Player", use_container_width=True, type="secondary"):
                    st.session_state.role = "player"
                    st.rerun()


# --- HOST VIEW ---
elif st.session_state.role == "host":
    if 'game_pin' not in st.session_state:
        # Host creates a new game
        with st.container(border=True):
            st.header("✨ Create a New Game")
            
            host_name = st.text_input("Enter your name as Host:")
            uploaded_file = st.file_uploader("Upload Quiz TXT file", type="txt")
            
            # New quiz mode options
            st.subheader("Quiz Settings")
            quiz_mode = st.radio(
                "Select Quiz Mode:", 
                ("Instructor-Paced", "Participant-Paced with Timer"),
                horizontal=True
            )
            time_per_question = None
            if quiz_mode == "Participant-Paced with Timer":
                time_per_question = st.number_input(
                    "Time per question (in seconds):",
                    min_value=10,
                    max_value=300,
                    value=60,
                    step=10
                )
            
            with st.expander("Click to see TXT format example"):
                st.code("""
Q: What is 2+2?
O: 3
O: 4
O: 5
A: 4
                """, language="text")
            
            # Display persistent error message if it exists
            if st.session_state.create_game_error:
                st.error(st.session_state.create_game_error)

            if st.button("Create New Game", use_container_width=True):
                st.session_state.create_game_error = None
                
                if not host_name:
                    st.session_state.create_game_error = "Please enter your name as the host."
                elif not uploaded_file:
                    st.session_state.create_game_error = "Please upload a quiz file."
                else:
                    try:
                        stringio = io.StringIO(uploaded_file.getvalue().decode("utf-8"))
                        text_contents = stringio.read()
                        quiz_data = parse_text_quiz(text_contents)
                        
                        if quiz_data:
                            st.session_state.game_pin = create_game_session(
                                host_name, quiz_data, 
                                quiz_mode.replace("-", "_").lower(), 
                                time_per_question
                            )
                        else:
                            st.session_state.create_game_error = "Invalid TXT format or empty file."
                            
                    except Exception as e:
                        st.session_state.create_game_error = f"An unexpected error occurred: {e}"

                st.rerun()

    else:
        game_pin = st.session_state.game_pin
        game_state = get_game_state(game_pin)
        
        if not game_state: st.error("Game not found. You may have to create a new game."); st.stop()
        
        # --- Host Layout: QR on the left, dashboard on the right ---
        col_qr, col_dashboard = st.columns([1, 2])
        
        with col_qr:
            st.header("🎮 Host Dashboard")
            st.markdown(f"<div class='game-pin-display'>{game_pin}</div>", unsafe_allow_html=True)
            
            # QR Code and Link Sharing
            st.markdown("---")
            st.subheader("📲 Share Game Link & QR Code")
            qr_text = f"{PLAYER_MODE_URL}?pin={game_pin}"
            qr_img = qrcode.make(qr_text)
            buf = io.BytesIO()
            qr_img.save(buf, format="PNG")
            st.image(buf, caption="Scan to join the game", use_container_width=True)
            st.markdown(f"**Direct Link:** `{PLAYER_MODE_URL}?pin={game_pin}`")

        with col_dashboard:
            with st.container(border=True):
                st.subheader("🏆 Live Leaderboard")
                show_leaderboard(game_state.get("players", {}))

            current_q_index = game_state.get("current_question_index", -1)
            quiz_mode = game_state.get("quiz_mode")
            
            with st.container(border=True):
                if game_state["status"] == "waiting":
                    st.subheader("Waiting for players to join...")
                    st.info(f"Current Players: {len(game_state.get('players', {}))}")
                    if st.button("Start Game", disabled=not game_state.get("players"), use_container_width=True):
                        update_game_state(game_pin, {
                            "status": "in_progress", 
                            "current_question_index": 0,
                            "question_start_time": firestore.SERVER_TIMESTAMP
                        })
                
                elif game_state["status"] == "in_progress":
                    if quiz_mode == "instructor_paced":
                        # Ensure show_answer state is reset when moving to a new question
                        if f"show_answer_{current_q_index}" not in st.session_state:
                            st.session_state[f"show_answer_{current_q_index}"] = False

                        st.subheader(f"Question {current_q_index + 1}/{len(game_state['questions'])}")
                        question = game_state["questions"][current_q_index]
                        st.title(question["question"])
                        
                        st.markdown("---")
                        
                        # Display options for the host
                        st.write("Options:")
                        answer_icons = ["🟥", "🔷", "🟡", "💚"]
                        for i, option in enumerate(question["options"]):
                            st.markdown(f"{answer_icons[i]} {option}")
                        
                        st.markdown("---")

                        # Toggle answer visibility with a button
                        show_answer_key = f"show_answer_{current_q_index}"
                        st.session_state[show_answer_key] = st.toggle("Show Answer", value=st.session_state[show_answer_key], key=show_answer_key)
                        
                        if st.session_state.get(show_answer_key):
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
            

# --- PLAYER VIEW ---
elif st.session_state.role == "player":
    # Refactor the main player logic into a function to avoid duplication
    def player_game_screen():
        game_pin = st.session_state.game_pin
        player_name = st.session_state.player_name
        game_state = get_game_state(game_pin)
        
        if not game_state: st.error("Game session ended."); st.stop()

        # Determine player's current score
        players_data = game_state.get("players", {})
        player_data = players_data.get(player_name, {})
        current_score = player_data.get('score', 0) if isinstance(player_data, dict) else player_data
        
        st.sidebar.info(f"Playing as: **{player_name}** | Score: **{current_score}**")
        show_leaderboard(players_data)
        
        current_q_index = game_state.get("current_question_index", -1)
        quiz_mode = game_state.get("quiz_mode")
        
        with st.container(border=True): # Consolidate player screen into one main container
            if game_state["status"] == "waiting":
                st.info("⏳ Waiting for the host to start the game...")
                # Add a button for the player to refresh their state manually, in case auto-refresh is slow
                if st.button("Check for Game Start"):
                    st.rerun()
            
            elif game_state["status"] == "in_progress":
                if quiz_mode == "instructor_paced":
                    if current_q_index > -1:
                        # Player has not answered for this question yet
                        if f"answered_{current_q_index}" not in st.session_state:
                            question = game_state["questions"][current_q_index]
                            st.subheader(f"Question {current_q_index + 1}")
                            st.title(question["question"])
                            
                            answer_icons = ["🟥", "🔷", "🟡", "💚"]
                            cols = st.columns(2)
                            for i, option in enumerate(question["options"]):
                                with cols[i % 2]:
                                    if st.button(f"{answer_icons[i]} {option}", use_container_width=True, key=f"opt_{i}"):
                                        st.session_state[f"answered_{current_q_index}"] = True
                                        if option == question["answer"]:
                                            st.balloons()
                                            st.success("Correct!")
                                            player_score_field = f"players.{player_name}.score"
                                            game_ref = st.session_state.db.collection("games").document(game_pin)
                                            game_ref.update({player_score_field: firestore.Increment(1)})
                                        else:
                                            st.error("Incorrect!")
                                        # Use st.rerun() here to immediately show the "answered" message
                                        st.rerun()
                        # Player has answered for this question
                        else:
                            st.info("You've answered this question. Waiting for the host to move on.")
                    # Waiting for first question to start
                    else:
                        st.info("⏳ Waiting for the host to start the game...")
            
                elif quiz_mode == "participant_paced_with_timer":
                    total_questions = len(game_state["questions"])
                    
                    # Player's state for this mode
                    if "current_player_q_index" not in st.session_state:
                        st.session_state.current_player_q_index = 0
                    
                    player_q_index = st.session_state.current_player_q_index
                    
                    if player_q_index < total_questions:
                        question = game_state["questions"][player_q_index]
                        
                        # Timer logic
                        time_per_question = game_state.get("time_per_question", 60)
                        now = firestore.SERVER_TIMESTAMP
                        time_left = time_per_question
                        
                        if "question_start_time" in st.session_state:
                            # Cannot get server time from client, so we assume a start time
                            # a more robust implementation would use a server function
                            elapsed_time = time.time() - st.session_state.question_start_time
                            time_left = time_per_question - elapsed_time
                        else:
                            st.session_state.question_start_time = time.time()

                        # Display the question and timer
                        timer_text = st.empty()
                        timer_text.markdown(f"**Time Remaining:** :alarm_clock: **{math.ceil(time_left)}** seconds")

                        st.subheader(f"Question {player_q_index + 1}/{total_questions}")
                        st.title(question["question"])
                        
                        # Check if player has already answered this question or time is up
                        has_answered = f"answered_paced_{player_q_index}" in st.session_state.player_answers
                        is_time_up = time_left <= 0
                        
                        if has_answered or is_time_up:
                            if has_answered:
                                st.success("You've already answered this question!")
                            else:
                                st.error("Time's up!")
                            st.info(f"The correct answer was: **{question['answer']}**")
                        else:
                            # Display answer options
                            answer_icons = ["🟥", "🔷", "🟡", "💚"]
                            cols = st.columns(2)
                            for i, option in enumerate(question["options"]):
                                with cols[i % 2]:
                                    if st.button(f"{answer_icons[i]} {option}", use_container_width=True, key=f"paced_opt_{player_q_index}_{i}"):
                                        st.session_state.player_answers[f"answered_paced_{player_q_index}"] = True
                                        if option == question["answer"]:
                                            st.balloons()
                                            st.success("Correct!")
                                            game_ref = st.session_state.db.collection("games").document(game_pin)
                                            # Update the player's score within the nested map
                                            player_score_field = f"players.{player_name}.score"
                                            game_ref.update({player_score_field: firestore.Increment(1)})
                                        else:
                                            st.error("Incorrect!")
                                        st.rerun()

                        # Navigation buttons
                        st.markdown("---")
                        nav_cols = st.columns(2)
                        with nav_cols[0]:
                            if st.button("Previous Question", disabled=player_q_index == 0, use_container_width=True):
                                st.session_state.current_player_q_index -= 1
                                del st.session_state.question_start_time # Reset timer
                                st.rerun()
                        with nav_cols[1]:
                            if st.button("Next Question", disabled=player_q_index >= total_questions - 1, use_container_width=True):
                                st.session_state.current_player_q_index += 1
                                del st.session_state.question_start_time # Reset timer
                                st.rerun()
                    else:
                        st.header("🎉 Quiz Finished! 🎉")

            elif game_state["status"] == "finished":
                st.balloons()
                st.header("🎉 Quiz Finished! 🎉")

    # --- Player Logic ---
    if 'game_pin' not in st.session_state:
        with st.container(border=True):
            st.header("👋 Join a Game")
            player_name = st.text_input("Your Name:")
            
            # Check for PIN in URL for direct link access
            query_params = st.query_params
            pin_from_url = query_params.get("pin", [""])[0]
            game_pin_input = st.text_input("Game PIN:", value=pin_from_url, max_chars=4)
            
            if st.button("Join Game", use_container_width=True, type="secondary") and player_name and game_pin_input:
                game_pin_input = game_pin_input.upper()
                success, message = join_game(game_pin_input, player_name)
                if success:
                    st.session_state.player_name = player_name
                    st.session_state.game_pin = game_pin_input
                    st.session_state.player_answers = {} # Tracks answers for participant-paced mode
                    st.rerun()
                else:
                    st.error(message)
    else:
        player_game_screen()
