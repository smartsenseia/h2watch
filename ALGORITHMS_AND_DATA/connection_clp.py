# -*- coding: utf-8 -*-
"""
connection_clp.py — Leitura de dados do CLP ABB via Modbus TCP

Diferença em relação ao Siemens/snap7:
  - Siemens: valores Int 16-bit raw (0–27648) → precisavam de norm() + scale()
  - ABB Modbus: valores Float 32-bit já em unidade de engenharia → leitura direta

Preencha REGISTRADORES com os endereços descobertos pelo scanner_modbus.py.
"""

import struct
from pymodbus.client import ModbusTcpClient

# ==========================================================
# Config de conexão
# ==========================================================

CLP_IP   = "192.168.0.10"  # ← IP do CLP ABB (mesmo IP do Siemens antes)
CLP_PORT = 502
SLAVE_ID = 1

# ==========================================================
# Ranges físicos
# (mantidos para validação — no Siemens eram usados no scale())
# ==========================================================

TEMP_MIN = 0.0
TEMP_MAX = 150.0

FLOW_MIN = 0.0
FLOW_MAX = 100.0

PI01_MIN = -1.0
PI01_MAX = 1.0

PI02_MIN = -1.0
PI02_MAX = 1.0

PI03_MIN = -1.0
PI03_MAX = 1.0

PI04_MIN = 0.0
PI04_MAX = 3.0

PI05_MIN = 0.0
PI05_MAX = 3.0

# ==========================================================
# Mapeamento de registradores Modbus
# Cada float 32-bit ocupa 2 registradores consecutivos
# Preencha após rodar scanner_modbus.py
# ==========================================================

REGISTRADORES = {

    # Temperaturas — mesma ordem do db_read() do Siemens
    "TI01": 0,    # era get_int(data, 0)
    "TI02": 2,    # era get_int(data, 2)
    "TI03": 4,    # era get_int(data, 4)
    "TI04": 6,    # era get_int(data, 6)
    "TI05": 8,    # era get_int(data, 8)
    "TI06": 10,   # era get_int(data, 10)
    "TI07": 12,   # era get_int(data, 12)
    "TI08": 14,   # era get_int(data, 14)
    "TI09": 16,   # era get_int(data, 16)
    "TI10": 18,   # era get_int(data, 18)
    "TI_A": 20,   # era get_int(data, 20)
    "TI_B": 22,   # era get_int(data, 22)
    "TI11": 24,   # era get_int(data, 42)

    # Vazões
    "FI01": 30,   # era get_int(data, 24)
    "FI02": 32,   # era get_int(data, 26)
    "FI03": 34,   # era get_int(data, 28)
    "FI04": 36,   # era get_int(data, 30)

    # Pressões
    "PI01": 40,   # era get_int(data, 32)
    "PI02": 42,   # era get_int(data, 34)
    "PI03": 44,   # era get_int(data, 36)
    "PI04": 46,   # era get_int(data, 38)
    "PI05": 48,   # era get_int(data, 44)

    # Válvula
    "VALVULA": 50,  # era get_int(data, 40)
}

# ==========================================================
# Helpers
# ==========================================================

def _regs_to_float(r1: int, r2: int) -> float:
    """
    Converte 2 registradores Modbus (16-bit cada) em float 32-bit.
    Big-endian é o padrão Modbus. Se os valores saírem errados,
    troque para: struct.pack('<HH', r2, r1)
    """
    raw = struct.pack(">HH", r1, r2)
    return round(struct.unpack(">f", raw)[0], 4)


def _ler_float(client: ModbusTcpClient, reg: int) -> float:
    """Lê um float 32-bit a partir do registrador `reg`."""
    resp = client.read_holding_registers(reg, count=2, slave=SLAVE_ID)
    if resp.isError():
        raise ConnectionError(f"Erro ao ler registrador {reg}: {resp}")
    return _regs_to_float(*resp.registers)


def _clamp(value: float, vmin: float, vmax: float) -> float:
    """
    Opcional: garante que o valor está dentro do range físico esperado.
    Substitui a validação implícita que o scale() fazia no Siemens.
    """
    return max(vmin, min(vmax, value))


# ==========================================================
# Função principal — mesma assinatura do código original
# ==========================================================

