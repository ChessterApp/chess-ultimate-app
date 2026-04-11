"""
Chess Ultimate App - Flask Backend (Phase 1)

ARCHITECTURE CHANGES:
- Removed Stockfish engine integration (now handled by frontend WASM)
- Removed python-chess dependencies (game logic in frontend)
- Removed SocketIO/UCI routes for engine communication
- Removed RAG pipeline routes (deferred to Phase 2)
- Removed voice API routes (deferred to future phase)

PHASE 1 FOCUS:
- LLM orchestration (Anthropic Claude, OpenAI GPT-4o)
- Clerk JWT authentication verification
- Supabase database integration (learning platform)
- API endpoints for:
  * Learning courses and lessons
  * User progress tracking
  * AI chat assistant with conversation history
  * Cached LLM responses (24hr TTL)

PHASE 2 (Planned):
- Weaviate vector database (6M+ games semantic search)
- Redis caching and session management
- RAG pipeline for game database queries

See: /IMPLEMENTATION_GUIDE.md for complete setup instructions
"""

import sys
import os
import json
import logging
import time
import uuid
import threading
import traceback
from datetime import datetime
import re
import atexit
import signal
from typing import Dict, List, Optional, Union, Any, Tuple

# --- Start sys.path modification ---
# When running from backend directory: python app.py
# backend_dir is /home/marblemaster/Desktop/Cursor/mvp1/backend (dynamic)
backend_dir = os.path.dirname(os.path.abspath(__file__))
# mvp1_dir is /home/marblemaster/Desktop/Cursor/mvp1 (parent directory)
mvp1_dir = os.path.dirname(backend_dir)

# Add both backend_dir and mvp1_dir to sys.path for proper imports
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)  # Add backend dir first for local imports
if mvp1_dir not in sys.path:
    sys.path.insert(1, mvp1_dir)     # Add mvp1 dir for any backend.* imports
# --- End sys.path modification ---

print(f"Current Working Directory: {os.getcwd()}")
print(f"Backend Directory: {backend_dir}")
print(f"MVP1 Directory: {mvp1_dir}")
print(f"Modified sys.path: {sys.path[:3]}...")  # Show first 3 paths

from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
import openai

# Phase 2 imports (commented out for Phase 1)
# from etl import config as etl_config
# from etl.agents.orchestrator import run_pipeline
# from etl.agents.answer_agent import AnswerAgent
# from etl.agents import router_agent_instance, retriever_agent_instance
# from etl.config import WEAVIATE_URL, WEAVIATE_OPENING_CLASS_NAME, WEAVIATE_GAMES_CLASS_NAME
# from etl.agents import opening_agent

# Phase 1: API blueprints (to be updated for Supabase)
# from api.register import register_blueprints  # Will be refactored for Phase 1

load_dotenv(dotenv_path=os.path.join(backend_dir, '.env')) # Load .env from backend directory

# Setup basic logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(module)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger(__name__) # Get logger for app.py

logger.info("Flask backend starting - Stockfish analysis handled by frontend WASM")

app = Flask(__name__)

# +++ Basic Logging Configuration +++
# This will help capture logs from other modules like RouterAgent if they use logging.getLogger()
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s %(name)s %(module)s: %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
# You might want to direct Flask's default logger to use this too, or customize further.
# For now, this sets up basicConfig which other modules using logging.getLogger() will pick up.

# Configure CORS with environment-based origins
flask_env = os.getenv('FLASK_ENV', 'production')
cors_origins_str = os.getenv('CORS_ALLOWED_ORIGINS', 'https://chesster.io,https://www.chesster.io')
cors_origins = [origin.strip() for origin in cors_origins_str.split(',')]

# Allow localhost in development only
if flask_env == 'development':
    if 'http://localhost:3000' not in cors_origins:
        cors_origins.append('http://localhost:3000')
    logger.info(f"CORS enabled for development origins: {cors_origins}")
else:
    logger.info(f"CORS enabled for production origins: {cors_origins}")

CORS(app, origins=cors_origins, supports_credentials=True)

# Setup performance monitoring middleware
try:
    from services.supabase_client import supabase
    from middleware.performance_monitor import setup_performance_monitoring, get_monitor

    performance_monitor = setup_performance_monitoring(app, supabase)
    logger.info("✅ Performance monitoring enabled with database logging")
