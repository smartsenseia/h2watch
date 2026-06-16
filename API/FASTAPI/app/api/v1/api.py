from fastapi import APIRouter
from app.api.v1.endpoints import endpoints
from app.api.v1.endpoints import auth

# Inicializa o roteador principal da API V1
# O APIRouter funciona como um "agrupador" de rotas para organizar o projeto em módulos

api_router = APIRouter()
api_router.include_router(auth.router)  # <-- /api/v1/auth/...

### Configuração de Rotas
# Aqui incluímos as rotas definidas no arquivo 'endpoints.py'
# prefix="/endpoints": Todas as URLs desse módulo começarão com /endpoints
# tags=["endpoints"]: Agrupa essas rotas sob o nome "endpoints" na documentação interativa (/docs)

api_router.include_router(
    endpoints.router, 
    prefix="/endpoints", 
    tags=["endpoints"]
)