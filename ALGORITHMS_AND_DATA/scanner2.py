# monitor_expanded.py — varre mais regiões para achar todos os sensores
import struct, time, socket
from pymodbus.client import ModbusTcpClient

CLP_IP = "192.168.0.35"
SOURCE_IP = "192.168.0.36"

def f32_le(r1, r2):
    return round(struct.unpack("<f", struct.pack("<HH", r1, r2))[0], 4)

def f32_be(r1, r2):
    return round(struct.unpack(">f", struct.pack(">HH", r1, r2))[0], 4)

def i16(r):
    return r if r < 32768 else r - 65536

def port_open():
    try:
        s = socket.create_connection((CLP_IP, 502), timeout=2)
        s.close(); return True
    except: return False

def ler_bloco(client, start, count):
    r = client.read_holding_registers(start, count=count)
    if r and not r.isError():
        return {start+i: r.registers[i] for i in range(len(r.registers))}
    return {}

historico = {}

print("Aguardando CLP...")
while not port_open(): time.sleep(3)
print("CLP online.\n")

# Regiões a monitorar — baseado no scan anterior
BLOCOS = [
    (0,   30),    # reg 0-29
    (1000, 60),   # reg 1000-1059
    (490,  50),   # reg 490-539
    (570,  40),   # reg 570-609
    (680,  20),   # reg 680-699
]

while True:
    if not port_open():
        print(f"  [{time.strftime('%H:%M:%S')}] CLP offline...")
        time.sleep(5)
        continue

    try:
        client = ModbusTcpClient(
            host=CLP_IP, port=502, timeout=5,
            source_address=(SOURCE_IP, 0)
        )
        client.connect()

        dados = {}
        for start, count in BLOCOS:
            dados.update(ler_bloco(client, start, count))
            time.sleep(0.1)

        client.close()

        mudanças = []
        print(f"\n{'Reg':>6} | {'BE':>10} | {'LE':>10} | {'I16':>8} | MUDOU?")
        print("-" * 55)

        for reg in sorted(dados.keys()):
            if reg+1 not in dados: continue
            r1, r2 = dados[reg], dados[reg+1]
            if r1 == 0 and r2 == 0: continue

            be  = f32_be(r1, r2)
            le  = f32_le(r1, r2)
            i   = i16(r1)

            # escolhe o valor mais representativo
            val = le if (0.01 < abs(le) < 500) else (be if (0.01 < abs(be) < 500) else i)

            ant = historico.get(reg)
            mudou = " ***" if (ant is not None and ant != val) else ""
            if mudou: mudanças.append(reg)
            historico[reg] = val

            # mostra só os não-zero ou que mudaram
            if val != 0 or mudou:
                print(f"{reg:>6} | {be:>10.4f} | {le:>10.4f} | {i:>8} |{mudou}")

        print(f"{'─'*55} [{time.strftime('%H:%M:%S')}]")
        if mudanças:
            print(f"  Regs que mudaram: {mudanças}")

    except Exception as e:
        print(f"  Erro: {e}")
        try: client.close()
        except: pass

    time.sleep(8)