except Exception as e:
    logger.warning(f"⚠️  Performance monitoring setup failed: {e}")
    performance_monitor = None

# Phase 1: Register API blueprints
try:
    from api.lessons import lessons_bp
    app.register_blueprint(lessons_bp)
    logger.info("✅ Lessons API registered")
except ImportError as e:
    logger.warning(f"⚠️  Could not import lessons API: {e}")

try:
    from api.chat import chat_bp
    app.register_blueprint(chat_bp)
    logger.info("✅ Chat API registered (server-managed LLM)")
except ImportError as e:
    logger.warning(f"⚠️  Could not import chat API: {e}")

try:
    from api.puzzles import puzzles_bp
    app.register_blueprint(puzzles_bp)
    logger.info("✅ Puzzles API registered (multi-puzzle lessons)")
except ImportError as e:
    logger.warning(f"⚠️  Could not import puzzles API: {e}")

try:
    from api.opponent_analysis import opponent_bp
    app.register_blueprint(opponent_bp)
    logger.info("✅ Opponent Analysis API registered (TWIC database search)")
except ImportError as e:
    logger.warning(f"⚠️  Could not import opponent analysis API: {e}")

try:
    from api.photo_to_fen import photo_fen_bp
    app.register_blueprint(photo_fen_bp)
    logger.info("✅ Photo-to-FEN API registered (image to FEN conversion)")
except ImportError as e:
    logger.warning(f"⚠️  Could not import photo-to-FEN API: {e}")

try:
    from api.scoresheet_to_pgn import scoresheet_bp
    app.register_blueprint(scoresheet_bp)
    logger.info("✅ Scoresheet Scanner API registered (scoresheet to PGN conversion)")
except ImportError as e:
    logger.warning(f"⚠️  Could not import scoresheet scanner API: {e}")

try:
    from api.openings import openings_bp
    app.register_blueprint(openings_bp)
    logger.info("✅ Openings API registered (repertoire management)")
except ImportError as e:
    logger.warning(f"⚠️  Could not import openings API: {e}")

try:
    from api.user_games import user_games_bp
    app.register_blueprint(user_games_bp)
    logger.info("✅ User Games API registered (My Games CRUD)")
except ImportError as e:
    logger.warning(f"⚠️  Could not import user games API: {e}")

try:
    from api.repertoire import repertoire_bp
    app.register_blueprint(repertoire_bp)
    logger.info("✅ Repertoire API registered (opening collection management)")
except ImportError as e:
    logger.warning(f"⚠️  Could not import repertoire API: {e}")

# Phase 2: SocketIO and RAG pipeline (commented out for Phase 1)
# socketio = SocketIO(app, cors_allowed_origins="*")
# user_sessions = {}
# session_lock = threading.Lock()

# --- LLM Client Setup (OpenRouter preferred, fallback to Anthropic/OpenAI/Deepseek) ---
# Check OpenRouter first (supports Gemini and other models), then ANTHROPIC_API_KEY
openrouter_key = os.getenv("OPENROUTER_API_KEY")
api_key = os.getenv("ANTHROPIC_API_KEY")
base_url = None
model_name = os.getenv("PRIMARY_MODEL", "google/gemini-3-flash-preview")  # Read from env or default to Gemini
llm_provider = "openrouter" if openrouter_key else "anthropic"

if openrouter_key:
    api_key = openrouter_key  # Use OpenRouter key
    print(f"INFO: Found OPENROUTER_API_KEY, using model {model_name}.")
elif api_key:
    # Fallback to direct Anthropic
    model_name = os.getenv("FALLBACK_MODEL", "claude-3-5-sonnet-20241022")
    llm_provider = "anthropic"
    print(f"INFO: Found ANTHROPIC_API_KEY, attempting to use with Anthropic endpoint and model {model_name}.")
    # base_url remains None (default Anthropic), model_name is already set
