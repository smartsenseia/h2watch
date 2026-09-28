# -*- coding: utf-8 -*-
"""Leitura da célula (segundo CLP) por Modbus RTU na porta serial.

Complementa o connection_clp.py: aquele lê o eletrolisador por Modbus TCP,
este lê os nove campos da célula que existem em Measurement mas não em
SINAIS.

Diferenças de propósito em relação ao connection_clp.py:
  - Valor fora da faixa vira None em vez de ser "grampeado", para que
    falha de sensor apareça como buraco no banco e não como medição
    plausível.
  - Falha em um bloco anula só os sinais daquele bloco; os demais seguem.
    Só quando TODOS os blocos falham é levantado ConnectionError, para o
    chamador reabrir a porta.
  - Os blocos de leitura são montados automaticamente a partir de
    SINAIS_CELULA, então não há BLOCOS_LEITURA para manter em sincronia.

PENDENTE: os registradores estão como None até o mapeamento ser feito.
Enquanto estiverem assim, ler_dados_celula() devolve tudo None sem tocar
na serial, então o módulo já pode ser integrado ao coletor com segurança.
Para levantar o mapa, use o modo de varredura:

    python connection_celula.py --scan 0 200
    python connection_celula.py --scan 0 200 --csv scan_celula.csv \\
        --intervalo 60 --amostras 120

Dependências: pip install pymodbus pyserial
"""

from __future__ import annotations

import argparse
import csv
import inspect
import logging
import struct
import time
from datetime import datetime, timezone

from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

__all__ = [
    "SINAIS_CELULA",
    "CAMPOS_CELULA",
    "BLOCOS_CELULA",
    "abrir_conexao_celula",
    "ler_dados_celula",
    "ler_dados_celula_avulso",
    "sinais_pendentes",
    "varrer",
]

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------
# Porta serial (confira na IHM ou no manual do CLP da célula)
# -----------------------------------------------------------------------------
PORTA = "/dev/ttyUSB0"      # no Windows, algo como "COM3"
BAUDRATE = 9600
PARIDADE = "N"              # "N" (nenhuma), "E" (par) ou "O" (ímpar)
BITS_DADOS = 8
BITS_PARADA = 1
TIMEOUT = 1.0               # s; RTU responde rápido, timeout longo só atrasa
ID_ESCRAVO = 1              # endereço Modbus do CLP no barramento
FUNCAO = 3                  # 3 = holding registers, 4 = input registers


# -----------------------------------------------------------------------------
# Mapa de sinais
# -----------------------------------------------------------------------------
# nome: (registrador, tipo, escala, valor mínimo, valor máximo)
#
# As chaves são exatamente os nomes das colunas de Measurement, inclusive
# o "F" maiúsculo de Fan_pwm_celula. Se renomear no model, renomeie aqui.
#
# Tipos aceitos:
#   i16, u16                  1 registrador
#   i32be, u32be, f32be       2 registradores, palavra alta primeiro (ABCD)
#   i32le, u32le, f32le       2 registradores, palavra baixa primeiro (CDAB)
#
# Atenção: aqui "le" troca só a ordem das PALAVRAS, que é o caso comum em
# CLPs. No connection_clp.py, _f32_le inverte também os bytes de cada
# palavra. Não são equivalentes.
#
# Escalas, faixas e unidades abaixo são PALPITES até o mapeamento.
SINAIS_CELULA: dict[str, tuple] = {
    "tensao_celula":            (None, "i16",   0.1,   0.0,   100.0),   # V
    "corrente_celula":          (None, "i16",   0.1,   0.0,   100.0),   # A
    "tempo_de_operacao_celula": (None, "u32be", 1.0,   0.0,   1.0e7),   # h? s?
    "conc_co2_celula":          (None, "u16",   1.0,   0.0,   10000.0), # ppm?
    "Fan_pwm_celula":           (None, "u16",   1.0,   0.0,   100.0),   # %
    "fc_temperatura":           (None, "i16",   0.1,  -20.0,  120.0),   # °C
    "tensao_bateria_celula":    (None, "i16",   0.01,  0.0,   60.0),    # V
    "tensao_fc_celula":         (None, "i16",   0.1,   0.0,   100.0),   # V
    "corrente_fc_celula":       (None, "i16",   0.1,   0.0,   100.0),   # A
}

