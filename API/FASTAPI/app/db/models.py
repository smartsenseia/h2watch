from sqlalchemy import Column, Integer, Float, DateTime
from datetime import datetime
from app.db.base import Base


class Measurement(Base):
    __tablename__ = "measurements"

    id = Column(Integer, primary_key=True, index=True)

    # Timestamp da medição
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    stack_1_temperature = Column(Float)
    stack_2_temperature = Column(Float)
    water_temperature = Column(Float)
    a_column_temperature = Column(Float)
    b_column_temperature = Column(Float)
    h2_pressure = Column(Float)
    aim_tank_pressure = Column(Float)
    stack_voltage = Column(Float)
    stack_current = Column(Float)
    h2_flow = Column(Float)
    aim_water_volume = Column(Float)
    water_conductivity = Column(Float)