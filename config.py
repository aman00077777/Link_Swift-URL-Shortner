import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "default-fallback-key-987654321")
    BASE_URL = os.getenv("BASE_URL", "http://localhost:5000").rstrip("/")
    DATABASE_URL = os.getenv("DATABASE_URL", None)
    DATABASE_FILE = os.getenv("DATABASE_FILE", "urls.db")