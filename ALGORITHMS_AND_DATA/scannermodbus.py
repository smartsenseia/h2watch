# deep_scan_modbus.py — pymodbus 3.13.x
import struct, math, socket
from pymodbus.client import ModbusTcpClient

CLP_IP = "192.168.0.35"
PORTS  = [502, 503, 510, 5020, 5502, 8502]
BLOCK  = 100

# =============================================================
# Helpers
# =============================================================

def to_f32(r1, r2, mode="BE"):
    try:
        if   mode == "BE": raw = struct.pack(">HH", r1, r2)
        elif mode == "LE": raw = struct.pack("<HH", r1, r2)
        elif mode == "WS": raw = struct.pack(">HH", r2, r1)
        elif mode == "BS": raw = struct.pack("<HH", r2, r1)
        v = struct.unpack(">f" if mode in ("BE","WS") else "<f", raw)[0]
        return None if math.isnan(v) or math.isinf(v) else round(v, 5)
    except:
        return None

def plausible(v):
    return v is not None and -9999 < v < 99999 and v != 0.0

def i16(r): return r if r < 32768 else r - 65536

def decode_row(r1, r2):
    out = {}
    for m in ("BE","LE","WS","BS"):
        v = to_f32(r1, r2, m)
        if plausible(v): out[f"F32_{m}"] = v
    s = i16(r1)
    if s != 0: out["I16"] = s
    return out

def port_open(ip, port, timeout=1.0):
    try:
        s = socket.create_connection((ip, port), timeout=timeout)
        s.close(); return True
    except:
        return False

def make_client(ip, port):
    """3.13.x — sem slave no construtor"""
    return ModbusTcpClient(host=ip, port=port)

def read_regs(client, fc, address, count):
    """Chama sem qualquer keyword de slave — 3.13.x ignora ou usa broadcast"""
    try:
        if   fc == 3: r = client.read_holding_registers(address, count=count)
        elif fc == 4: r = client.read_input_registers(address, count=count)
        elif fc == 1: r = client.read_coils(address, count=count)
        elif fc == 2: r = client.read_discrete_inputs(address, count=count)
        else: return None
        if r is None or r.isError(): return None
        return r
    except Exception as e:
        return None

def scan_fc(client, fc, start, total):
    hits = []
    for base in range(start, start + total, BLOCK):
        count = min(BLOCK, start + total - base)
        resp = read_regs(client, fc, base, count)
        if resp is None:
            continue
        data = resp.bits if fc in (1,2) else resp.registers
        if fc in (1, 2):
            for i, bit in enumerate(data):
                if bit: hits.append((base+i, "BIT=1"))
        else:
            regs = data
            # offset par
            for i in range(0, len(regs)-1, 2):
                r1, r2 = regs[i], regs[i+1]
                dec = decode_row(r1, r2)
                if dec: hits.append((base+i, r1, r2, dec))
            # offset ímpar
            for i in range(1, len(regs)-1, 2):
                r1, r2 = regs[i], regs[i+1]
                dec = decode_row(r1, r2)
                if dec: hits.append((base+i, r1, r2, {f"{k}[odd]":v for k,v in dec.items()}))
    return hits

# =============================================================
# MAIN
# =============================================================

print("=" * 65)
print(f"  DEEP SCAN — {CLP_IP} | pymodbus 3.13.x")
print("=" * 65)

# --- Port scan ---
print("\n[1/3] PORT SCAN")
open_ports = []
for p in PORTS:
    ok = port_open(CLP_IP, p)
    print(f"  :{p} → {'ABERTA ✅' if ok else 'fechada'}")
    if ok: open_ports.append(p)

use_ports = open_ports if open_ports else [502]

# --- Sintaxe correta ---
print("\n[2/3] VERIFICANDO SINTAXE 3.13.x")
c = make_client(CLP_IP, 502)
c.connect()
print(f"  Conectado: {c.is_socket_open()}")

import inspect
sig3 = inspect.signature(c.read_holding_registers)
sig4 = inspect.signature(c.read_input_registers)
print(f"  Assinatura FC3: {sig3}")
print(f"  Assinatura FC4: {sig4}")

# teste rápido leitura direta
r = c.read_holding_registers(0, count=10)
if r and not r.isError():
    print(f"  Leitura reg 0-9 OK: {r.registers}")
else:
    print(f"  Leitura reg 0-9: {r}")
c.close()

# --- Deep scan ---
print("\n[3/3] DEEP REGISTER SCAN")

RANGES = [
    ("0–499",     0,     500),
    ("500–999",   500,   500),
    ("1000–1499", 1000,  500),
    ("1500–1999", 1500,  500),
    ("2000–2499", 2000,  500),
    ("4000–4199", 4000,  200),
    ("9000–9199", 9000,  200),
]

FCS = [
    (3, "Holding Registers FC3"),
    (4, "Input Registers   FC4"),
    (1, "Coils             FC1"),
    (2, "Discrete Inputs   FC2"),
]

all_hits = {}

for port in use_ports:
    client = make_client(CLP_IP, port)
    if not client.connect():
        print(f"  Não conectou em :{port}")
        continue

    print(f"\n  ── Porta {port} ──")

    for fc, fc_label in FCS:
        fc_hits = []
        for rng_label, rng_start, rng_count in RANGES:
            hits = scan_fc(client, fc, rng_start, rng_count)
            fc_hits.extend(hits)

        if fc_hits:
            print(f"\n    {fc_label} — {len(fc_hits)} posição(ões) com dados:")
            if fc in (3, 4):
                print(f"    {'Reg':>6} | {'R1':>6} {'R2':>6} | Decodificações")
                print(f"    {'-'*55}")
                seen = set()
                for row in fc_hits:
                    reg = row[0]
                    if reg in seen: continue
                    seen.add(reg)
                    r1, r2, dec = row[1], row[2], row[3]
                    dec_str = "  |  ".join(f"{k}={v}" for k,v in dec.items())
                    print(f"    {reg:>6} | {r1:>6} {r2:>6} | {dec_str}")
                    all_hits[(port, fc, reg)] = dec
            else:
                for row in fc_hits:
                    print(f"    Coil/DI {row[0]}: {row[1]}")
        else:
            print(f"    {fc_label} → nenhum dado")

    client.close()

# --- Resumo ---
print("\n" + "=" * 65)
print("RESUMO FINAL")
print("=" * 65)
if all_hits:
    for (port, fc, reg), dec in sorted(all_hits.items()):
        print(f"  Porta={port} FC={fc} Reg={reg:>6} → {dec}")
else:
    print("  Nenhum dado plausível encontrado.")
    print("\n  Próximos passos:")
    print("  1. Confirme que o Modbus está HABILITADO no CLP ABB")
    print("     (configuração via software do fabricante, ex: Drive Composer)")
    print("  2. Verifique se há firewall entre o PC e 192.168.0.35")
    print("  3. Rode: ping 192.168.0.35 no terminal")
    print("  4. Consulte o manual do ABB — alguns modelos usam")
    print("     Modbus RTU over TCP (precisa de wrapper diferente)")

print("\nScan concluído.\n")