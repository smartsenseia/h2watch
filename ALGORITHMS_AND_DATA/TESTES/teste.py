import time
import snap7
from snap7.util import get_int


PLC_IP = "192.168.0.10"
RACK = 0
SLOT = 1
DB_NUMBER = 7
READ_START = 0
READ_SIZE = 46


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


def norm(raw):
    return raw / 27648.0


def scale(norm_val, eng_min, eng_max):
    return eng_min + norm_val * (eng_max - eng_min)


def convert(raw, eng_min, eng_max):
    return scale(norm(raw), eng_min, eng_max)


def conectar_clp():
    plc = snap7.client.Client()
    plc.connect(PLC_IP, RACK, SLOT)

    if not plc.get_connected():
        raise ConnectionError("Não foi possível conectar ao CLP.")

    print("Conectado ao CLP.")
    return plc


def ler_dados_clp(plc):
    data = plc.db_read(DB_NUMBER, READ_START, READ_SIZE)

    dados = {
        "temperaturas": {
            "TI01": convert(get_int(data, 0), TEMP_MIN, TEMP_MAX),
            "TI02": convert(get_int(data, 2), TEMP_MIN, TEMP_MAX),
            "TI03": convert(get_int(data, 4), TEMP_MIN, TEMP_MAX),
            "TI04": convert(get_int(data, 6), TEMP_MIN, TEMP_MAX),
            "TI05": convert(get_int(data, 8), TEMP_MIN, TEMP_MAX),
            "TI06": convert(get_int(data, 10), TEMP_MIN, TEMP_MAX),
            "TI07": convert(get_int(data, 12), TEMP_MIN, TEMP_MAX),
            "TI08": convert(get_int(data, 14), TEMP_MIN, TEMP_MAX),
            "TI09": convert(get_int(data, 16), TEMP_MIN, TEMP_MAX),
            "TI10": convert(get_int(data, 18), TEMP_MIN, TEMP_MAX),
            "TI_A": convert(get_int(data, 20), TEMP_MIN, TEMP_MAX),
            "TI_B": convert(get_int(data, 22), TEMP_MIN, TEMP_MAX),
            "TI11": convert(get_int(data, 42), TEMP_MIN, TEMP_MAX),
        },

        "vazoes": {
            "FI01": convert(get_int(data, 24), FLOW_MIN, FLOW_MAX),
            "FI02": convert(get_int(data, 26), FLOW_MIN, FLOW_MAX),
            "FI03": convert(get_int(data, 28), FLOW_MIN, FLOW_MAX),
            "FI04": convert(get_int(data, 30), FLOW_MIN, FLOW_MAX),
        },

        "pressoes": {
            "PI01": convert(get_int(data, 32), PI01_MIN, PI01_MAX),
            "PI02": convert(get_int(data, 34), PI02_MIN, PI02_MAX),
            "PI03": convert(get_int(data, 36), PI03_MIN, PI03_MAX),
            "PI04": convert(get_int(data, 38), PI04_MIN, PI04_MAX),
            "PI05": convert(get_int(data, 44), PI05_MIN, PI05_MAX),
        },

        "valvula": (get_int(data, 40) / 27648.0) * 100.0,
    }

    return dados


def imprimir_dados(dados):
    print("\n--- TEMPERATURAS ---")
    for nome, valor in dados["temperaturas"].items():
        print(f"{nome}: {valor:.2f} °C")

    print("\n--- VAZÕES ---")
    for nome, valor in dados["vazoes"].items():
        print(f"{nome}: {valor:.2f}")

    print("\n--- PRESSÕES ---")
    for nome, valor in dados["pressoes"].items():
        print(f"{nome}: {valor:.2f} bar")

    print("\n--- VÁLVULA ---")
    print(f"Válvula: {dados['valvula']:.2f} %")


def main():
    plc = None

    try:
        plc = conectar_clp()

        while True:
            dados = ler_dados_clp(plc)
            imprimir_dados(dados)
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nLeitura encerrada pelo usuário.")

    except Exception as erro:
        print(f"Erro: {erro}")

    finally:
        if plc is not None:
            plc.disconnect()
            plc.destroy()
            print("Conexão com CLP encerrada.")


if __name__ == "__main__":
    main()