CAMPOS_CELULA: tuple[str, ...] = tuple(SINAIS_CELULA)

_LARGURA = {
    "i16": 1, "u16": 1,
    "i32be": 2, "u32be": 2, "f32be": 2,
    "i32le": 2, "u32le": 2, "f32le": 2,
}
_FORMATO_32 = {"i32": ">i", "u32": ">I", "f32": ">f"}

# Montagem dos blocos: registradores próximos são lidos numa só requisição.
# Em RTU cada requisição custa um ida-e-volta na serial, então vale juntar
# mesmo com alguns registradores sobrando no meio.
MAX_REGS_POR_LEITURA = 60   # o protocolo permite até 125
MAX_BURACO = 8              # junta blocos separados por até 8 registradores


def _validar_config() -> None:
    """Falha na importação se o mapa tiver tipo ou faixa inválidos."""
    for nome, (reg, tipo, escala, minimo, maximo) in SINAIS_CELULA.items():
        if tipo not in _LARGURA:
            raise ValueError(f"{nome}: tipo Modbus desconhecido {tipo!r}")
        if minimo >= maximo:
            raise ValueError(f"{nome}: mínimo {minimo} >= máximo {maximo}")
        if escala == 0:
            raise ValueError(f"{nome}: escala zero")
        if reg is not None and not (0 <= reg <= 65535):
            raise ValueError(f"{nome}: registrador {reg} fora de 0..65535")


def _montar_blocos() -> tuple[tuple[int, int], ...]:
    """Agrupa os registradores de SINAIS_CELULA em (início, quantidade)."""
    intervalos = sorted(
        (reg, reg + _LARGURA[tipo] - 1)
        for reg, tipo, *_ in SINAIS_CELULA.values()
        if reg is not None
    )

    blocos: list[list[int]] = []
    for inicio, fim in intervalos:
        if blocos:
            b_inicio, b_fim = blocos[-1]
            perto = inicio <= b_fim + 1 + MAX_BURACO
            cabe = max(b_fim, fim) - b_inicio + 1 <= MAX_REGS_POR_LEITURA
            if perto and cabe:
                blocos[-1][1] = max(b_fim, fim)
                continue
        blocos.append([inicio, fim])

    return tuple((inicio, fim - inicio + 1) for inicio, fim in blocos)


_validar_config()
BLOCOS_CELULA = _montar_blocos()


def sinais_pendentes() -> list[str]:
    """Sinais ainda sem registrador definido."""
    return [nome for nome, cfg in SINAIS_CELULA.items() if cfg[0] is None]


# -----------------------------------------------------------------------------
# Conexão e leitura
# -----------------------------------------------------------------------------
def abrir_conexao_celula(
    porta: str | None = None,
    baudrate: int | None = None,
) -> ModbusSerialClient:
    """Abre e devolve o cliente serial conectado. Quem chamar fecha."""
    porta = porta or PORTA
    baudrate = baudrate or BAUDRATE

    client = ModbusSerialClient(
        port=porta,
        baudrate=baudrate,
        parity=PARIDADE,
        bytesize=BITS_DADOS,
        stopbits=BITS_PARADA,
        timeout=TIMEOUT,
    )

    if not client.connect():
        client.close()
        raise ConnectionError(
            f"Falha ao abrir a porta serial {porta} "
            f"({baudrate} {BITS_DADOS}{PARIDADE}{BITS_PARADA})."
        )

    return client


def _kw_escravo(metodo, id_escravo: int) -> dict:
    """Nome do argumento do ID do escravo muda entre versões do pymodbus.

    3.9+ usa device_id, 3.x anteriores usam slave, 2.x usava unit.
    """
    parametros = inspect.signature(metodo).parameters
    for nome in ("device_id", "slave", "unit"):
        if nome in parametros:
            return {nome: id_escravo}
    return {}


