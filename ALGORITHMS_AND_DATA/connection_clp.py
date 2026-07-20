# connection_clp.py — mapeamento definitivo ABB Modbus TCP
import struct, socket
from pymodbus.client import ModbusTcpClient

CLP_IP    = "192.168.0.35"
CLP_PORT  = 502
SOURCE_IP = "192.168.0.36"   # força saída pela Ethernet

# =============================================================
# Helpers
# =============================================================

def _f32_le(r1, r2):
    """Float 32-bit Little-Endian — temperaturas reg 1008/1010"""
    return round(struct.unpack("<f", struct.pack("<HH", r1, r2))[0], 2)

def _f32_be(r1, r2):
    """Float 32-bit Big-Endian — pressão H2 reg 6"""
    return round(struct.unpack(">f", struct.pack(">HH", r1, r2))[0], 2)

def _i16(r):
    """Int 16-bit signed"""
    return r if r < 32768 else r - 65536

def _clamp(v, vmin, vmax):
    return max(vmin, min(vmax, v))

def _port_open(timeout=2):
    try:
        s = socket.create_connection((CLP_IP, CLP_PORT), timeout=timeout)
        s.close(); return True
    except:
        return False

def _ler_bloco(client, start, count):
    r = client.read_holding_registers(start, count=count)
    if r and not r.isError():
        return {start + i: r.registers[i] for i in range(len(r.registers))}
    return {}

# =============================================================
# Mapeamento de registradores e conversões
#
# Reg  | Variável               | Tipo  | Conversão        | Range painel
# -----|------------------------|-------|------------------|-------------------
# 1008 | stack_1_temperature    | F32LE | × 4              | 22–34 °C
# 1010 | water_temperature      | F32LE | × 4              | 20–34 °C
# 6    | h2_pressure            | F32BE | × 1 (já em bar)  | 0–28 bar
# 526  | aim_tank_pressure      | I16   | ÷ 100            | 25.6–30 bar
# 506  | stack_voltage          | I16   | ÷ 10             | 42–54 V
# 586  | stack_current          | I16   | ÷ 10             | 30–52 A
# 580  | aim_water_volume       | I16   | ÷ 10             | 20–28 Lt
# 582  | h2_flow                | I16   | × 1 (já NLt/h)   | 0–500 NLt/h
# 584  | water_flow             | I16   | ÷ 10             | 4–6 Lt/m
# 681  | a_column_temperature   | I16   | ÷ 10             | ~17 °C
# 687  | b_column_temperature   | I16   | ÷ 10             | ~17 °C
# 689  | water_conductivity     | I16   | ÷ 100            | 0.1–0.2 µS
# =============================================================

