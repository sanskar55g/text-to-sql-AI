import os
from dotenv import load_dotenv

# Load variables from .env
load_dotenv()

class Config:
    # Look for the Groq Key
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")
    
    # Database Settings
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_NAME = os.getenv("DB_NAME")
    DB_USER = os.getenv("DB_USER")
    DB_PASSWORD = os.getenv("DB_PASSWORD")
    
    @classmethod
    def validate(cls):
        """Check if all required settings are in .env"""
        missing = []
        if not cls.GROQ_API_KEY: missing.append("GROQ_API_KEY")
        if not cls.DB_NAME: missing.append("DB_NAME")
        if not cls.DB_USER: missing.append("DB_USER")
        if not cls.DB_PASSWORD: missing.append("DB_PASSWORD")
            
        if missing:
            print(f" Error: Missing {', '.join(missing)} in .env file")
            return False
        
        print(" Configuration loaded successfully (Groq Mode).")
        return True

if __name__ == "__main__":
    Config.validate()