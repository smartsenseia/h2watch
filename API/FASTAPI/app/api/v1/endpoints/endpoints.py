from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from app.db import models
from app.db.session import get_db

router = APIRouter()


def orm_to_dict(obj: Any) -> Dict[str, Any]:
    """
    Converte um objeto SQLAlchemy (ORM) em dict usando as colunas reais da tabela.
    """
    return {c.name: getattr(obj, c.name) for c in obj.__table__.columns}


# 1) Listar Medições (GET)
@router.get("/", response_model=List[dict])
def read_measurements(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    rows = (
        db.query(models.Measurement)
        .order_by(models.Measurement.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    # ✅ retorna list[dict], como o response_model exige
    return [orm_to_dict(r) for r in rows]


# 2) Buscar por ID (GET)
@router.get("/{measurement_id}", response_model=dict)
def read_measurement(measurement_id: int, db: Session = Depends(get_db)):
    measurement = (
        db.query(models.Measurement)
        .filter(models.Measurement.id == measurement_id)
        .first()
    )
    if not measurement:
        raise HTTPException(status_code=404, detail="Medição não encontrada.")
    # ✅ retorna dict
    return orm_to_dict(measurement)


# 3) Criar Medição (POST)
@router.post("/post", response_model=dict)
def create_measurement(measurement: dict, db: Session = Depends(get_db)):
    # --- Passo A: Normalização do Timestamp ---
    ts = measurement.get("timestamp")

    if isinstance(ts, str):
        try:
            ts_norm = ts.replace("Z", "+00:00")
            dt = datetime.fromisoformat(ts_norm)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            measurement["timestamp"] = dt
        except ValueError:
            raise HTTPException(status_code=400, detail="Formato de timestamp inválido. Use ISO 8601.")
    elif ts is not None and not isinstance(ts, datetime):
        raise HTTPException(status_code=400, detail="O campo timestamp deve ser uma string ISO ou datetime.")

    # --- Passo B: Sanitização ---
    allowed_columns = {c.name for c in models.Measurement.__table__.columns}
    cleaned_data = {k: v for k, v in measurement.items() if k in allowed_columns}

    # --- Passo C: Persistência ---
    try:
        new_measurement = models.Measurement(**cleaned_data)
        db.add(new_measurement)
        db.commit()
        db.refresh(new_measurement)
        # ✅ retorna dict
        return orm_to_dict(new_measurement)
    except TypeError as e:
        raise HTTPException(status_code=400, detail=f"Erro na estrutura dos dados: {e}")


# 4) Atualizar Medição (PUT)
@router.put("/{measurement_id}", response_model=dict)
def update_measurement(measurement_id: int, measurement: dict, db: Session = Depends(get_db)):
    db_measurement = (
        db.query(models.Measurement)
        .filter(models.Measurement.id == measurement_id)
        .first()
    )
    if not db_measurement:
        raise HTTPException(status_code=404, detail="Medição não encontrada para atualização.")

    # ✅ atualiza só colunas válidas (evita setar lixo e quebrar)
    allowed_columns = {c.name for c in models.Measurement.__table__.columns}
    for key, value in measurement.items():
        if key in allowed_columns and key != "id":
            setattr(db_measurement, key, value)

    db.commit()
    db.refresh(db_measurement)
    return orm_to_dict(db_measurement)


# 5) Deletar Medição (DELETE)
@router.delete("/{measurement_id}", response_model=dict)
def delete_measurement(measurement_id: int, db: Session = Depends(get_db)):
    db_measurement = (
        db.query(models.Measurement)
        .filter(models.Measurement.id == measurement_id)
        .first()
    )
    if not db_measurement:
        raise HTTPException(status_code=404, detail="Medição não encontrada para exclusão.")

    db.delete(db_measurement)
    db.commit()
    return {"detail": "Medição excluída com sucesso."}
