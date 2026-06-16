import logging
from datetime import datetime, timezone
from typing import Any, Dict

from app.db import models
from app.db.session import SessionLocal
from app.mqtt.publisher import Publisher
from app.mqtt.topics import (
    MEASUREMENTS_CREATE_RES,
    MEASUREMENTS_DELETE_RES,
    MEASUREMENTS_GET_RES,
    MEASUREMENTS_LIST_RES,
    MEASUREMENTS_UPDATE_RES,
)

logger = logging.getLogger(__name__)


# ==========================================================
# Helpers
# ==========================================================

def _get_db():
    return SessionLocal()


def _orm_to_dict(obj: Any) -> Dict[str, Any]:
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


def _normalize_timestamp(payload: dict, pub: Publisher, response_topic: str):
    """
    Normaliza o campo timestamp do payload para datetime UTC sem tzinfo.
    Retorna o payload modificado, ou None se houver erro (já publica o erro).
    """
    ts = payload.get("timestamp")

    if isinstance(ts, str):
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            payload["timestamp"] = dt
        except ValueError:
            return None, "Formato de timestamp inválido. Use ISO 8601."

    elif ts is not None and not isinstance(ts, datetime):
        return None, "O campo timestamp deve ser uma string ISO ou datetime."

    return payload, None


# ==========================================================
# Handlers
# ==========================================================

async def handle_list(client, payload: dict) -> None:
    """
    Equiv: GET /
    Payload:  { "skip": 0, "limit": 100 }
    Resposta: measurements/list/response
    """
    pub = Publisher(client)
    skip  = payload.get("skip", 0)
    limit = payload.get("limit", 100)

    db = _get_db()
    try:
        rows = (
            db.query(models.Measurement)
            .order_by(models.Measurement.timestamp.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
        await pub.measurements_list([_orm_to_dict(r) for r in rows])
        logger.debug("handle_list: retornados %d registros", len(rows))

    except Exception as e:
        logger.error("handle_list: erro na query: %s", e, exc_info=True)
        await pub.error(MEASUREMENTS_LIST_RES, f"Erro ao listar medições: {e}")

    finally:
        db.close()


async def handle_get(client, payload: dict) -> None:
    """
    Equiv: GET /{id}
    Payload:  { "id": 1 }
    Resposta: measurements/get/response
    """
    pub = Publisher(client)
    measurement_id = payload.get("id")

    if measurement_id is None:
        await pub.error(MEASUREMENTS_GET_RES, "Campo 'id' é obrigatório.")
        return

    db = _get_db()
    try:
        row = (
            db.query(models.Measurement)
            .filter(models.Measurement.id == measurement_id)
            .first()
        )
        if not row:
            await pub.error(MEASUREMENTS_GET_RES, "Medição não encontrada.", code=404)
            return

        await pub.measurements_get(_orm_to_dict(row))

    except Exception as e:
        logger.error("handle_get: erro na query: %s", e, exc_info=True)
        await pub.error(MEASUREMENTS_GET_RES, f"Erro ao buscar medição: {e}")

    finally:
        db.close()


async def handle_create(client, payload: dict) -> None:
    """
    Equiv: POST /post
    Payload:  { "timestamp": "2024-01-15T10:30:00Z", "valor": 22.5, ... }
    Resposta: measurements/create/response
    """
    pub = Publisher(client)

    # Normalização do timestamp
    payload, err = _normalize_timestamp(payload, pub, MEASUREMENTS_CREATE_RES)
    if err:
        await pub.error(MEASUREMENTS_CREATE_RES, err)
        return

    # Sanitização — só colunas válidas do modelo
    allowed = {c.name for c in models.Measurement.__table__.columns}
    cleaned = {k: v for k, v in payload.items() if k in allowed}

    db = _get_db()
    try:
        new_row = models.Measurement(**cleaned)
        db.add(new_row)
        db.commit()
        db.refresh(new_row)
        await pub.measurements_created(_orm_to_dict(new_row))
        logger.debug("handle_create: medição criada id=%s", new_row.id)

    except TypeError as e:
        await pub.error(MEASUREMENTS_CREATE_RES, f"Erro na estrutura dos dados: {e}")

    except Exception as e:
        db.rollback()
        logger.error("handle_create: erro ao persistir: %s", e, exc_info=True)
        await pub.error(MEASUREMENTS_CREATE_RES, f"Erro ao criar medição: {e}")

    finally:
        db.close()


async def handle_update(client, payload: dict) -> None:
    """
    Equiv: PUT /{id}
    Payload:  { "id": 1, "valor": 25.0, ... }
    Resposta: measurements/update/response
    """
    pub = Publisher(client)
    measurement_id = payload.get("id")

    if measurement_id is None:
        await pub.error(MEASUREMENTS_UPDATE_RES, "Campo 'id' é obrigatório.")
        return

    db = _get_db()
    try:
        row = (
            db.query(models.Measurement)
            .filter(models.Measurement.id == measurement_id)
            .first()
        )
        if not row:
            await pub.error(MEASUREMENTS_UPDATE_RES, "Medição não encontrada para atualização.", code=404)
            return

        allowed = {c.name for c in models.Measurement.__table__.columns}
        for key, value in payload.items():
            if key in allowed and key != "id":
                setattr(row, key, value)

        db.commit()
        db.refresh(row)
        await pub.measurements_updated(_orm_to_dict(row))
        logger.debug("handle_update: medição id=%s atualizada", measurement_id)

    except Exception as e:
        db.rollback()
        logger.error("handle_update: erro ao atualizar: %s", e, exc_info=True)
        await pub.error(MEASUREMENTS_UPDATE_RES, f"Erro ao atualizar medição: {e}")

    finally:
        db.close()


async def handle_delete(client, payload: dict) -> None:
    """
    Equiv: DELETE /{id}
    Payload:  { "id": 1 }
    Resposta: measurements/delete/response
    """
    pub = Publisher(client)
    measurement_id = payload.get("id")

    if measurement_id is None:
        await pub.error(MEASUREMENTS_DELETE_RES, "Campo 'id' é obrigatório.")
        return

    db = _get_db()
    try:
        row = (
            db.query(models.Measurement)
            .filter(models.Measurement.id == measurement_id)
            .first()
        )
        if not row:
            await pub.error(MEASUREMENTS_DELETE_RES, "Medição não encontrada para exclusão.", code=404)
            return

        db.delete(row)
        db.commit()
        await pub.measurements_deleted("Medição excluída com sucesso.")
        logger.debug("handle_delete: medição id=%s excluída", measurement_id)

    except Exception as e:
        db.rollback()
        logger.error("handle_delete: erro ao excluir: %s", e, exc_info=True)
        await pub.error(MEASUREMENTS_DELETE_RES, f"Erro ao excluir medição: {e}")

    finally:
        db.close()