else:
    print("WARNING: ANTHROPIC_API_KEY environment variable not found.")
    # Fallback to OPENAI_API_KEY
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        print("INFO: Found OPENAI_API_KEY, attempting to use with default OpenAI endpoint and model gpt-4o.")
        model_name = "gpt-4o"
        llm_provider = "openai"
    else:
        print("WARNING: OPENAI_API_KEY environment variable not found.")
        # Fallback to DEEPSEEK_API_KEY
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if api_key:
            print("INFO: Found DEEPSEEK_API_KEY, attempting to use with Deepseek endpoint.")
            base_url = "https://api.deepseek.com/v1" # Set Deepseek URL
            model_name = "deepseek-chat" # Set Deepseek model
            llm_provider = "deepseek"
        else:
            print("WARNING: Neither ANTHROPIC_API_KEY, OPENAI_API_KEY nor DEEPSEEK_API_KEY found.")
            print("Chat functionality will be disabled.")
            llm_client = None # Explicitly set to None here if no key found

# Import appropriate LLM wrapper based on provider
if api_key and 'llm_client' not in locals(): # Check if llm_client wasn't set to None already
    try:
        if llm_provider == "openrouter":
            from llm.openrouter_llm import OpenRouterLLM  # Local import
            llm_client = OpenRouterLLM(
                api_key=api_key,
                model_name=model_name,
                max_tokens=2000,
                temperature=0.7
            )
        elif llm_provider == "anthropic":
            from llm.anthropic_llm import AnthropicLLM  # Local import
            llm_client = AnthropicLLM(
                api_key=api_key,
                model_name=model_name,
                max_tokens=2000,
                temperature=0.7
            )
        else:
            # Use OpenAILLM wrapper for OpenAI and Deepseek
            from llm.openai_llm import OpenAILLM  # Local import
            llm_client = OpenAILLM(
                api_key=api_key,
                model_name=model_name,
                max_tokens=2000,
                temperature=0.7,
                base_url=base_url  # Pass base_url for Deepseek support
            )
        print(f"LLM client initialized successfully for provider: {llm_provider}, model: {model_name}")
    except Exception as e:
        print(f"Error initializing LLM client: {e}")
        llm_client = None
elif not api_key: # Ensure client is None if no key was ever found
     llm_client = None

# Instantiate AnswerAgent after llm_client is potentially initialized
# Use the proper answer agent instance from etl.agents that has conversation memory support
try:
    from etl.agents import answer_agent_instance  # Local import
    print("Using enhanced AnswerAgent with conversation memory from etl.agents")
    print(f"Answer agent LLM client status: {answer_agent_instance.llm_client is not None if answer_agent_instance else 'Agent is None'}")
except ImportError as e:
    print(f"Warning: Could not import enhanced AnswerAgent: {e}")
    # Fallback to creating a basic one
    answer_agent_instance = None # Default to None
    if llm_client:
        try:
            answer_agent_instance = AnswerAgent(llm_client=llm_client)
            print("AnswerAgent initialized successfully (fallback).")
        except Exception as e:
            print(f"Error initializing AnswerAgent: {e}")
            # answer_agent_instance remains None
    else:
        print("LLM client not available, AnswerAgent not initialized.")

# Initialize conversation memory system
conversation_memory_manager = None
conversation_summarizer = None

try:
    # Import conversation memory components
    from etl.agents.conversation_memory import initialize_conversation_memory  # Local import
    from etl.agents.conversation_summarizer import initialize_conversation_summarizer  # Local import
    
    # Initialize Redis client for conversation memory
    import redis
    redis_host = os.getenv("REDIS_HOST", "localhost")
    redis_port = int(os.getenv("REDIS_PORT", "6379"))
    redis_db = int(os.getenv("REDIS_DB", "0"))
    
    try:
        redis_client = redis.Redis(host=redis_host, port=redis_port, db=redis_db, decode_responses=True)
        # Test Redis connection
        redis_client.ping()
        print(f"Redis connection established at {redis_host}:{redis_port}")
        
        # Initialize conversation memory with SQLite database (file-based for simplicity)
        database_url = os.getenv("CONVERSATION_DB_URL", "sqlite:///conversation_memory.db")
        conversation_memory_manager = initialize_conversation_memory(redis_client, database_url)
        print("Conversation memory manager initialized successfully")
        
        # Update the answer agent with the conversation memory manager
        if answer_agent_instance and conversation_memory_manager:
            answer_agent_instance.conversation_memory_manager = conversation_memory_manager
            print("✅ Answer agent updated with conversation memory manager")
        
        # Initialize conversation summarizer if OpenAI key is available
        if api_key and base_url is None:  # Only for OpenAI API, not Deepseek
            conversation_summarizer = initialize_conversation_summarizer(api_key)
            print("Conversation summarizer initialized successfully")
        
    except redis.ConnectionError as e:
        print(f"Warning: Could not connect to Redis at {redis_host}:{redis_port}: {e}")
        print("Conversation memory will not be available. Consider starting Redis server.")
    except Exception as e:
        print(f"Warning: Failed to initialize Redis client: {e}")
        
