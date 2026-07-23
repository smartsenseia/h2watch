# -*- coding: utf-8 -*-
"""
Scanner contínuo de holding registers para ABB AC500.

O programa:
- conecta ao CLP somente para leitura;
- monitora continuamente as faixas configuradas;
- registra somente os endereços cujo valor mudou;
- estima o tipo de dado de cada registrador;
- salva tudo em um único arquivo CSV.

Colunas do CSV:
    dia
    hora_minuto
    registrador
    tipo_estimado
    valor_clp

O valor salvo em valor_clp é a palavra bruta de 16 bits recebida do CLP,
sem aplicação de escala.

Encerramento seguro:
    Ctrl+C
"""

from __future__ import annotations

import csv
import math
import socket
import statistics
import struct
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from pymodbus.client import ModbusTcpClient


# =============================================================================
# CONFIGURAÇÃO DA CONEXÃO
# =============================================================================

CLP_IP = "192.168.0.35"
CLP_PORT = 502

# Endereço Ethernet local do computador.
SOURCE_IP = "192.168.0.36"


# Identificador lógico Modbus. Em muitos dispositivos Modbus TCP é 1.
DEVICE_ID = 1

TIMEOUT = 3.0
RECONNECT_DELAY = 5.0


# =============================================================================
# CONFIGURAÇÃO DO SCAN
# =============================================================================

# Cada tupla é:
#     (endereço inicial, endereço final exclusivo)
#
# A faixa padrão 0–1199 cobre todos os registradores que apareceram no seu
# mapeamento atual, incluindo 6, 506, 526, 580–586, 681–689 e 1008–1011.
#
# Para varrer toda a faixa teórica Modbus:
#     SCAN_RANGES = ((0, 65536),)
#
# ATENÇÃO: a varredura 0–65535 gera centenas de requisições por ciclo, pode ser
# lenta e pode aumentar muito a carga de comunicação do CLP. Comece com 0–1200.
SCAN_RANGES: tuple[tuple[int, int], ...] = (
    (0, 1200),
)

# O protocolo permite blocos de holding registers. O limite normal é 125.
# Um bloco menor reduz o impacto quando uma região retorna erro.
BLOCK_SIZE = 100

# Pausa entre requisições Modbus consecutivas.
REQUEST_DELAY_SECONDS = 1

# Pausa após terminar uma varredura completa.
SWEEP_DELAY_SECONDS = 1

# Intervalo para regravar o arquivo com o estado atual.
CURRENT_SNAPSHOT_INTERVAL_SECONDS = 30.0

# Mostra cada mudança no terminal.
PRINT_CHANGES = True

# Se True, ignora mudanças entre valores que oscilam apenas dentro dessa
# tolerância. Como holding registers são inteiros, o padrão correto é zero.
MIN_RAW_CHANGE = 0

# Diretório dos arquivos de saída.
OUTPUT_DIR = Path("monitor_modbus")


# =============================================================================
# CONFIGURAÇÃO DA ESTIMATIVA DE TIPOS
# =============================================================================

# Quantidade máxima de amostras recentes guardadas para cada registrador.
TYPE_HISTORY_LENGTH = 600

# Quantidade mínima de amostras antes de confiar melhor na estimativa.
MIN_TYPE_SAMPLES = 20

# Pontuação mínima para considerar dois registradores consecutivos como
# uma variável de 32 bits.
PAIR_CONFIDENCE_THRESHOLD = 0.78


# =============================================================================
# ESTRUTURAS DE DADOS
# =============================================================================

@dataclass
class RegisterStats:
    """Estatísticas acumuladas de um registrador que apresentou alteração."""

    register: int
    first_value: int
    last_value: int
    minimum: int
    maximum: int
    change_count: int
    first_seen: str
    first_change: str
    last_change: str

    def update(self, previous: int, current: int, timestamp: str) -> None:
        self.last_value = current
        self.minimum = min(self.minimum, current)
        self.maximum = max(self.maximum, current)
        self.change_count += 1
        self.last_change = timestamp


# =============================================================================
# CONVERSÕES DE EXIBIÇÃO
# =============================================================================

