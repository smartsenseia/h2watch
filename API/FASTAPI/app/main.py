from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response, FileResponse
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.api import api_router
from app.core.config import settings
from app.db.base import Base
from app.db.session import engine

from pathlib import Path

app = FastAPI(title=settings.PROJECT_NAME, version="1.0.0")

# ==========================================================
# CORS
# ==========================================================

origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://192.168.0.6:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://192.168.0.6:5173",
    "https://dashboard.smartsenseiatrl6.org",
    "https://api.smartsenseiatrl6.org",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================================
# API
# ==========================================================

app.include_router(api_router, prefix=settings.API_V1_STR)

# ==========================================================
# Startup
# ==========================================================

@app.on_event("startup")
def on_startup():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Banco de Dados inicializado com sucesso.")
    except Exception as e:
        print(f"⚠️ Erro ao conectar no DB durante o startup: {e}")


# ==========================================================
# React build path
# ==========================================================

APP_DIR = Path(__file__).resolve().parent
FASTAPI_DIR = APP_DIR.parent
PROJECT_DIR = FASTAPI_DIR.parent

FRONTEND_DIST   = PROJECT_DIR.parent / "FRONTEND" / "dist"
FRONTEND_ASSETS = FRONTEND_DIST / "assets"
INDEX_HTML      = FRONTEND_DIST / "index.html"

print(f"🔎 Procurando React build em: {FRONTEND_DIST}")


# ==========================================================
# Servir React em produção
# ==========================================================

if FRONTEND_DIST.exists() and INDEX_HTML.exists():

    if FRONTEND_ASSETS.exists():
        app.mount(
            "/assets",
            StaticFiles(directory=FRONTEND_ASSETS),
            name="react-assets"
        )

    @app.get("/", include_in_schema=False)
    async def serve_react_root():
        return FileResponse(INDEX_HTML)

    @app.get("/{full_path:path}", include_in_schema=False)
    async def serve_react_routes(full_path: str):
        if full_path.startswith(settings.API_V1_STR.strip("/")):
            return Response(
                content="API route not found",
                status_code=404
            )

        requested_file = FRONTEND_DIST / full_path

        if requested_file.exists() and requested_file.is_file():
            return FileResponse(requested_file)

        return FileResponse(INDEX_HTML)

    print("✅ React build encontrado e servido pelo FastAPI.")

else:

    print("⚠️ React build não encontrado.")

    @app.get("/", include_in_schema=False)
    async def no_build():
        return Response(
            content="React build não encontrado. Rode o main.py da raiz para gerar npm run build.",
            status_code=404
        )