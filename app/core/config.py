import os
from dotenv import load_dotenv
load_dotenv()
class Settings:
    MONGO_URL: str = os.getenv("MONGO_URL")
    GEMINI_API: str = os.getenv("GEMINI_API_KEY")
    MONGO_URL: str = os.getenv("MONGO_URL")
    DB_NAME: str = 'sict_db'

settings = Settings()