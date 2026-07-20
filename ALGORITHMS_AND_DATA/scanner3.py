# connection_clp.py — mapeamento definitivo ABB Modbus TCP
import struct, socket
from pymodbus.client import ModbusTcpClient

CLP_IP    = "192.168.0.35"
CLP_PORT  = 502
SOURCE_IP = "192.168.0.36"  # força saída pela Ethernet

# =============================================================
# Helpers
# =============================================================

def _f32_le(r1, r2):
    """Float 32-bit Little-Endian — usado em temperaturas reg 1008/1010"""
    return round(struct.unpack("<f", struct.pack("<HH", r1, r2))[0], 2)

def _f32_be(r1, r2):
    """Float 32-bit Big-Endian — usado em reg 6"""
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
    except: return False

def _ler_bloco(client, start, count):
    r = client.read_holding_registers(start, count=count)
    if r and not r.isError():
        return {start+i: r.registers[i] for i in range(len(r.registers))}
    return {}

# =============================================================
# Mapeamento confirmado pelo scanner
#
# Reg  | Variável               | Tipo  | Escala | Range CSV
# -----|------------------------|-------|--------|----------
# 1008 | stack_1_temperature    | F32LE | ×4     | 22–34 °C
# 1010 | water_temperature      | F32LE | ×4     | 23–34 °C
# 6    | h2_pressure            | F32BE | ×4000  | 0–3005
# 526  | aim_tank_pressure      | I16   | ×1     | 2505–3030
# 506  | stack_voltage          | I16   | ×1     | 0–550
# 586  | stack_current          | I16   | ×1     | 0–493
# 580  | aim_water_volume       | I16   | ×1     | 0–312
# 582  | h2_flow                | I16   | ×1     | 0–513
# 681  | a_column_temperature   | I16   | ×1     | 21–27 °C  (R2 do par 680)
# 687  | b_column_temperature   | I16   | ×1     | 23–27 °C  (R2 do par 686)
# 689  | water_conductivity?    | I16   | ×1     | 1–22
# =============================================================

def ler_dados_clp() -> dict:
    """
    Lê todos os sensores do CLP ABB via Modbus TCP.
    Retorna dict com as 14 variáveis de processo.
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
        # Leitura em 4 blocos — minimiza número de requisições
        d = {}
        d.update(_ler_bloco(client, 0,   30))   # reg 0–29   (h2_pressure)
        d.update(_ler_bloco(client, 500, 100))   # reg 500–599 (voltage, current, volume, flow)
        d.update(_ler_bloco(client, 678, 16))    # reg 678–693 (column temps, conductivity)
        d.update(_ler_bloco(client, 1006, 8))    # reg 1006–1013 (stack temp, water temp)

    finally:
        client.close()

    # ----------------------------------------------------------
    # Decodificação
    # ----------------------------------------------------------

    def get(reg):
        return d.get(reg, 0)

    # Temperaturas — F32 LE × 4
    stack_1_temperature = _clamp(_f32_le(get(1008), get(1009)) * 4, 0, 100)
    water_temperature   = _clamp(_f32_le(get(1010), get(1011)) * 4, 0, 100)

    # Temperaturas — I16 direto (offset ímpar: valor está em R2 do par)
    a_column_temperature = _clamp(_i16(get(681)), 0, 100)
    b_column_temperature = _clamp(_i16(get(687)), 0, 100)

    # Pressões
    h2_pressure       = _clamp(_f32_be(get(6), get(7)) * 4000, 0, 5000)
    aim_tank_pressure = _clamp(_i16(get(526)), 0, 5000)

    # Elétricos
    stack_voltage = _clamp(_i16(get(506)), 0, 700)
    stack_current = _clamp(_i16(get(586)), 0, 600)

    # Vazão / volume
    h2_flow          = _clamp(_i16(get(582)), 0, 600)
    aim_water_volume = _clamp(_i16(get(580)), 0, 500)

    # Condutividade
    water_conductivity = _clamp(_i16(get(689)), 0, 50)

    # Ainda não mapeados com certeza — retornam 0 até confirmar
    aim_stack_current_2 = 0
    aim_stack_voltage_2 = 0
    stack_2_temperature = 0

    return {
        "stack_1_temperature":  stack_1_temperature,
        "stack_2_temperature":  stack_2_temperature,   # inativo
        "water_temperature":    water_temperature,
        "a_column_temperature": a_column_temperature,
        "b_column_temperature": b_column_temperature,
        "h2_pressure":          h2_pressure,
        "aim_tank_pressure":    aim_tank_pressure,
        "stack_voltage":        stack_voltage,
        "stack_current":        stack_current,
        "aim_stack_current_2":  aim_stack_current_2,   # inativo
        "aim_stack_voltage_2":  aim_stack_voltage_2,   # inativo
        "h2_flow":              h2_flow,
        "aim_water_volume":     aim_water_volume,
        "water_conductivity":   water_conductivity,
    }


# =============================================================
# Teste rápido
# =============================================================
if __name__ == "__main__":
    import time
    print("Testando leitura...\n")
    dados = ler_dados_clp()
    print(f"{'Variável':<25} {'Valor':>10}")
    print("-" * 37)
    for k, v in dados.items():
        print(f"{k:<25} {v:>10}")