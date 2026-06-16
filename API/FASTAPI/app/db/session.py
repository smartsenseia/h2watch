from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings

# -------------------------------------------------------------------------
# 1. Automação de Infraestrutura (Criação de Pastas)
# -------------------------------------------------------------------------
# Este bloco verifica se você está usando SQLite e, se sim, garante que a
# pasta onde o arquivo .db ficará guardado realmente exista.
if settings.DATABASE_URL.startswith("sqlite:///"):
    # Extrai o caminho do arquivo da string de conexão
    db_path = settings.DATABASE_URL.replace("sqlite:///", "", 1)
    # Cria os diretórios pais (ex: /DATABASE/) caso não existam
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------------------
# 2. Configuração do Engine (O Motor)
# -------------------------------------------------------------------------
# O Engine é o componente que realmente sabe como "falar" com o banco de dados.
engine = create_engine(
    settings.DATABASE_URL,
    # 'check_same_thread': False é exclusivo para SQLite. 
    # Permite que o FastAPI (que é assíncrono) use a mesma conexão em threads diferentes.
    connect_args={"check_same_thread": False},
)

# -------------------------------------------------------------------------
# 3. Fábrica de Sessões (SessionLocal)
# -------------------------------------------------------------------------
# SessionLocal é uma classe que gera novas sessões de banco de dados.
# Não é a conexão em si, mas um "molde" para criá-las quando necessário.
SessionLocal = sessionmaker(
    autocommit=False, # Impede que o banco salve alterações automaticamente sem o seu comando .commit()
    autoflush=False,  # Evita que o SQLAlchemy envie mudanças ao banco antes de você pedir
    bind=engine,      # Conecta esta fábrica ao motor criado acima
)

# -------------------------------------------------------------------------
# 4. Dependência do FastAPI (Injeção de Dependência)
# -------------------------------------------------------------------------
def get_db():
    """
    Função geradora que cria uma nova sessão para cada requisição HTTP.
    - Abre a conexão.
    - Entrega a sessão para quem pediu (yield).
    - Garante o fechamento da conexão após o fim da requisição (finally).
    """
    db = SessionLocal()
    try:
        yield db  # A execução da rota acontece aqui
    finally:
        db.close() # Importante para não esgotar as conexões do banco