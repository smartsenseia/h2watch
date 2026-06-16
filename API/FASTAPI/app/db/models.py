from sqlalchemy import Column, Integer, Float, DateTime
from datetime import datetime
from app.db.base import Base


class Measurement(Base):
    __tablename__ = "measurements"

    id = Column(Integer, primary_key=True, index=True)

    # Timestamp da medição
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    # -----------------------------
    # Temperaturas
    # -----------------------------

    temp_1 = Column(Float)
    temp_2 = Column(Float)
    temp_3 = Column(Float)
    temp_4 = Column(Float)
    temp_5 = Column(Float)
    temp_6 = Column(Float)
    temp_7 = Column(Float)
    temp_8 = Column(Float)
    temp_9 = Column(Float)
    temp_10 = Column(Float)
    temp_11 = Column(Float)

    temp_A = Column(Float)
    temp_B = Column(Float)

    # -----------------------------
    # Pressões
    # -----------------------------

    pressao_1 = Column(Float)
    pressao_2 = Column(Float)
    pressao_3 = Column(Float)
    pressao_4 = Column(Float)
    pressao_5 = Column(Float)

    # -----------------------------
    # Vazões
    # -----------------------------

    vazao_1 = Column(Float)
    vazao_2 = Column(Float)
    vazao_3 = Column(Float)
    vazao_4 = Column(Float)

    # -----------------------------
    # Atuador
    # -----------------------------

    valvula = Column(Float)