except ImportError as e:
    print(f"Warning: Conversation memory system not available: {e}")
    print("Chat will work without conversation memory.")
except Exception as e:
    print(f"Warning: Failed to initialize conversation memory system: {e}")
    print("Chat will work without conversation memory.")

# In-memory store for active games (Session ID -> {'board': chess.Board})
active_games = {} # REINSTATE THIS

# --- Constants ---
# IMPORTANT: Adjust this path based on the actual location and execution method
# Point to the new CLI script
BOARD_TO_FEN_SCRIPT = "/home/marblemaster/Desktop/Cursor/board-to-fen/board_to_fen_cli.py" 
# Use the python executable from the board-to-fen tool's venv
BOARD_TO_FEN_PYTHON_EXECUTABLE = "/home/marblemaster/Desktop/Cursor/board-to-fen/.venv/bin/python"
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}

SYSTEM_MESSAGE_CHAT_INTERACTIVE = (
    f"You are an AI Chess Tutor. Your primary goal is to help users understand chess concepts, positions, and game play. "
    f"You have access to a function 'get_stockfish_analysis(fen_string)' to get Stockfish engine analysis for a given FEN position."
    f"You also have access to a function 'check_move_legality(fen_string, move_san)' which returns if a move is legal."
    f"When a user asks for the best move, or for analysis that would benefit from engine calculation, you MUST use 'get_stockfish_analysis' for the relevant FEN and incorporate its findings."
    f"If the user provides a FEN or describes a position, use that FEN for analysis. If the context implies a current board state, use that."
    f"When discussing specific moves:"
    f"1.  **Move Legality is Paramount:** Always verify move legality using 'check_move_legality' before suggesting moves. Never suggest illegal moves.\\n" +
    f"2.  **Clarity:** Explain your reasoning clearly and concisely, especially when it's based on Stockfish analysis (e.g., 'Stockfish suggests ... because ... and evaluates the position as ...').\\n" +
    f"3.  **Interactive Assistance:** If the user makes a move, acknowledge it. If they ask for hints or ideas, provide them based on sound chess principles and engine analysis if appropriate.\\n" +
    f"4.  **Board State:** If you refer to a specific position that should be shown on a visual board, end your response with [SET_FEN: <fen_string>]. Use the FEN relevant to your explanation.\\n" +
    f"5.  **Opening Recognition:** If the current FEN or sequence of moves corresponds to a known chess opening, identify it (e.g., 'This position is reached after the main line of the Ruy Lopez'). You may have access to opening data.\\n"
    f"User messages may include their current FEN state as `Current FEN: <fen_string>` or their last move as `User's last move: <move_san>`.\\n" + # Note: these backticks are for Markdown, not function calls
    f"If asked about an opening from a FEN, try to identify it. If provided with opening moves, identify the opening.\\n"
)

@app.route('/')
def index():
    return "Chess Companion Backend is running!"

# API endpoints have been moved to specific blueprint modules
# See backend/api/ directory for all API routes

