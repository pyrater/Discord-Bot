import os
from dotenv import load_dotenv

class Config:
    def __init__(self):
        # Load .env from the same directory as this file
        base_dir = os.path.dirname(os.path.abspath(__file__))
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
        self.DB_PATH = os.path.join(base_dir, "tars_state.db")
        self.CHROMA_PATH = os.path.join(base_dir, "chroma_db")
        self.LOG_FILE = os.path.join(base_dir, "bot.log")

        # Security
        self.DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD")

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
