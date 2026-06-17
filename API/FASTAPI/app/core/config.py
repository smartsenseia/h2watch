from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Classe de configuração centralizada.
    O Pydantic Settings permite que você defina valores padrão, mas também
    permite que eles sejam sobrescritos por variáveis de ambiente (.env).
    """

    # Prefixo padrão para todas as rotas da API (versão 1)
    API_V1_STR: str = "/api/v1"
    
    # Nome do projeto que aparecerá na documentação automática
    PROJECT_NAME: str = "h2"

    # String de conexão com o banco de dados. 
    # Atualmente configurada para um SQLite local em um caminho específico.
    DATABASE_URL: str = "sqlite:///C:/Users/Master/Desktop/SOFTWARE_ELETROLISADOR/DATABASE/database.db"

    class Config:
        # Permite que o Pydantic ignore campos extras e trate strings de forma case-insensitive
        case_sensitive = True

# Instanciamos a classe para que possamos importar 'settings' em qualquer lugar do projeto
# Exemplo: from app.core.config import settings
settings = Settings()