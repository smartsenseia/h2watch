"""
session.py — Configuração da sessão SQLAlchemy

Cria o engine SQLite e a fábrica de sessões (SessionLocal).
Também expõe init_db() para criar as tabelas na primeira execução.
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.models import Base


# ==========================================================
# Engine
# ==========================================================

engine = create_engine(
    settings.DATABASE_URL,
    # check_same_thread=False obrigatório para SQLite com múltiplas threads
    # (necessário pois o MQTT roda em thread separada do loop principal)
    connect_args={"check_same_thread": False},
    # Mantém 5 conexões no pool; ajuste conforme a carga
    pool_size=5,
    max_overflow=10,
)


# Ativa WAL mode no SQLite — melhora concorrência de leitura/escrita
# entre o loop do PLC e o cliente MQTT
@event.listens_for(engine, "connect")
def _set_wal_mode(dbapi_conn, _):
    dbapi_conn.execute("PRAGMA journal_mode=WAL;")
    dbapi_conn.execute("PRAGMA synchronous=NORMAL;")


# ==========================================================
# SessionLocal
# ==========================================================

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ==========================================================
# Criação das tabelas
# ==========================================================

def init_db() -> None:
    """
    Cria todas as tabelas definidas em models.py se ainda não existirem.
    Chame uma vez na inicialização da aplicação (main.py).
    """
    Base.metadata.create_all(bind=engine)