def ler_dados_clp() -> dict:
    """
    Conecta ao CLP ABB via Modbus TCP e retorna os dados no mesmo
    formato do código original (Siemens/snap7), sem nenhuma conversão
    manual — o ABB já entrega os valores em unidade de engenharia.
    """
    client = ModbusTcpClient(CLP_IP, port=CLP_PORT)

    if not client.connect():
        raise ConnectionError(
            f"Não foi possível conectar ao CLP ABB em {CLP_IP}:{CLP_PORT}"
        )

    try:

        # Temperaturas — ABB já entrega em °C (era raw/27648 * 150 no Siemens)
        TI01 = _clamp(_ler_float(client, REGISTRADORES["TI01"]), TEMP_MIN, TEMP_MAX)
        TI02 = _clamp(_ler_float(client, REGISTRADORES["TI02"]), TEMP_MIN, TEMP_MAX)
        TI03 = _clamp(_ler_float(client, REGISTRADORES["TI03"]), TEMP_MIN, TEMP_MAX)
        TI04 = _clamp(_ler_float(client, REGISTRADORES["TI04"]), TEMP_MIN, TEMP_MAX)
        TI05 = _clamp(_ler_float(client, REGISTRADORES["TI05"]), TEMP_MIN, TEMP_MAX)
        TI06 = _clamp(_ler_float(client, REGISTRADORES["TI06"]), TEMP_MIN, TEMP_MAX)
        TI07 = _clamp(_ler_float(client, REGISTRADORES["TI07"]), TEMP_MIN, TEMP_MAX)
        TI08 = _clamp(_ler_float(client, REGISTRADORES["TI08"]), TEMP_MIN, TEMP_MAX)
        TI09 = _clamp(_ler_float(client, REGISTRADORES["TI09"]), TEMP_MIN, TEMP_MAX)
        TI10 = _clamp(_ler_float(client, REGISTRADORES["TI10"]), TEMP_MIN, TEMP_MAX)
        TI_A = _clamp(_ler_float(client, REGISTRADORES["TI_A"]), TEMP_MIN, TEMP_MAX)
        TI_B = _clamp(_ler_float(client, REGISTRADORES["TI_B"]), TEMP_MIN, TEMP_MAX)
        TI11 = _clamp(_ler_float(client, REGISTRADORES["TI11"]), TEMP_MIN, TEMP_MAX)

        # Vazões — ABB já entrega em unidade de engenharia (era raw/27648 * 100)
        FI01 = _clamp(_ler_float(client, REGISTRADORES["FI01"]), FLOW_MIN, FLOW_MAX)
        FI02 = _clamp(_ler_float(client, REGISTRADORES["FI02"]), FLOW_MIN, FLOW_MAX)
        FI03 = _clamp(_ler_float(client, REGISTRADORES["FI03"]), FLOW_MIN, FLOW_MAX)
        FI04 = _clamp(_ler_float(client, REGISTRADORES["FI04"]), FLOW_MIN, FLOW_MAX)

        # Pressões — ABB já entrega em bar/kPa
        PI01 = _clamp(_ler_float(client, REGISTRADORES["PI01"]), PI01_MIN, PI01_MAX)
        PI02 = _clamp(_ler_float(client, REGISTRADORES["PI02"]), PI02_MIN, PI02_MAX)
        PI03 = _clamp(_ler_float(client, REGISTRADORES["PI03"]), PI03_MIN, PI03_MAX)
        PI04 = _clamp(_ler_float(client, REGISTRADORES["PI04"]), PI04_MIN, PI04_MAX)
        PI05 = _clamp(_ler_float(client, REGISTRADORES["PI05"]), PI05_MIN, PI05_MAX)

        # Válvula — ABB já entrega em % (era raw/27648 * 100 no Siemens)
        VALVULA = _clamp(_ler_float(client, REGISTRADORES["VALVULA"]), 0.0, 100.0)

    finally:
        client.close()

    return {
        "temperaturas": {
            "TI01": TI01,
            "TI02": TI02,
            "TI03": TI03,
            "TI04": TI04,
            "TI05": TI05,
            "TI06": TI06,
            "TI07": TI07,
            "TI08": TI08,
            "TI09": TI09,
            "TI10": TI10,
            "TI_A": TI_A,
            "TI_B": TI_B,
            "TI11": TI11,
        },
        "pressoes": {
            "PI01": PI01,
            "PI02": PI02,
            "PI03": PI03,
            "PI04": PI04,
            "PI05": PI05,
        },
        "vazoes": {
            "FI01": FI01,
            "FI02": FI02,
            "FI03": FI03,
            "FI04": FI04,
        },
        "valvula": VALVULA,
    }