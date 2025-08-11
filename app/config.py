from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    database_url: str
    pinecone_api_key: str
    pinecone_environment: str
    openai_api_key: str
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440
    upload_dir: str = "./uploads"
    max_file_size: int = 104857600  # 100MB
    
    class Config:
        env_file = ".env"

settings = Settings()