def _ler_bloco(
    client: ModbusSerialClient,
    inicio: int,
    quantidade: int,
    id_escravo: int | None = None,
) -> dict[int, int]:
    metodo = (
        client.read_holding_registers if FUNCAO == 3
        else client.read_input_registers
    )
    kw = _kw_escravo(metodo, id_escravo if id_escravo is not None else ID_ESCRAVO)
    resposta = metodo(inicio, count=quantidade, **kw)

    fim = inicio + quantidade - 1
    if resposta is None or resposta.isError():
        raise RuntimeError(
            f"Falha na leitura Modbus RTU dos registradores {inicio} a {fim}: "
            f"{resposta}"
        )
    if len(resposta.registers) != quantidade:
        raise RuntimeError(
            f"Leitura incompleta a partir do registrador {inicio}: "
            f"esperados {quantidade}, recebidos {len(resposta.registers)}."
        )

    return {inicio + i: v for i, v in enumerate(resposta.registers)}


def _decodificar(registradores: dict[int, int], cfg: tuple) -> float | None:
    """Converte o valor bruto; devolve None se ausente ou fora da faixa."""
    reg, tipo, escala, minimo, maximo = cfg
    if reg is None:
        return None

    try:
        palavras = [registradores[reg + i] for i in range(_LARGURA[tipo])]
    except KeyError:
        return None  # bloco que continha este registrador falhou

    if tipo == "u16":
        bruto = palavras[0]
    elif tipo == "i16":
        bruto = struct.unpack(">h", struct.pack(">H", palavras[0]))[0]
    else:
        ordem = palavras if tipo.endswith("be") else palavras[::-1]
        bruto = struct.unpack(_FORMATO_32[tipo[:3]], struct.pack(">HH", *ordem))[0]

    valor = bruto * escala
    if valor != valor or not (minimo <= valor <= maximo):  # NaN ou fora
        return None
    return round(valor, 4)


def ler_dados_celula(client: ModbusSerialClient) -> dict[str, float | None]:
    """Lê os sinais da célula com um cliente já aberto, sem fechá-lo.

    Sempre devolve todas as chaves de CAMPOS_CELULA. Sinais sem mapa, de
    blocos que falharam ou fora da faixa vêm como None. Se todos os blocos
    falharem, levanta ConnectionError para o chamador reabrir a porta.
    """
    registradores: dict[int, int] = {}
    falhas: list[str] = []

    for inicio, quantidade in BLOCOS_CELULA:
        try:
            registradores.update(_ler_bloco(client, inicio, quantidade))
        except (RuntimeError, OSError, ModbusException) as erro:
            falhas.append(str(erro))

    if BLOCOS_CELULA and len(falhas) == len(BLOCOS_CELULA):
        raise ConnectionError(
            "Nenhum bloco da célula respondeu: " + " | ".join(falhas)
        )
    for falha in falhas:
        log.warning("Célula, leitura parcial: %s", falha)

    return {
        nome: _decodificar(registradores, cfg)
        for nome, cfg in SINAIS_CELULA.items()
    }


def ler_dados_celula_avulso() -> dict[str, float | None]:
    """Abre a porta, lê e fecha. Em laço, prefira abrir uma vez só."""
    if not BLOCOS_CELULA:
        return {nome: None for nome in CAMPOS_CELULA}
    client = abrir_conexao_celula()
    try:
        return ler_dados_celula(client)
    finally:
        client.close()


