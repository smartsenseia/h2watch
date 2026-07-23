# -*- coding: utf-8 -*-
"""Conexão e leitura do eletrolisador por Modbus TCP.

Mapeamento de registradores obtido em 21/07/2026 cruzando o scan Modbus
(scan_modbus_20260721_175859.csv, 118 registradores, 1 amostra/min entre
17:59 e 19:50) com 9 leituras fotografadas da IHM ABB CP604.

Observação sobre tipos: o scanner classificou a maioria destes endereços
como DINT32_*_PALAVRA_n, REAL32_* ou BYTE/ENUM. Nenhuma dessas hipóteses
se confirmou. O maior valor observado em toda a série é 2928 e o vizinho
que seria a "palavra alta" carrega outra grandeza (o 978, ao lado do 977,
é a tensão). Todos os sinais abaixo são holding registers de 16 bits com
escala decimal implícita, lidos pela função 03.
"""

from __future__ import annotations
import struct
from pymodbus.client import ModbusTcpClient

__all__ = ["ler_dados_clp", "abrir_conexao", "ler_dados", "SINAIS"]


# -----------------------------------------------------------------------------
# Conexão
# -----------------------------------------------------------------------------
CLP_IP = "192.168.0.35"
CLP_PORT = 502
SOURCE_IP = "192.168.0.36"  # IP Ethernet do computador
TIMEOUT = 5.0


# nome: (registrador, tipo, escala, valor mínimo, valor máximo)
#
# Confiança do mapeamento:
#   ALTA   - bate nos 9 pontos da IHM (grandezas de variação lenta)
#   MÉDIA  - correlação da série completa > 0.99, mas a grandeza varia
#            rápido demais para casar ponto a ponto com amostragem de
#            1 minuto; a identificação é segura, os valores instantâneos
#            é que não conferem exatamente
SINAIS = {
    # --- Temperatura do stack -----------------------------------------------
    "stack_1_temperature": (316, "i16", 1.0, -50.0, 300.0),   # ALTA

    # --- Água ---------------------------------------------------------------
    "water_temperature": (526, "i16", 0.01, 0.0, 100.0),      # ALTA
    "water_conductivity": (338, "i16", 0.1, 0.0, 20.0),       # ALTA
    "aim_water_volume": (586, "i16", 0.1, 0.0, 200.0),        # MÉDIA
    "h2o_flow": (582, "i16", 0.1, 0.0, 20.0),                 # ALTA

    # --- Colunas de secagem -------------------------------------------------
    "a_column_temperature": (333, "i16", 1.0, -50.0, 300.0),  # ALTA
    "b_column_temperature": (334, "i16", 1.0, -50.0, 300.0),  # ALTA
    "dryer_cycle": (339, "i16", 1.0, 0.0, 300.0),             # ALTA (n/300)

    # --- Pressões -----------------------------------------------------------
    # 314 = pressão da linha principal (a que a IHM mostra no topo, ~28 bar).
    # 435 = pressão de H2 na saída (o "H2 x,xx bar" do canto direito).
    "aim_tank_pressure": (314, "i16", 0.01, 0.0, 50.0),       # MÉDIA
    "h2_pressure": (435, "i16", 0.01, 0.0, 50.0),             # MÉDIA

    # --- Elétricos ----------------------------------------------------------
    "stack_voltage": (589, "i16", 0.1, 0.0, 100.0),           # ALTA
    "stack_current": (977, "i16", 0.1, 0.0, 100.0),           # MÉDIA
    "stack_load": (1057, "i16", 1.0, 0.0, 100.0),             # ALTA (%)

    # --- Bomba --------------------------------------------------------------
    "pump_speed": (359, "i16", 1.0, 0.0, 100.0),              # ALTA (%)
}


