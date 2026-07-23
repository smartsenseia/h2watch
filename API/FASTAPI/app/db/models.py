from sqlalchemy import Column, Integer, Float, DateTime, Index, func
from app.db.base import Base


class Measurement(Base):
    """Uma amostra do eletrolisador lida por Modbus TCP.

    Todos os campos são anuláveis de propósito: se um registrador parar de
    responder, é melhor gravar a amostra com um buraco do que perder a
    linha inteira.
    """

    __tablename__ = "measurements"

    id = Column(Integer, primary_key=True)

    # Instante da medição, em UTC. O coletor envia timezone-aware, então a
    # coluna precisa de timezone=True para não perder o offset.
    # server_default garante ordenação mesmo se o relógio do coletor falhar.
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        index=True,
    )

    # --- Temperaturas (°C) ---------------------------------------------------
    stack_1_temperature = Column(Float)
    water_temperature = Column(Float)
    a_column_temperature = Column(Float)
    b_column_temperature = Column(Float)

    # --- Pressões (bar) ------------------------------------------------------
    h2_pressure = Column(Float)         # H2 na saída
    aim_tank_pressure = Column(Float)   # linha principal de alta

    # --- Elétricos -----------------------------------------------------------
    stack_voltage = Column(Float)       # V
    stack_current = Column(Float)       # A
    stack_load = Column(Integer)        # carga da célula, %

    # --- Água ----------------------------------------------------------------
    h2o_flow = Column(Float)            # L/min no circuito de água
    aim_water_volume = Column(Float)    # L no tanque
    water_conductivity = Column(Float)  # µS/cm
    pump_speed = Column(Integer)        # %

    # --- Secador -------------------------------------------------------------
    dryer_cycle = Column(Integer)       # contador do ciclo, n/300

    __table_args__ = (
        # Consultas de telemetria quase sempre são "últimas N amostras".
        Index("ix_measurements_timestamp_desc", timestamp.desc()),
    )

    def __repr__(self) -> str:
        return (
            f"<Measurement {self.id} {self.timestamp} "
            f"{self.stack_voltage}V {self.stack_current}A>"
        )