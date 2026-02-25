import os
from dotenv import load_dotenv

class Config:
    def __init__(self):
        # bot_config.py is in src/, so go up one level to get root
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(base_dir, ".env"))
        
        # Core Settings
        self.DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
        self.LLM_TOKEN = os.getenv("LLM_TOKEN")
        self.LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.featherless.ai/v1")
        self.MODEL_NAME = os.getenv("MODEL_NAME", "google/gemma-3-27b-it")
        
        # Service URLs
        self.COMFY_URL = os.getenv("COMFY_URL")
        self.DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
        
        # Paths
        self.LOCAL_MODEL_PATH = os.getenv("LOCAL_MODEL_PATH", "/app/models/google_gemma-3-270m-it-Q8_0.gguf")
        self.BASE_DIR = base_dir
        # Store database and vector store under a dedicated `db/` directory
        self.DB_PATH = os.path.join(base_dir, "db", "tars_state.db")
        self.CHROMA_PATH = os.path.join(base_dir, "db", "chroma_db")
        self.PERSONA_PATH = os.path.join(base_dir, "chars", "TARS.json")
        self.TEMPLATES_DIR = os.path.join(base_dir, "templates")
        self.SD_API_TEMPLATE = os.path.join(self.TEMPLATES_DIR, "SD-API.json")
        self.SD_IMG2IMG_TEMPLATE = os.path.join(self.TEMPLATES_DIR, "SD-IMG2IMG.json")
        self.ART_FILENAME = "tars_art.png"
        # Log and other runtime artifacts go into `data/`
        self.DATA_DIR = os.path.join(base_dir, "data")
        os.makedirs(self.DATA_DIR, exist_ok=True)
        self.LOG_FILE = os.path.join(self.DATA_DIR, "bot.log")
        # Common runtime artifact paths
        self.TRANSCRIPT_FILE = os.path.join(self.DATA_DIR, "transcript.md")
        self.SPEAKER_REGISTRY = os.path.join(self.DATA_DIR, "speaker_registry.json")
        self.AUDIO_DEBUG_LOG = os.path.join(self.DATA_DIR, "audio_debug.log")
        self.STOP_FLAG = os.path.join(base_dir, "stop_bot.flag")
        
        # Token Limits
        # Use MAX_TOKENS (explicit) or TOKEN_LIMIT (legacy/user preference)
        env_token_limit = os.getenv("MAX_TOKENS") or os.getenv("TOKEN_LIMIT") or "4096"
        self.MAX_TOKENS = int(env_token_limit) # Context Window
        self.MAX_GENERATION = int(os.getenv("MAX_GENERATION", "4096")) # Output Limit

        # Security
        self.DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")
        self.ADMIN_USER = os.getenv("ADMIN_USER")

    def validate(self):
        """Checks for critical missing keys."""
        if not self.DISCORD_TOKEN:
            print("❌ Critical Error: DISCORD_TOKEN not found in .env")
            return False
            
        if not self.DASHBOARD_PASSWORD:
            import secrets
            generated_pw = secrets.token_urlsafe(16)
            print(f"⚠️ DASHBOARD_PASSWORD not set in .env. Generated temporary password: {generated_pw}")
            self.DASHBOARD_PASSWORD = generated_pw
            
        return True

settings = Config()