def to_i16(value: int) -> int:
    """Interpreta uma palavra unsigned de 16 bits como INT16."""
    return value if value < 32768 else value - 65536


def to_hex(value: int) -> str:
    """Representação hexadecimal da palavra Modbus."""
    return f"0x{value & 0xFFFF:04X}"


def to_binary(value: int) -> str:
    """Representação binária com 16 bits."""
    return f"{value & 0xFFFF:016b}"


def local_computer_time() -> datetime:
    """Retorna a data/hora local do computador com informação de fuso."""
    return datetime.now().astimezone()


def timestamp_now() -> str:
    """Data/hora local do computador em ISO 8601, incluindo o fuso."""
    return local_computer_time().isoformat(
        sep=" ",
        timespec="milliseconds",
    )


# =============================================================================
# CONEXÃO MODBUS
# =============================================================================

def port_open(timeout: float = 2.0) -> bool:
    """Verifica se a porta TCP responde antes de abrir o cliente Modbus."""
    try:
        with socket.create_connection(
            (CLP_IP, CLP_PORT),
            timeout=timeout,
            source_address=(SOURCE_IP, 0),
        ):
            return True
    except OSError:
        return False


def create_client() -> ModbusTcpClient:
    """Cria o cliente usando a interface Ethernet definida em SOURCE_IP."""
    return ModbusTcpClient(
        host=CLP_IP,
        port=CLP_PORT,
        timeout=TIMEOUT,
        retries=1,
        source_address=(SOURCE_IP, 0),
    )


def connect_forever() -> ModbusTcpClient:
    """
    Tenta conectar continuamente.

    Ctrl+C continua funcionando durante as tentativas.
    """
    while True:
        client = create_client()

        try:
            if not port_open():
                raise ConnectionError(
                    f"Porta {CLP_IP}:{CLP_PORT} não respondeu."
                )

            if client.connect():
                print(
                    f"[{timestamp_now()}] Conectado ao CLP "
                    f"{CLP_IP}:{CLP_PORT} pela interface {SOURCE_IP}."
                )
                return client

            raise ConnectionError("client.connect() retornou False.")

        except KeyboardInterrupt:
            client.close()
            raise

        except Exception as error:
            client.close()
            print(
                f"[{timestamp_now()}] Falha de conexão: {error}\n"
                f"Nova tentativa em {RECONNECT_DELAY:.1f} s..."
            )
            time.sleep(RECONNECT_DELAY)


def read_holding_block(
    client: ModbusTcpClient,
    start: int,
    count: int,
) -> Optional[list[int]]:
    """
    Lê um bloco de holding registers.

    Compatível com versões do PyModbus que usam:
        device_id=...
    e versões anteriores que usam:
        slave=...
    """
    try:
        try:
            response = client.read_holding_registers(
                start,
                count=count,
                device_id=DEVICE_ID,
            )
        except TypeError:
            response = client.read_holding_registers(
                start,
                count=count,
                slave=DEVICE_ID,
            )

    except Exception:
        return None

    if response is None or response.isError():
        return None

    registers = getattr(response, "registers", None)

    if registers is None or len(registers) != count:
        return None

    return [int(value) & 0xFFFF for value in registers]



# =============================================================================
# ESTIMATIVA HEURÍSTICA DOS TIPOS
# =============================================================================

def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _variation_score(values: list[float]) -> float:
    """Pontuação de quantidade de variação observada."""
    if len(values) < 2:
        return 0.0

    unique = len(set(values))

    if unique <= 1:
        return 0.0

    return _clamp01(unique / min(len(values), 20))


def _smoothness_score(values: list[float]) -> float:
    """
    Mede continuidade temporal.

    Próximo de 1 indica mudanças pequenas em relação à faixa observada.
    """
    finite = [value for value in values if math.isfinite(value)]

    if len(finite) < 3:
        return 0.25

    ordered = sorted(finite)
    p05 = ordered[int((len(ordered) - 1) * 0.05)]
    p95 = ordered[int((len(ordered) - 1) * 0.95)]
    observed_range = abs(p95 - p05)

    typical_magnitude = statistics.median(
        abs(value) for value in finite
    )

    scale = max(observed_range, typical_magnitude * 0.10, 1.0)

    differences = [
        abs(current - previous)
        for previous, current in zip(finite, finite[1:])
    ]

    median_difference = (
        statistics.median(differences)
        if differences
        else 0.0
    )

    return _clamp01(
        1.0 / (1.0 + 5.0 * median_difference / scale)
    )


