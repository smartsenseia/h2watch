"""
topics.py — Constantes de tópicos MQTT

Organização:
    <domínio>/<recurso>/<ação>

Convenção:
    - Requisições terminam em /request
    - Respostas  terminam em /response
    - Comandos diretos (sem resposta esperada) não têm sufixo
    - Wildcards usam '#' para qualquer subtópico
"""

# ==========================================================
# Measurements
# ==========================================================

# Listar
MEASUREMENTS_LIST_REQ = "measurements/list/request"
MEASUREMENTS_LIST_RES = "measurements/list/response"

# Buscar por ID
MEASUREMENTS_GET_REQ  = "measurements/get/request"
MEASUREMENTS_GET_RES  = "measurements/get/response"

# Criar
MEASUREMENTS_CREATE     = "measurements/create"
MEASUREMENTS_CREATE_RES = "measurements/create/response"

# Atualizar
MEASUREMENTS_UPDATE     = "measurements/update"
MEASUREMENTS_UPDATE_RES = "measurements/update/response"

# Deletar
MEASUREMENTS_DELETE     = "measurements/delete"
MEASUREMENTS_DELETE_RES = "measurements/delete/response"

# Wildcard — escuta qualquer tópico de measurements
MEASUREMENTS_ALL = "measurements/#"


# ==========================================================
# Sistema
# ==========================================================

SISTEMA_HEARTBEAT = "sistema/heartbeat"
SISTEMA_STATUS    = "sistema/status"
SISTEMA_ERRO      = "sistema/erro"


# ==========================================================
# Sensor (exemplo para expansão futura)
# ==========================================================

# Dado bruto de um sensor específico: sensor/<id>/data
# Use f-string: f"sensor/{sensor_id}/data"
SENSOR_DATA_TEMPLATE    = "sensor/{sensor_id}/data"
SENSOR_COMANDO_TEMPLATE = "sensor/{sensor_id}/comando"

# Wildcard — escuta dados de todos os sensores
SENSOR_ALL_DATA    = "sensor/+/data"     # '+' = um nível qualquer
SENSOR_ALL_COMANDO = "sensor/+/comando"
SENSOR_ALL         = "sensor/#"          # '#' = qualquer subtópico


# ==========================================================
# Helpers
# ==========================================================

def sensor_data(sensor_id: str) -> str:
    """Retorna o tópico de dados para um sensor específico."""
    return SENSOR_DATA_TEMPLATE.format(sensor_id=sensor_id)


def sensor_comando(sensor_id: str) -> str:
    """Retorna o tópico de comando para um sensor específico."""
    return SENSOR_COMANDO_TEMPLATE.format(sensor_id=sensor_id)


# ==========================================================
# Mapa de request → response
# (útil para o dispatcher montar respostas automaticamente)
# ==========================================================

RESPONSE_MAP: dict[str, str] = {
    MEASUREMENTS_LIST_REQ:  MEASUREMENTS_LIST_RES,
    MEASUREMENTS_GET_REQ:   MEASUREMENTS_GET_RES,
    MEASUREMENTS_CREATE:    MEASUREMENTS_CREATE_RES,
    MEASUREMENTS_UPDATE:    MEASUREMENTS_UPDATE_RES,
    MEASUREMENTS_DELETE:    MEASUREMENTS_DELETE_RES,
}


# ==========================================================
# Todos os tópicos que o servidor deve assinar
# ==========================================================

SUBSCRIBE_TOPICS: list[str] = [
    MEASUREMENTS_LIST_REQ,
    MEASUREMENTS_GET_REQ,
    MEASUREMENTS_CREATE,
    MEASUREMENTS_UPDATE,
    MEASUREMENTS_DELETE,
]