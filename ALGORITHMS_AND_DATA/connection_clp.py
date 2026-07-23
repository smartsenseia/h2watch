# -*- coding: utf-8 -*-
"""Conexão e leitura do eletrolisador por Modbus TCP."""

from __future__ import annotations
import struct
from pymodbus.client import ModbusTcpClient

__all__ = ["ler_dados_clp"]


# -----------------------------------------------------------------------------
# Conexão
# -----------------------------------------------------------------------------
CLP_IP = "192.168.0.35"
CLP_PORT = 502
SOURCE_IP = "192.168.0.36"  # IP Ethernet do computador
TIMEOUT = 5.0


# nome: (registrador, tipo, escala, valor mínimo, valor máximo)
#
# Os registradores 6, 681, 687, 1008 e 1010 foram mantidos para preservar
# o funcionamento atual, mas ainda precisam ser confirmados contra a IHM.
SINAIS = {
    # Ainda não identificados corretamente
    "stack_1_temperature": (None, "zero", 0.0, 0.0, 0.0),
    "stack_2_temperature": (None, "zero", 0.0, 0.0, 0.0),
    "water_temperature": (526, "i16", 0.01, 0.0, 100.0),
    "a_column_temperature": (None, "zero", 0.0, -50.0, 300.0),
    "b_column_temperature": (None, "zero", 0.0, -50.0, 300.0),
    "h2_pressure": (None, "zero", 0.0, 0.0, 50.0),
    "aim_tank_pressure": (None, "zero", 0.0, 0.0, 50.0),
    "stack_voltage": (None, "zero", 0.0, 0.0, 100.0),
    "stack_current": (None, "zero", 0.0, 0.0, 100.0),
    "h2_flow": (582, "i16", 0.1, 0.0, 20.0),
    "aim_water_volume": (586, "i16", 0.1, 0.0, 200.0),
    "water_conductivity": (None, "zero", 0.0, 0.0, 20.0),
}


# Somente os blocos necessários para os sinais acima.
# Formato: (registrador inicial, quantidade)
BLOCOS_LEITURA = (
    (6, 2),       # pressão H2: registradores 6 e 7
    (506, 81),    # registradores 506 até 586
    (681, 9),     # registradores 681 até 689
    (1008, 4),    # registradores 1008 até 1011
)


def _i16(valor: int) -> int:
    """Converte unsigned 16 bits para signed 16 bits."""
    return valor if valor < 32768 else valor - 65536


def _f32_le(reg1: int, reg2: int) -> float:
    """Decodifica dois registradores como float32 little-endian."""
    return struct.unpack("<f", struct.pack("<HH", reg1, reg2))[0]


def _f32_be(reg1: int, reg2: int) -> float:
    """Decodifica dois registradores como float32 big-endian."""
    return struct.unpack(">f", struct.pack(">HH", reg1, reg2))[0]


def _conectar() -> ModbusTcpClient:
    client = ModbusTcpClient(
        host=CLP_IP,
        port=CLP_PORT,
        timeout=TIMEOUT,
        source_address=(SOURCE_IP, 0),
    )

    if not client.connect():
        client.close()
        raise ConnectionError(
            f"Falha ao conectar ao CLP {CLP_IP}:{CLP_PORT} "
            f"pela interface local {SOURCE_IP}."
        )

    return client


def _ler_bloco(
    client: ModbusTcpClient,
    inicio: int,
    quantidade: int,
) -> dict[int, int]:
    resposta = client.read_holding_registers(inicio, count=quantidade)

    if resposta is None or resposta.isError():
        fim = inicio + quantidade - 1
        raise RuntimeError(
            f"Falha na leitura Modbus dos registradores {inicio} a {fim}."
        )

    if len(resposta.registers) != quantidade:
        raise RuntimeError(
            f"Leitura incompleta a partir do registrador {inicio}: "
            f"esperados {quantidade}, recebidos {len(resposta.registers)}."
        )

    return {
        inicio + indice: valor
        for indice, valor in enumerate(resposta.registers)
    }


def _decodificar(
    registradores: dict[int, int],
    configuracao: tuple,
) -> float:
    reg, tipo, escala, minimo, maximo = configuracao

    if tipo == "zero":
        return 0.0

    try:
        if tipo == "i16":
            bruto = float(_i16(registradores[reg]))
        elif tipo == "f32le":
            bruto = float(
                _f32_le(registradores[reg], registradores[reg + 1])
            )
        elif tipo == "f32be":
            bruto = float(
                _f32_be(registradores[reg], registradores[reg + 1])
            )
        else:
            raise ValueError(f"Tipo Modbus desconhecido: {tipo}")
    except KeyError as erro:
        raise RuntimeError(
            f"Registrador {erro.args[0]} não recebido do CLP."
        ) from erro

    valor = bruto * escala
    valor = max(minimo, min(maximo, valor))
    return round(valor, 4)


def ler_dados_clp() -> dict[str, float]:
    """Lê e retorna somente os dados usados pelo código de envio."""
    client = _conectar()

    try:
        registradores: dict[int, int] = {}

        for inicio, quantidade in BLOCOS_LEITURA:
            registradores.update(
                _ler_bloco(client, inicio, quantidade)
            )
    finally:
        client.close()

    return {
        nome: _decodificar(registradores, configuracao)
        for nome, configuracao in SINAIS.items()
    }