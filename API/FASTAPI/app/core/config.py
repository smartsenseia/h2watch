from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "h2"

    # Prefixo sqlite:/// obrigatório + barras normais para Windows
    DATABASE_URL: str = "sqlite:///C:/SOFTWARE_ELETROLISADOR/DATABASE/database.db"

    class Config:
        case_sensitive = True

settings = Settings()