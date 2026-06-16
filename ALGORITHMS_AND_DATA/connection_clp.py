import snap7
from snap7.util import get_int


# -----------------------------
# Conversões equivalentes ao PLC
# -----------------------------

def norm(raw):
    return raw / 27648


def scale(norm_val, eng_min, eng_max):
    return eng_min + norm_val * (eng_max - eng_min)


def convert(raw, eng_min, eng_max):
    return scale(norm(raw), eng_min, eng_max)


# -----------------------------
# Ranges físicos
# -----------------------------

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


# -----------------------------
# Conexão PLC
# -----------------------------

PLC_IP = "192.168.0.10"
DB_NUMBER = 7

plc = snap7.client.Client()
plc.connect(PLC_IP, 0, 1)


# -----------------------------
# Função principal de leitura
# -----------------------------

def ler_dados_clp():

    data = plc.db_read(DB_NUMBER, 0, 46)

    # Temperaturas

    TI01 = convert(get_int(data,0), TEMP_MIN, TEMP_MAX)
    TI02 = convert(get_int(data,2), TEMP_MIN, TEMP_MAX)
    TI03 = convert(get_int(data,4), TEMP_MIN, TEMP_MAX)
    TI04 = convert(get_int(data,6), TEMP_MIN, TEMP_MAX)
    TI05 = convert(get_int(data,8), TEMP_MIN, TEMP_MAX)
    TI06 = convert(get_int(data,10), TEMP_MIN, TEMP_MAX)
    TI07 = convert(get_int(data,12), TEMP_MIN, TEMP_MAX)
    TI08 = convert(get_int(data,14), TEMP_MIN, TEMP_MAX)
    TI09 = convert(get_int(data,16), TEMP_MIN, TEMP_MAX)
    TI10 = convert(get_int(data,18), TEMP_MIN, TEMP_MAX)

    TI_A = convert(get_int(data,20), TEMP_MIN, TEMP_MAX)
    TI_B = convert(get_int(data,22), TEMP_MIN, TEMP_MAX)

    TI11 = convert(get_int(data,42), TEMP_MIN, TEMP_MAX)

    # Vazões

    FI01 = convert(get_int(data,24), FLOW_MIN, FLOW_MAX)
    FI02 = convert(get_int(data,26), FLOW_MIN, FLOW_MAX)
    FI03 = convert(get_int(data,28), FLOW_MIN, FLOW_MAX)
    FI04 = convert(get_int(data,30), FLOW_MIN, FLOW_MAX)

    # Pressões

    PI01 = convert(get_int(data,32), PI01_MIN, PI01_MAX)
    PI02 = convert(get_int(data,34), PI02_MIN, PI02_MAX)
    PI03 = convert(get_int(data,36), PI03_MIN, PI03_MAX)
    PI04 = convert(get_int(data,38), PI04_MIN, PI04_MAX)
    PI05 = convert(get_int(data,44), PI05_MIN, PI05_MAX)

    # Válvula

    VALVULA_RAW = get_int(data,40)
    VALVULA = (VALVULA_RAW / 27648) * 100

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
            "TI11": TI11
        },

        "pressoes": {
            "PI01": PI01,
            "PI02": PI02,
            "PI03": PI03,
            "PI04": PI04,
            "PI05": PI05
        },

        "vazoes": {
            "FI01": FI01,
            "FI02": FI02,
            "FI03": FI03,
            "FI04": FI04
        },

        "valvula": VALVULA

    }