def _monotonic_fraction(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0

    differences = [
        current - previous
        for previous, current in zip(values, values[1:])
        if current != previous
    ]

    if not differences:
        return 0.0

    increasing = sum(value > 0 for value in differences)
    decreasing = sum(value < 0 for value in differences)

    return max(increasing, decreasing) / len(differences)


def _bit_transition_score(values: list[int]) -> float:
    """
    Verifica se cada alteração modifica poucos bits.

    Isso é comum em flags, ENUMs pequenos e bitfields.
    """
    transitions = [
        (previous ^ current).bit_count()
        for previous, current in zip(values, values[1:])
        if previous != current
    ]

    if not transitions:
        return 0.0

    return (
        sum(bits <= 2 for bits in transitions)
        / len(transitions)
    )


def _single_register_guess(values: list[int]) -> dict[str, object]:
    """Estima tipos de 16 bits para um registrador isolado."""
    if not values:
        return {
            "type": "SEM_DADOS",
            "confidence": 0.0,
            "evidence": "Nenhuma amostra válida.",
        }

    unique = sorted(set(values))
    changed = len(unique) > 1
    sample_count = len(values)
    minimum = min(values)
    maximum = max(values)

    if set(unique).issubset({0, 1}):
        return {
            "type": "BOOL",
            "confidence": 0.97 if changed else 0.55,
            "evidence": (
                f"Somente 0 e 1 em {sample_count} amostras."
            ),
        }

    bit_score = _bit_transition_score(values)

    if (
        maximum <= 255
        and len(unique) <= 32
        and bit_score >= 0.70
    ):
        return {
            "type": "BYTE/ENUM/BITFIELD",
            "confidence": 0.82 if changed else 0.45,
            "evidence": (
                f"Faixa 0..255; {len(unique)} valores distintos; "
                f"{bit_score:.0%} das transições alteraram até 2 bits."
            ),
        }

    unsigned_values = [float(value) for value in values]
    signed_values = [float(to_i16(value)) for value in values]

    monotonic = _monotonic_fraction(unsigned_values)
    has_high_bit = any(value >= 32768 for value in values)

    if not has_high_bit:
        if changed and monotonic >= 0.90:
            return {
                "type": "UINT16/CONTADOR ou INT16_POSITIVO",
                "confidence": 0.64,
                "evidence": (
                    f"Série {monotonic:.0%} monotônica. Como todos os "
                    "valores são menores que 32768, INT16 e UINT16 são "
                    "numericamente iguais."
                ),
            }

        return {
            "type": "INT16/UINT16_AMBIGUO",
            "confidence": 0.55 if changed else 0.28,
            "evidence": (
                "Todos os valores estão entre 0 e 32767; nessa faixa "
                "não é possível distinguir INT16 de UINT16 pelos dados."
            ),
        }

    signed_smooth = _smoothness_score(signed_values)
    unsigned_smooth = _smoothness_score(unsigned_values)

    signed_magnitude = statistics.median(
        abs(value) for value in signed_values
    )
    unsigned_magnitude = statistics.median(
        abs(value) for value in unsigned_values
    )

    signed_advantage = (
        signed_smooth
        - unsigned_smooth
        + 0.30
        * _clamp01(
            (unsigned_magnitude - signed_magnitude)
            / max(unsigned_magnitude, 1.0)
        )
    )

    if signed_advantage > 0.15:
        return {
            "type": "INT16",
            "confidence": _clamp01(
                0.62 + signed_advantage * 0.35
            ),
            "evidence": (
                "O bit de sinal aparece ativo e a interpretação INT16 "
                "produz uma série mais compacta/contínua."
            ),
        }

    if signed_advantage < -0.15:
        return {
            "type": "UINT16",
            "confidence": _clamp01(
                0.62 + abs(signed_advantage) * 0.35
            ),
            "evidence": (
                "A interpretação UINT16 produz uma série mais "
                "contínua/plausível que INT16."
            ),
        }

    return {
        "type": "INT16/UINT16_AMBIGUO",
        "confidence": 0.45,
        "evidence": (
            "O histórico não separa com clareza INT16 de UINT16."
        ),
    }


def _pair_bytes(register_1: int, register_2: int) -> bytes:
    return (
        int(register_1 & 0xFFFF).to_bytes(2, "big")
        + int(register_2 & 0xFFFF).to_bytes(2, "big")
    )


def _reorder_bytes(raw: bytes, order: str) -> bytes:
    """
    Ordem original: A B C D.

    ABCD: ordem direta
    CDAB: troca das palavras de 16 bits
    BADC: troca dos bytes dentro de cada palavra
    DCBA: inversão completa
    """
    if order == "ABCD":
        return raw
    if order == "CDAB":
        return raw[2:4] + raw[0:2]
    if order == "BADC":
        return bytes((raw[1], raw[0], raw[3], raw[2]))
    if order == "DCBA":
        return raw[::-1]

    raise ValueError(f"Ordem desconhecida: {order}")


def _decode_real32(r1: int, r2: int, order: str) -> float:
    raw = _reorder_bytes(_pair_bytes(r1, r2), order)
    return struct.unpack(">f", raw)[0]


def _decode_int32(
    r1: int,
    r2: int,
    order: str,
    signed: bool,
) -> int:
    raw = _reorder_bytes(_pair_bytes(r1, r2), order)
    return int.from_bytes(raw, "big", signed=signed)


def _aligned_pair_values(
    history_1: deque[tuple[int, int]],
    history_2: deque[tuple[int, int]],
) -> tuple[list[int], list[int]]:
    """Alinha duas séries pelo número da varredura."""
    map_1 = dict(history_1)
    map_2 = dict(history_2)
    sweeps = sorted(map_1.keys() & map_2.keys())

    return (
        [map_1[sweep] for sweep in sweeps],
        [map_2[sweep] for sweep in sweeps],
    )


def _score_real32(values: list[float]) -> tuple[float, str]:
    if len(values) < MIN_TYPE_SAMPLES:
        return 0.0, "Poucas amostras."

    finite = [value for value in values if math.isfinite(value)]
    finite_ratio = len(finite) / len(values)

    if finite_ratio < 0.98:
        return 0.0, "Muitos NaN ou infinitos."

    nonzero = [abs(value) for value in finite if value != 0.0]

    if nonzero:
        plausible_ratio = sum(
            1e-7 <= value <= 1e9
            for value in nonzero
        ) / len(nonzero)

        tiny_ratio = sum(
            value < 1e-20
            for value in nonzero
        ) / len(nonzero)

        huge_ratio = sum(
            value > 1e15
            for value in nonzero
        ) / len(nonzero)
    else:
        plausible_ratio = 0.25
        tiny_ratio = 0.0
        huge_ratio = 0.0

    fractional_ratio = sum(
        not math.isclose(
            value,
            round(value),
            rel_tol=0.0,
            abs_tol=1e-5,
        )
        for value in finite
    ) / len(finite)

    smoothness = _smoothness_score(finite)
    variation = _variation_score(finite)

    score = (
        0.18 * finite_ratio
        + 0.28 * plausible_ratio
        + 0.24 * smoothness
        + 0.17 * fractional_ratio
        + 0.13 * variation
        - 0.35 * tiny_ratio
        - 0.35 * huge_ratio
    )

    if len(set(finite)) <= 1:
        score *= 0.55

    evidence = (
        f"finitos={finite_ratio:.0%}, "
        f"plausíveis={plausible_ratio:.0%}, "
        f"fracionários={fractional_ratio:.0%}, "
        f"continuidade={smoothness:.0%}, "
        f"variação={variation:.0%}"
    )

    return _clamp01(score), evidence


def _score_int32(
    decoded: list[int],
    high_word: list[int],
    low_word: list[int],
) -> tuple[float, str]:
    if len(decoded) < MIN_TYPE_SAMPLES:
        return 0.0, "Poucas amostras."

    numeric = [float(value) for value in decoded]

    smoothness = _smoothness_score(numeric)
    variation = _variation_score(numeric)
    monotonic = _monotonic_fraction(numeric)

    high_transitions = sum(
        current != previous
        for previous, current in zip(
            high_word,
            high_word[1:],
        )
    )

    low_transitions = sum(
        current != previous
        for previous, current in zip(
            low_word,
            low_word[1:],
        )
    )

    high_ratio = high_transitions / max(len(high_word) - 1, 1)
    low_ratio = low_transitions / max(len(low_word) - 1, 1)

    high_stability = _clamp01(
        1.0 - high_ratio / max(low_ratio + 0.05, 0.05)
    )

    score = (
        0.32 * smoothness
        + 0.20 * variation
        + 0.16 * monotonic
        + 0.20 * high_stability
        + 0.12
    )

    if len(set(decoded)) <= 1:
        score *= 0.50

    evidence = (
        f"continuidade={smoothness:.0%}, "
        f"variação={variation:.0%}, "
        f"monotonicidade={monotonic:.0%}, "
        f"palavra alta estável={high_stability:.0%}"
    )

    return _clamp01(score), evidence


def _best_pair_guess(
    register: int,
    histories: dict[int, deque[tuple[int, int]]],
) -> Optional[dict[str, object]]:
    """Procura a melhor hipótese de 32 bits iniciando em register."""
    next_register = register + 1

    if register not in histories or next_register not in histories:
        return None

    first_values, second_values = _aligned_pair_values(
        histories[register],
        histories[next_register],
    )

    if len(first_values) < MIN_TYPE_SAMPLES:
        return None

    candidates: list[dict[str, object]] = []

    for order in ("ABCD", "CDAB", "BADC", "DCBA"):
        try:
            decoded = [
                _decode_real32(r1, r2, order)
                for r1, r2 in zip(first_values, second_values)
            ]
        except (OverflowError, struct.error):
            continue

        score, evidence = _score_real32(decoded)
        finite = [
            value for value in decoded
            if math.isfinite(value)
        ]

        candidates.append(
            {
                "type": f"REAL32_{order}",
                "confidence": score,
                "byte_order": order,
                "evidence": evidence,
                "decoded_min": min(finite) if finite else None,
                "decoded_max": max(finite) if finite else None,
            }
        )

    for order in ("ABCD", "CDAB"):
        if order == "ABCD":
            high_word = first_values
            low_word = second_values
        else:
            high_word = second_values
            low_word = first_values

        for signed, name in (
            (True, "DINT32"),
            (False, "UDINT32"),
        ):
            decoded = [
                _decode_int32(
                    r1,
                    r2,
                    order,
                    signed=signed,
                )
                for r1, r2 in zip(first_values, second_values)
            ]

            score, evidence = _score_int32(
                decoded,
                high_word,
                low_word,
            )

            candidates.append(
                {
                    "type": f"{name}_{order}",
                    "confidence": score,
                    "byte_order": order,
                    "evidence": evidence,
                    "decoded_min": min(decoded),
                    "decoded_max": max(decoded),
                }
            )

    if not candidates:
        return None

    return max(
        candidates,
        key=lambda item: float(item["confidence"]),
    )


def _estimate_all_types(
    stats: dict[int, RegisterStats],
    histories: dict[int, deque[tuple[int, int]]],
) -> dict[int, dict[str, object]]:
    """
    Estima o tipo de cada registrador alterado.

    Pares de 32 bits fortes são selecionados sem sobreposição.
    """
    registers = sorted(stats)

    single_guesses: dict[int, dict[str, object]] = {}

    for register in registers:
        values = [
            value
            for _, value in histories.get(register, ())
        ]

        single_guesses[register] = _single_register_guess(values)

    pair_candidates: list[
        tuple[int, dict[str, object]]
    ] = []

    for register in registers:
        guess = _best_pair_guess(register, histories)

        if (
            guess is not None
            and float(guess["confidence"])
            >= PAIR_CONFIDENCE_THRESHOLD
        ):
            pair_candidates.append((register, guess))

    pair_candidates.sort(
        key=lambda item: float(item[1]["confidence"]),
        reverse=True,
    )

    estimates: dict[int, dict[str, object]] = {}
    occupied: set[int] = set()

    for register, pair_guess in pair_candidates:
        next_register = register + 1

        if register in occupied or next_register in occupied:
            continue

        first_single = single_guesses.get(
            register,
            {"confidence": 0.0},
        )
        second_single = single_guesses.get(
            next_register,
            {"confidence": 0.0},
        )

        required = max(
            PAIR_CONFIDENCE_THRESHOLD,
            float(first_single["confidence"]) + 0.10,
            float(second_single["confidence"]) + 0.10,
        )

        if float(pair_guess["confidence"]) < required:
            continue

        estimates[register] = {
            **pair_guess,
            "role": "PALAVRA_1_DE_2",
            "paired_register": next_register,
        }

        if next_register in stats:
            estimates[next_register] = {
                **pair_guess,
                "role": "PALAVRA_2_DE_2",
                "paired_register": register,
            }

        occupied.add(register)
        occupied.add(next_register)

    for register in registers:
        if register in estimates:
            continue

        guess = single_guesses[register]

        estimates[register] = {
            **guess,
            "role": "REGISTRADOR_16_BITS",
            "paired_register": "",
            "byte_order": "",
            "decoded_min": None,
            "decoded_max": None,
        }

    return estimates

# =============================================================================
# ÚNICO ARQUIVO CSV
# =============================================================================

CSV_HEADERS = [
    "dia",
    "hora_minuto",
    "registrador",
    "tipo_estimado",
    "valor_clp",
]


def _estimate_type_for_register(
    register: int,
    histories: dict[int, deque[tuple[int, int]]],
) -> str:
    """
    Estima o tipo do registrador usando o seu histórico e os registradores
    consecutivos.

    Quando houver uma hipótese forte de 32 bits, o texto informa se o endereço
    é a primeira ou a segunda palavra do valor.
    """
    values = [
        value
        for _, value in histories.get(register, ())
    ]

    single_guess = _single_register_guess(values)
    best_type = str(single_guess["type"])
    best_confidence = float(single_guess["confidence"])

    pair_options: list[tuple[float, str]] = []

    # Hipótese: o registrador atual é a primeira palavra de um valor de 32 bits.
    pair_starting_here = _best_pair_guess(register, histories)

    if pair_starting_here is not None:
        confidence = float(pair_starting_here["confidence"])

        if confidence >= PAIR_CONFIDENCE_THRESHOLD:
            pair_options.append(
                (
                    confidence,
                    f"{pair_starting_here['type']}_PALAVRA_1",
                )
            )

    # Hipótese: o registrador atual é a segunda palavra de um valor de 32 bits.
    pair_starting_before = _best_pair_guess(register - 1, histories)

    if pair_starting_before is not None:
        confidence = float(pair_starting_before["confidence"])

        if confidence >= PAIR_CONFIDENCE_THRESHOLD:
            pair_options.append(
                (
                    confidence,
                    f"{pair_starting_before['type']}_PALAVRA_2",
                )
            )

    if pair_options:
        pair_confidence, pair_type = max(
            pair_options,
            key=lambda item: item[0],
        )

        # Só troca a hipótese de 16 bits quando a hipótese do par é
        # significativamente mais forte.
        if pair_confidence >= best_confidence + 0.10:
            best_type = pair_type

    return best_type


def iter_blocks():
    """Produz blocos contínuos das faixas configuradas."""
    for range_start, range_end in SCAN_RANGES:
        if not 0 <= range_start < range_end <= 65536:
            raise ValueError(
                f"Faixa inválida: ({range_start}, {range_end}). "
                "Os endereços devem estar entre 0 e 65535."
            )

        start = range_start

        while start < range_end:
            count = min(BLOCK_SIZE, range_end - start)
            yield start, count
            start += count


def monitor() -> None:
    """
    Monitora os registradores continuamente e salva somente alterações.

    A primeira leitura de cada endereço estabelece a referência inicial e não
    é gravada como alteração.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    session = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = OUTPUT_DIR / f"scan_modbus_{session}.csv"

    previous_values: dict[int, int] = {}

    # Histórico de todas as leituras, necessário para estimar os tipos.
    histories: dict[int, deque[tuple[int, int]]] = {}

    sweep = 0
    total_changes = 0
    failed_blocks = 0

    client = connect_forever()

    with csv_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
        buffering=1,
    ) as csv_file:

        writer = csv.DictWriter(
            csv_file,
            fieldnames=CSV_HEADERS,
            delimiter=";",
        )
        writer.writeheader()
        csv_file.flush()

        print("\nMonitoramento iniciado.")
        print(f"Faixas monitoradas: {SCAN_RANGES}")
        print(f"Arquivo único: {csv_path}")
        print(
            "Somente registradores que mudarem serão gravados. "
            "Pressione Ctrl+C para encerrar.\n"
        )

        try:
            while True:
                sweep += 1
                sweep_changes = 0
                successful_blocks = 0

                for block_start, block_count in iter_blocks():
                    values = read_holding_block(
                        client,
                        block_start,
                        block_count,
                    )

                    if values is None:
                        failed_blocks += 1
                        time.sleep(REQUEST_DELAY_SECONDS)
                        continue

                    successful_blocks += 1

                    for offset, current in enumerate(values):
                        register = block_start + offset

                        history = histories.setdefault(
                            register,
                            deque(maxlen=TYPE_HISTORY_LENGTH),
                        )
                        history.append((sweep, current))

                        # Primeira leitura: cria a referência, mas não registra
                        # como alteração.
                        if register not in previous_values:
                            previous_values[register] = current
                            continue

                        previous = previous_values[register]

                        if abs(current - previous) <= MIN_RAW_CHANGE:
                            continue

                        computer_time = local_computer_time()
                        estimated_type = _estimate_type_for_register(
                            register,
                            histories,
                        )

                        writer.writerow(
                            {
                                "dia": computer_time.strftime("%Y-%m-%d"),
                                "hora_minuto": computer_time.strftime("%H:%M"),
                                "registrador": register,
                                "tipo_estimado": estimated_type,
                                "valor_clp": current,
                            }
                        )

                        # Entrega a linha ao sistema operacional imediatamente.
                        csv_file.flush()

                        previous_values[register] = current
                        sweep_changes += 1
                        total_changes += 1

                        if PRINT_CHANGES:
                            print(
                                f"[{computer_time.strftime('%Y-%m-%d %H:%M')}] "
                                f"reg {register:5d} | "
                                f"tipo {estimated_type:<35} | "
                                f"valor {current}"
                            )

                    time.sleep(REQUEST_DELAY_SECONDS)

                print(
                    f"[{timestamp_now()}] "
                    f"varredura={sweep} | "
                    f"registradores conhecidos={len(previous_values)} | "
                    f"alterações no ciclo={sweep_changes} | "
                    f"alterações acumuladas={total_changes} | "
                    f"blocos OK={successful_blocks}"
                )

                if successful_blocks == 0:
                    print(
                        f"[{timestamp_now()}] Nenhum bloco respondeu. "
                        "Reconectando..."
                    )
                    client.close()
                    time.sleep(RECONNECT_DELAY)
                    client = connect_forever()

                time.sleep(SWEEP_DELAY_SECONDS)

        except KeyboardInterrupt:
            print("\nInterrupção solicitada pelo usuário.")

        finally:
            client.close()
            csv_file.flush()

            print("\nMonitoramento encerrado.")
            print(f"Varreduras completas: {sweep}")
            print(f"Alterações registradas: {total_changes}")
            print(f"Blocos com falha: {failed_blocks}")
            print(f"Arquivo CSV: {csv_path}")


if __name__ == "__main__":
    monitor()