###### ARQUITETURA ######

DATAQATAR/
├── ALGORITHMS_AND_DATA/
│   ├── __pycache__/
│   ├── connection.py
│   ├── indicadores.py
│   └── teste.py
│
├── FASTAPI/
│   ├── app/
│   │   ├── __pycache__/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── __pycache__/
│   │   │   └── v1/
│   │   │       ├── __pycache__/
│   │   │       ├── api.py
│   │   │       ├── deps.py
│   │   │       └── endpoints/
│   │   │           ├── __pycache__/
│   │   │           └── endpoints.py
│   │   │
│   │   ├── core/
│   │   │   ├── __pycache__/
│   │   │   └── config.py
│   │   │
│   │   └── db/
│   │       ├── __pycache__/
│   │       ├── base.py
│   │       ├── models.py
│   │       ├── session.py
│   │       └── main.py
│
│   ├── .env
│   ├── database.db
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── README.md
│   └── requirements.txt
│
├── FRONTEND/
│   ├── __pycache__/
│   └── frontend.py
│
├── venv/
│   └── ... (ambiente virtual)
│
└── main.py


##### FLUXO DE FUNCIONAMENTO ######

main.py
   └── app = FastAPI()
         └── carrega core/config.py (variáveis ambiente)
         └── api_router (api/api.py)
                 ├── endpoints/users.py
                 └── endpoints/items.py
                     └── db/session.py (conexão)
                         └── db/models/*.py


##### RESUMO DO FLUXO ####

main.py → Inicializa o FastAPI.

core/config.py → Carrega as configurações ao iniciar.

api/api.py → Carrega e agrupa endpoints.

Endpoints específicos são carregados no router.

Sessão do DB (session.py) é inicializada quando endpoints chamam CRUD.

Modelos são usados ao interagir com o banco.