def ler_dados_clp() -> dict:
    """
    Lê todos os sensores do CLP ABB via Modbus TCP.
    Retorna dict com as variáveis de processo convertidas para unidades físicas.
    """
    if not _port_open():
        raise ConnectionError(f"CLP inacessível em {CLP_IP}:{CLP_PORT}")

    client = ModbusTcpClient(
        host=CLP_IP,
        port=CLP_PORT,
        timeout=5,
        source_address=(SOURCE_IP, 0)
    )
    if not client.connect():
        raise ConnectionError(f"Falha ao conectar em {CLP_IP}:{CLP_PORT}")

    try:
        d = {}
        d.update(_ler_bloco(client, 0,    30))    # reg 0–29   → h2_pressure (F32BE, reg 6)
        d.update(_ler_bloco(client, 500,  100))   # reg 500–599 → voltage, current, volume, flow
        d.update(_ler_bloco(client, 678,  16))    # reg 678–693 → column temps, conductivity
        d.update(_ler_bloco(client, 1006, 8))     # reg 1006–1013 → stack temp, water temp
    finally:
        client.close()

    # ----------------------------------------------------------
    # Decodificação com conversões fisicamente corretas
    # ----------------------------------------------------------
    def get(reg):
        return d.get(reg, 0)

    # --- Temperaturas — F32LE × 4 (float bruto ~5–8 → × 4 = °C) ---
    stack_1_temperature = _clamp(_f32_le(get(1008), get(1009)) * 4, 0, 100)
    water_temperature   = _clamp(_f32_le(get(1010), get(1011)) * 4, 0, 100)

    # --- Temperaturas colunas TSA — I16 ÷ 10 (bruto ~170 → ÷10 = 17 °C) ---
    a_column_temperature = _clamp(_i16(get(681)) / 10, -50, 200)
    b_column_temperature = _clamp(_i16(get(687)) / 10, -50, 200)

    # --- Pressões ---
    # H2 outlet: F32BE já entrega o valor em bar diretamente (remover ×4000 anterior)
    h2_pressure      = _clamp(_f32_be(get(6), get(7)),         0, 50)

    # Tank pressure: I16 ÷ 100 (bruto ~2560–3030 → ÷100 = 25.6–30.3 bar)
    aim_tank_pressure = _clamp(_i16(get(526)) / 100,           0, 50)

    # --- Elétricos ---
    # Bruto 300–550 (×10 do valor real) → ÷ 10
    stack_voltage = _clamp(_i16(get(506)) / 10, 0, 100)
    stack_current = _clamp(_i16(get(586)) / 10, 0, 100)

    # --- Fluxos e volumes ---
    # H2 flow: I16 já em NLt/h diretamente (bruto 0–500)
    h2_flow = _clamp(_i16(get(582)), 0, 2500)

    # Water flow: I16 ÷ 10 (bruto ~40–60 → ÷10 = 4.0–6.0 Lt/m)
    # ATENÇÃO: registrador 584 a confirmar — ajuste se scanner indicar outro reg
    water_flow = _clamp(_i16(get(584)) / 10, 0, 20)

    # Water tank volume: I16 ÷ 10 (bruto ~200–280 → ÷10 = 20–28 Lt)
    aim_water_volume = _clamp(_i16(get(580)) / 10, 0, 200)

    # --- Condutividade ---
    # I16 ÷ 100 (bruto ~10–22 → ÷100 = 0.10–0.22 µS)
    water_conductivity = _clamp(_i16(get(689)) / 100, 0, 20)

    # --- Não mapeados com certeza — retornam 0 até confirmar ---
    aim_stack_current_2 = 0
    aim_stack_voltage_2 = 0
    stack_2_temperature = 0

    return {
        "stack_1_temperature":  stack_1_temperature,   # °C
        "stack_2_temperature":  stack_2_temperature,   # °C  (inativo)
        "water_temperature":    water_temperature,     # °C
        "a_column_temperature": a_column_temperature,  # °C
        "b_column_temperature": b_column_temperature,  # °C
        "h2_pressure":          h2_pressure,           # bar
        "aim_tank_pressure":    aim_tank_pressure,     # bar
        "stack_voltage":        stack_voltage,         # V
        "stack_current":        stack_current,         # A
        "aim_stack_current_2":  aim_stack_current_2,   # A   (inativo)
        "aim_stack_voltage_2":  aim_stack_voltage_2,   # V   (inativo)
        "h2_flow":              h2_flow,               # NLt/h
        "water_flow":           water_flow,            # Lt/m
        "aim_water_volume":     aim_water_volume,      # Lt
        "water_conductivity":   water_conductivity,    # µS
    }

# =============================================================
# Teste rápido
# =============================================================
if __name__ == "__main__":
    print("Testando leitura...\n")
    dados = ler_dados_clp()
    units = {
        "stack_1_temperature":  "°C",
        "stack_2_temperature":  "°C",
        "water_temperature":    "°C",
        "a_column_temperature": "°C",
        "b_column_temperature": "°C",
        "h2_pressure":          "bar",
        "aim_tank_pressure":    "bar",
        "stack_voltage":        "V",
        "stack_current":        "A",
        "aim_stack_current_2":  "A",
        "aim_stack_voltage_2":  "V",
        "h2_flow":              "NLt/h",
        "water_flow":           "Lt/m",
        "aim_water_volume":     "Lt",
        "water_conductivity":   "µS",
    }
    print(f"{'Variável':<25} {'Valor':>10}  {'Unidade'}")
    print("-" * 45)
    for k, v in dados.items():
        print(f"{k:<25} {v:>10.2f}  {units.get(k, '')}")