# --- Legacy Chat Endpoint (Moved to blueprint) --- 
@app.route('/api/chat', methods=['POST'])
def legacy_chat_endpoint():
    if not llm_client:
        return jsonify({"error": "LLM client not configured. Please set API key."}), 503

    data = request.get_json()
    messages = data.get('messages')
    session_id = data.get('session_id')
    received_fen = data.get('fen')

    # --- Validate Session ID and FEN ---
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    if not received_fen:
        return jsonify({"error": "fen is required"}), 400

    user_input = messages[-1]['content'] if messages else ""

    print(f"\n--- Enhanced Chat Request with Conversation Memory ---")
    print(f"Session ID: {session_id}")
    print(f"Received FEN: {received_fen}")
    print(f"User Input: {user_input}")

    # --- Retrieve/Initialize/Synchronize Game State from Memory ---
    if session_id not in active_games:
        print(f"Initializing new game state for session {session_id} with FEN: {received_fen}")
        try:
            initial_board = chess.Board(received_fen)
            active_games[session_id] = {'board': initial_board}
        except ValueError:
            print(f"ERROR: Invalid initial FEN received from frontend: {received_fen}")
            return jsonify({"error": f"Invalid initial FEN provided: {received_fen}"}), 400
    
    session_state = active_games[session_id]
    board = session_state['board']

    # Synchronize backend board with frontend FEN if they differ
    if received_fen != board.fen():
        print(f"FEN mismatch! Frontend FEN: {received_fen}, Backend FEN: {board.fen()}. Updating backend state.")
        try:
            board = chess.Board(received_fen)
            active_games[session_id]['board'] = board
        except ValueError:
            print(f"ERROR: Invalid FEN received from frontend during sync: {received_fen}")
            return jsonify({"error": f"Invalid FEN received: {received_fen}"}), 400

    print(f"Current synchronized FEN for session {session_id}: {board.fen()}")

    # === Use Enhanced Answer Agent with Conversation Memory ===
    if not answer_agent_instance:
        print("ERROR: AnswerAgent not available")
        return jsonify({"error": "Chat AI not initialized. Please check server configuration."}), 503

    try:
        # Use the enhanced answer agent that includes conversation memory
        enhanced_response = answer_agent_instance.generate_answer(
            query=user_input,
            retrieved_documents=None,  # Let the agent handle retrieval if needed
            query_type="chat",
            current_fen=board.fen(),
            session_id=session_id
        )
        
        answer = enhanced_response.get("answer", "Sorry, I couldn't generate a response.")
        
        # Generate PGN for response
        try:
            game_pgn = chess.pgn.Game()
            temp_board_pgn = board.copy()
            moves_to_add = []
            while temp_board_pgn.move_stack:
                moves_to_add.append(temp_board_pgn.pop())
            moves_to_add.reverse()
            node = game_pgn
            for move in moves_to_add:
                node = node.add_variation(move)
            pgn_exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
            final_pgn = game_pgn.accept(pgn_exporter)
        except Exception as pgn_error:
            print(f"Error generating PGN: {pgn_error}")
            final_pgn = "[PGN generation error]"

        # Get Stockfish analysis for response
        analysis_lines = analyze_fen_with_stockfish(fen_string=board.fen(), time_limit=None, depth_limit=24, multipv=3)
        if not analysis_lines:
            analysis_lines = []

        game_ended = board.is_game_over(claim_draw=board.can_claim_draw())
        outcome_obj = board.outcome(claim_draw=board.can_claim_draw()) if game_ended else None
        
        response_data = {
            "reply": answer,
            "fen": board.fen(),
            "pgn": final_pgn,
            "is_game_over": game_ended,
            "outcome": outcome_obj.result() if outcome_obj else None,
            "analysis_lines": analysis_lines,
            "conversation_memory_used": enhanced_response.get("conversation_history_used", False),
            "quality_metrics": enhanced_response.get("quality_metrics"),
            "query_id": enhanced_response.get("query_id"),
            "answer_id": enhanced_response.get("answer_id")
        }
        
        print(f"Enhanced chat response generated with conversation memory for session {session_id}")
        print(f"Conversation history used: {enhanced_response.get('conversation_history_used', False)}")
        
        return jsonify(response_data)
        
    except Exception as e:
        print(f"Error in enhanced chat processing: {e}")
        return jsonify({"error": f"An error occurred processing your message: {str(e)}"}), 500

# --- Helper Function ---
def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# +++ Update diagnostic print +++
print("DEBUG: Attempting to register /api/fen_upload_test route...") 

