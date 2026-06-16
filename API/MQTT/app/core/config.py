"""
config.py — Configurações centrais da aplicação

Lê variáveis de ambiente automaticamente.
Crie um arquivo .env na raiz do projeto com as variáveis abaixo.

Exemplo de .env:
    MQTT_HOST=192.168.0.10
    MQTT_PORT=1883
    MQTT_USERNAME=admin
    MQTT_PASSWORD=senha123
    DATABASE_URL=postgresql://user:pass@localhost:5432/mydb
    ASSET_ID=MD01BR01
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):

    # ==========================================================
    # MQTT
    # ==========================================================

    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883

    # Deixe vazio se o broker não exigir autenticação
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""

    # ID único do cliente no broker (gerado automaticamente se vazio)
    MQTT_CLIENT_ID: str = ""

    # Intervalo de keepalive em segundos
    MQTT_KEEPALIVE: int = 60

    # Reconexão: tempo mínimo e máximo de espera (backoff exponencial)
    MQTT_RECONNECT_DELAY_MIN: float = 1.0
    MQTT_RECONNECT_DELAY_MAX: float = 60.0

    # ==========================================================
    # Banco de dados
    # ==========================================================

    DATABASE_URL: str = "sqlite:///./db.sqlite3"

    # ==========================================================
    # Aplicação
    # ==========================================================

    ASSET_ID: str = "MD01BR01"
    LOOP_SECONDS: float = 1.0

    # Nível de log: DEBUG, INFO, WARNING, ERROR
    LOG_LEVEL: str = "INFO"

    # ==========================================================
    # Pydantic config
    # ==========================================================

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",       # ignora variáveis do .env que não estão aqui
    )


# Instância global — importe em qualquer lugar com:
#   from app.core.config import settings
settings = Settings()