# Endereços redundantes confirmados, caso algum dos principais falhe.
# As chaves seguem exatamente as de SINAIS.
REDUNDANTES = {
    "water_conductivity": 596,
    "water_temperature": 597,      # versão arredondada em 1 °C do 526
    "aim_water_volume": 354,
    "h2o_flow": 315,
    "a_column_temperature": 593,
    "b_column_temperature": 594,
    "dryer_cycle": 335,            # e 605
    "stack_voltage": 500,          # e 328, 978
    "stack_current": 590,          # e 343, 501
    "aim_tank_pressure": 580,      # e 996, 1051
    "h2_pressure": 581,            # e 1052
}


# Somente os blocos necessários para os sinais acima.
# Formato: (registrador inicial, quantidade)
#
# ATENÇÃO ao editar SINAIS: todo registrador precisa cair dentro de um bloco,
# senão _decodificar levanta RuntimeError. Use validar_blocos() para conferir.
BLOCOS_LEITURA = (
    (314, 46),   # 314 a 359: pressão HP, temp. stack, colunas A/B, contador,
                 #            condutividade, bomba
    (435, 1),    # 435: pressão de H2 na saída
    (526, 64),   # 526 a 589: temp. da água, vazão, volume, tensão
    (977, 1),    # 977: corrente
    (1057, 1),   # 1057: carga do stack
)


def validar_blocos() -> list[str]:
    """Retorna os sinais cujo registrador não está coberto por BLOCOS_LEITURA."""
    cobertos: set[int] = set()
    for inicio, quantidade in BLOCOS_LEITURA:
        cobertos.update(range(inicio, inicio + quantidade))

    return [
        f"{nome} (registrador {cfg[0]})"
        for nome, cfg in SINAIS.items()
        if cfg[0] is not None and cfg[0] not in cobertos
    ]


def _i16(valor: int) -> int:
    """Converte unsigned 16 bits para signed 16 bits."""
    return valor if valor < 32768 else valor - 65536


def _f32_le(reg1: int, reg2: int) -> float:
    """Decodifica dois registradores como float32 little-endian."""
    return struct.unpack("<f", struct.pack("<HH", reg1, reg2))[0]


def _f32_be(reg1: int, reg2: int) -> float:
    """Decodifica dois registradores como float32 big-endian."""
    return struct.unpack(">f", struct.pack(">HH", reg1, reg2))[0]


def abrir_conexao() -> ModbusTcpClient:
    """Abre e devolve um cliente Modbus conectado.

    Quem chamar é responsável por fechar. Use isto quando for ler em laço,
    para não abrir um socket novo a cada amostra.
    """
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


# Mantido para compatibilidade com o código antigo.
_conectar = abrir_conexao


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
        elif tipo == "u16":
            bruto = float(registradores[reg])
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
            f"Registrador {erro.args[0]} não recebido do CLP. "
            f"Verifique BLOCOS_LEITURA (use validar_blocos())."
        ) from erro

    valor = bruto * escala
    valor = max(minimo, min(maximo, valor))
    return round(valor, 4)


def ler_dados(client: ModbusTcpClient) -> dict[str, float]:
    """Lê os sinais usando um cliente já conectado, sem fechá-lo."""
    registradores: dict[int, int] = {}

    for inicio, quantidade in BLOCOS_LEITURA:
        registradores.update(_ler_bloco(client, inicio, quantidade))

    return {
        nome: _decodificar(registradores, configuracao)
        for nome, configuracao in SINAIS.items()
    }


def ler_dados_clp() -> dict[str, float]:
    """Abre a conexão, lê os sinais e fecha.

    Conveniente para leituras avulsas. Em laço, prefira abrir_conexao()
    + ler_dados() para não reabrir o socket a cada amostra.
    """
    client = abrir_conexao()
    try:
        return ler_dados(client)
    finally:
        client.close()


if __name__ == "__main__":
    pendentes = validar_blocos()
    if pendentes:
        print("Sinais fora dos blocos de leitura:")
        for item in pendentes:
            print("  -", item)
    else:
        print("Todos os sinais estão cobertos pelos blocos de leitura.")
        for nome, valor in ler_dados_clp().items():
            print(f"  {nome:<22} {valor}")