# --- New Route for Image Upload --- 
@app.route('/api/fen_upload_test', methods=['POST'])
def fen_from_image_endpoint():
    if 'image' not in request.files:
        return jsonify({"error": "No image file part in the request"}), 400
    
    file = request.files['image']

    if file.filename == '':
        return jsonify({"error": "No image file selected"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename) # Sanitize filename
        # Create a secure temporary file
        temp_file = None
        try:
            # Use NamedTemporaryFile to get a path easily, ensure it's deleted
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(filename)[1]) as temp_file_obj:
                file.save(temp_file_obj.name)
                temp_file_path = temp_file_obj.name
            
            print(f"Saved uploaded image temporarily to: {temp_file_path}")

            # --- Execute the board-to-fen script --- 
            command = [BOARD_TO_FEN_PYTHON_EXECUTABLE, BOARD_TO_FEN_SCRIPT, temp_file_path]
            print(f"Executing command: {' '.join(command)}")
            
            result = subprocess.run(command, capture_output=True, text=True, check=False) # Don't check=True yet

            print(f"board-to-fen stdout: {result.stdout}")
            print(f"board-to-fen stderr: {result.stderr}")

            if result.returncode != 0:
                error_msg = f"board-to-fen script failed: {result.stderr or 'Unknown error'}"
                print(f"ERROR: {error_msg}")
                return jsonify({"error": error_msg}), 500

            # --- Process and Validate Output --- 
            extracted_fen_fragment = result.stdout.strip() 
            if not extracted_fen_fragment:
                 return jsonify({"error": "board-to-fen script returned empty output."}), 500
            
            # --- Construct full FEN ---
            # Assume White to move, standard castling, no en passant, standard clocks
            full_fen = f"{extracted_fen_fragment} w KQkq - 0 1"
            print(f"Constructed full FEN: {full_fen}")

            # Validate the FULL FEN string using python-chess
            try:
                board_check = chess.Board(full_fen)
                print(f"Successfully validated full FEN: {full_fen}")
                # Send the full FEN back to the frontend
                return jsonify({"fen": full_fen}), 200 
            except ValueError:
                print(f"ERROR: Constructed FEN is invalid: {full_fen}")
                # Include the invalid FEN in the error for easier debugging
                return jsonify({"error": f"Failed to parse constructed FEN: {full_fen}"}), 500

        except Exception as e:
            print(f"Error processing image upload: {e}")
            return jsonify({"error": "Internal server error during image processing."}), 500
        finally:
            # --- Clean up the temporary file --- 
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    print(f"Removed temporary file: {temp_file_path}")
                except OSError as e:
                    print(f"Error removing temporary file {temp_file_path}: {e}")
    else:
        return jsonify({"error": "Invalid file type. Allowed types: png, jpg, jpeg"}), 400

# --- ETL Endpoints ---
# @app.route('/api/etl/process', methods=['POST'])  # Moved to blueprint
def legacy_process_document_endpoint():
    """Process a document through the ETL pipeline."""
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
        
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
        
    if not file.filename.lower().endswith(('.docx', '.pdf')):
        return jsonify({"error": "File must be DOCX or PDF"}), 400
    
    try:
        # Save the file to the input directory
        from etl import config as etl_config_local  # Local import, avoid re-using global etl_config name
        from etl.main import run_pipeline_for_file  # Local import
        
        # Ensure input directory exists
        os.makedirs(etl_config_local.INPUT_DIR, exist_ok=True)
        
        # Save the file
        file_path = os.path.join(etl_config_local.INPUT_DIR, file.filename)
        file.save(file_path)
        
        # Run the ETL pipeline
        success, message = run_pipeline_for_file(file_path)
        
        if success:
            return jsonify({
                "success": True,
                "message": message,
                "filename": file.filename
            }), 200
        else:
            return jsonify({
                "success": False,
                "error": message,
                "filename": file.filename
            }), 500
            
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "filename": file.filename
        }), 500

# @app.route('/api/etl/status', methods=['GET'])  # Moved to blueprint
def legacy_etl_status_endpoint():
    """Get the status of the ETL pipeline."""
    try:
        from etl import config as etl_config_local  # Local import
        
        # Check if input and output directories exist
        input_dir_exists = os.path.exists(etl_config_local.INPUT_DIR)
        output_dir_exists = os.path.exists(etl_config_local.OUTPUT_IMAGE_DIR)
        
        # Count files in each directory
        input_files = len(os.listdir(etl_config_local.INPUT_DIR)) if input_dir_exists else 0
        processed_files = len(os.listdir(etl_config_local.CHUNKS_JSON_DIR)) if os.path.exists(etl_config_local.CHUNKS_JSON_DIR) else 0
        
        # Check if FEN converter is enabled and available
        fen_enabled = etl_config_local.FEN_CONVERTER_ENABLED
        fen_available = os.path.exists(etl_config_local.BOARD_TO_FEN_TOOL_PATH)
        
        # Check if Weaviate is enabled and connected
        weaviate_enabled = etl_config_local.WEAVIATE_ENABLED
        weaviate_connected = False
        
        if weaviate_enabled:
            from etl.weaviate_loader import get_weaviate_client  # Local import
            client = get_weaviate_client()
            weaviate_connected = client is not None
        
        return jsonify({
            "status": "operational",
            "input_directory": {
                "exists": input_dir_exists,
                "path": etl_config_local.INPUT_DIR,
                "file_count": input_files
            },
            "processing": {
                "fen_converter_enabled": fen_enabled,
                "fen_converter_available": fen_available,
                "processed_files": processed_files
            },
            "weaviate": {
                "enabled": weaviate_enabled,
                "connected": weaviate_connected,
                "url": etl_config_local.WEAVIATE_URL
            }
        }), 200
    except Exception as e:
        return jsonify({
            "status": "error",
            "error": str(e)
        }), 500