# -----------------------------------------------------------------------------
# Varredura, para levantar o mapa de registradores
# -----------------------------------------------------------------------------
def varrer(
    client: ModbusSerialClient,
    inicio: int,
    fim: int,
    tamanho: int = 10,
    id_escravo: int | None = None,
) -> dict[int, int | None]:
    """Lê de inicio a fim (inclusive). Registrador recusado vira None.

    Lê em blocos; se o CLP recusar um bloco (endereço ilegal no meio),
    tenta registrador por registrador para salvar os que existem.
    """
    resultado: dict[int, int | None] = {}
    for bloco_inicio in range(inicio, fim + 1, tamanho):
        qtd = min(tamanho, fim - bloco_inicio + 1)
        try:
            resultado.update(_ler_bloco(client, bloco_inicio, qtd, id_escravo))
        except (RuntimeError, OSError, ModbusException):
            for reg in range(bloco_inicio, bloco_inicio + qtd):
                try:
                    resultado.update(_ler_bloco(client, reg, 1, id_escravo))
                except (RuntimeError, OSError, ModbusException):
                    resultado[reg] = None
    return resultado


def _imprimir_varredura(valores: dict[int, int | None]) -> None:
    print(f"{'reg':>6} {'u16':>6} {'i16':>7}")
    for reg, v in sorted(valores.items()):
        if v is None:
            continue
        i16 = v - 65536 if v >= 32768 else v
        print(f"{reg:>6} {v:>6} {i16:>7}")
    recusados = sum(1 for v in valores.values() if v is None)
    if recusados:
        print(f"({recusados} registradores recusados pelo CLP)")


def _main() -> None:
    parser = argparse.ArgumentParser(description="Leitura serial da célula.")
    parser.add_argument("--porta", default=None, help=f"padrão {PORTA}")
    parser.add_argument("--baud", type=int, default=None, help=f"padrão {BAUDRATE}")
    parser.add_argument("--escravo", type=int, default=None,
                        help=f"ID Modbus, padrão {ID_ESCRAVO}")
    parser.add_argument("--scan", nargs=2, type=int, metavar=("INICIO", "FIM"),
                        help="varre registradores em vez de ler os sinais")
    parser.add_argument("--csv", help="grava a varredura neste CSV (1 linha por amostra)")
    parser.add_argument("--intervalo", type=float, default=60.0,
                        help="segundos entre amostras da varredura (padrão 60)")
    parser.add_argument("--amostras", type=int, default=1,
                        help="quantas amostras de varredura (padrão 1)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if not args.scan:
        pendentes = sinais_pendentes()
        if pendentes:
            print("Sinais ainda sem registrador:")
            for nome in pendentes:
                print("  -", nome)
            if not BLOCOS_CELULA:
                print("Nada para ler. Use --scan para levantar o mapa.")
                return
        client = abrir_conexao_celula(args.porta, args.baud)
        try:
            for nome, valor in ler_dados_celula(client).items():
                print(f"  {nome:<26} {valor}")
        finally:
            client.close()
        return

    inicio, fim = args.scan
    client = abrir_conexao_celula(args.porta, args.baud)
    arquivo = None
    try:
        escritor = None
        if args.csv:
            arquivo = open(args.csv, "a", newline="", encoding="utf-8")
            escritor = csv.writer(arquivo)
            if arquivo.tell() == 0:
                escritor.writerow(["timestamp", *range(inicio, fim + 1)])

        for n in range(args.amostras):
            t0 = time.monotonic()
            valores = varrer(client, inicio, fim, id_escravo=args.escravo)
            agora = datetime.now(timezone.utc).isoformat()

            if escritor:
                escritor.writerow([agora, *(
                    "" if valores.get(r) is None else valores[r]
                    for r in range(inicio, fim + 1)
                )])
                arquivo.flush()
                validos = sum(v is not None for v in valores.values())
                print(f"[{n + 1}/{args.amostras}] {agora}: {validos} registradores")
            else:
                print(f"--- {agora}")
                _imprimir_varredura(valores)

            if n + 1 < args.amostras:
                time.sleep(max(0.0, args.intervalo - (time.monotonic() - t0)))
    except KeyboardInterrupt:
        print("\nEncerrando.")
    finally:
        client.close()
        if arquivo:
            arquivo.close()


if __name__ == "__main__":
    _main()