# @app.route('/api/rag/query', methods=['POST'])  # Moved to blueprint
def legacy_rag_query_endpoint():
    """RAG query endpoint using the new orchestrator"""
    data = request.get_json()
    
    if not data or not data.get('query'):
        return jsonify({"error": "Query is required"}), 400
    
    query = data.get('query')
    session_id = data.get('session_id') 
    
    current_board_fen_for_rag = None
    current_pgn_for_rag = None # ADDED: To store PGN

    if session_id and session_id in active_games:
        with session_lock:
            if session_id in active_games and 'board' in active_games[session_id]:
                board = active_games[session_id]['board']
                current_board_fen_for_rag = board.fen()
                try:
                    # Generate PGN from the board state
                    game_for_pgn = chess.pgn.Game()
                    # Build PGN from move stack
                    # The board in active_games should have the full history
                    node = game_for_pgn
                    for move in board.move_stack:
                        node = node.add_main_variation(move) # Use add_main_variation for simplicity
                    
                    pgn_exporter = chess.pgn.StringExporter(headers=False, variations=False, comments=False)
                    current_pgn_for_rag = game_for_pgn.accept(pgn_exporter)
                    if not current_pgn_for_rag and board.move_stack: # Handle empty PGN if moves exist (should not happen)
                        current_pgn_for_rag = "[Could not generate PGN from move stack]"
                    elif not board.move_stack:
                        current_pgn_for_rag = "[No moves played yet]"

                    print(f"DEBUG: [rag_query_endpoint] Fetched FEN for session {session_id}: {current_board_fen_for_rag}")
                    print(f"DEBUG: [rag_query_endpoint] Generated PGN for session {session_id}: {current_pgn_for_rag}")
                except Exception as e:
                    print(f"ERROR: [rag_query_endpoint] Failed to generate PGN for session {session_id}: {e}")
                    current_pgn_for_rag = "[Error generating PGN]"
            else:
                print(f"DEBUG: [rag_query_endpoint] No board found for session {session_id} in active_games.")
    else:
        print(f"DEBUG: [rag_query_endpoint] No session_id provided or session_id {session_id} not in active_games.")

    if not answer_agent_instance:
        print("ERROR: /api/rag/query called but answer_agent_instance is not available globally.")
        return jsonify({"error": "RAG system not initialized. LLM client or AnswerAgent might be missing."}), 503
    
    if not run_pipeline: # Check if orchestrator imported successfully
        print("ERROR: /api/rag/query called but run_pipeline (orchestrator) is not available.")
        return jsonify({"error": "RAG system's orchestrator is not available."}), 503

    try:
        # Call the new orchestrator\'s run_pipeline function
        pipeline_state = run_pipeline(
            initial_query=query,
            router_agent_instance=router_agent_instance,
            retriever_agent_instance=retriever_agent_instance,
            answer_agent_instance=answer_agent_instance,
            current_board_fen=current_board_fen_for_rag,
            session_pgn=current_pgn_for_rag,
            session_id=session_id  # Pass session_id for conversation memory
        )
        
        # Determine the FEN for which to run analysis for the UI
        # Priority: FEN set by router, then current board FEN from pipeline, then initial FEN.
        final_fen_for_ui_analysis = pipeline_state.get("fen_for_analysis", 
                                      pipeline_state.get("current_board_fen", 
                                                         current_board_fen_for_rag))

        analysis_lines_for_ui = []
        if final_fen_for_ui_analysis:
            app.logger.info(f"Running Stockfish analysis for UI for FEN: {final_fen_for_ui_analysis}")
            analysis_lines_for_ui = analyze_fen_with_stockfish(
                fen_string=final_fen_for_ui_analysis, 
                time_limit=None,  # Quick analysis for UI update
                depth_limit=24,
                multipv=3
            )
            if analysis_lines_for_ui is None: # Ensure it's an empty list if analysis fails
                analysis_lines_for_ui = []
                app.logger.warning(f"Stockfish analysis for UI returned None for FEN: {final_fen_for_ui_analysis}")
        else:
            app.logger.warning("No FEN determined for UI Stockfish analysis in RAG query response.")

        # Construct response from the pipeline_state
        if pipeline_state.get("final_answer"):
            response_data = {
                "query": query,
                "answer": pipeline_state["final_answer"],
                "query_type": pipeline_state.get("query_type"),
                "metadata": pipeline_state.get("router_metadata"), 
                "retrieved_chunks_count": len(pipeline_state.get("retrieved_chunks", [])),
                "analysis_lines": analysis_lines_for_ui, # <<< ADDED ANALYSIS LINES
                "fen": final_fen_for_ui_analysis # <<< FEN for which analysis was run (or current FEN if none by router)
            }
            if pipeline_state.get("error_message"): 
                response_data["note"] = pipeline_state["error_message"]
            app.logger.info(f"RAG Query successful. Returning answer and {len(analysis_lines_for_ui)} analysis lines for FEN: {final_fen_for_ui_analysis}")
            return jsonify(response_data), 200
        elif pipeline_state.get("error_message"):
            app.logger.error(f"RAG pipeline error: {pipeline_state['error_message']}")
            # Even on error, provide any analysis that might have been generated if a FEN was available
            return jsonify({
                "error": pipeline_state["error_message"], 
                "query": query,
                "query_type": pipeline_state.get("query_type"),
                "analysis_lines": analysis_lines_for_ui, # Include analysis if available
                "fen": final_fen_for_ui_analysis    # Include FEN if available
            }), 500 
        else:
            app.logger.error("RAG pipeline did not produce an answer or an error.")
            # Fallback, include analysis if available
            return jsonify({
                "error": "RAG pipeline did not produce an answer or an error.", 
                "query": query,
                "analysis_lines": analysis_lines_for_ui, # Include analysis if available
                "fen": final_fen_for_ui_analysis    # Include FEN if available
            }), 500

    except Exception as e:
        app.logger.error(f"Error during RAG pipeline execution: {e}", exc_info=True)
        return jsonify({"error": f"An unexpected error occurred in the RAG pipeline: {str(e)}"}), 500

# @app.route('/api/set_fen', methods=['POST'])  # Moved to blueprint
def legacy_set_fen_endpoint():
    """
    Endpoint to set a FEN position in an active session.
    Used by the LangGraph agent to update the chessboard when a FEN is detected.
    """
    data = request.get_json()
    session_id = data.get('session_id')
    fen = data.get('fen')
    source = data.get('source', 'agent')  # Where the FEN came from (agent, rag, etc.)
    explanation = data.get('explanation', '')  # Optional explanation text

    # Validate the required parameters
    if not session_id:
        return jsonify({"error": "session_id is required"}), 400
    if not fen:
        return jsonify({"error": "fen is required"}), 400

    # Validate the FEN format
    try:
        board = chess.Board(fen)
        valid_fen = board.fen()  # Get the normalized FEN
    except ValueError as e:
        return jsonify({"error": f"Invalid FEN string: {str(e)}"}), 400
    
    # Store in active games or update existing session
    if session_id not in active_games:
        active_games[session_id] = {'board': board}
        app.logger.info(f"[update_backend_fen] Created new session {session_id} with FEN: {new_fen}")
    else:
        active_games[session_id]['board'] = board
        app.logger.info(f"[update_backend_fen] Updated board for session {session_id} with FEN: {new_fen}")
    
    # Emit a WebSocket event with the new FEN
    socketio.emit('fen_update', {
        'session_id': session_id,
        'fen': valid_fen,
        'source': source,
        'explanation': explanation
    })
    
    # Return success with normalized FEN and any relevant info
    return jsonify({
        "success": True,
        "fen": valid_fen,
        "source": source,
        "explanation": explanation
    }), 200

# ============================================
# Application Entry Point
# ============================================

if __name__ == '__main__':
    app.run(debug=False, port=5001, host='0.0.0.0', use_reloader=False, threaded=True)
