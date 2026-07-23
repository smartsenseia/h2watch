from __future__ import annotations
from datetime import datetime
import time
import httpx
from connection_clp import ler_dados_clp

API_URL = "http://localhost:8000/api/v1/endpoints/post"

client = httpx.Client(timeout=3.0)

# =============================================================================
# LEGENDA DE STATUS (validado contra a IHM + scanner):
#   [OK]         escala confirmada, bruto×escala cai em cima da IHM
#   [REG_ERRADO] registrador congelado ou incoerente com a IHM -> NÃO confiar,
#                reencontrar o registrador (achar_registrador / testar_decodes)
#   [VERIFICAR]  provável, mas sem referência da IHM para cravar
#   [ZERO]       canal inativo, sempre 0 por enquanto
# =============================================================================


def enviar_dados_clp():
    try:
        dados = ler_dados_clp()

        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "stack_1_temperature":  dados["stack_1_temperature"],    # reg 1008  ❗INCERTO
            "stack_2_temperature":  dados["stack_2_temperature"],    # inativo = 0
            "water_temperature":  dados["water_temperature"],      # reg 1010  ❗INCERTO
            "a_column_temperature":  dados["a_column_temperature"],   # reg 681   ❗INCERTO
            "b_column_temperature":  dados["b_column_temperature"],   # reg 687   ❗INCERTO
            "h2_pressure": dados["h2_pressure"],              # reg 6     ❗INCERTO
            "aim_tank_pressure": dados["aim_tank_pressure"],  # reg 526   ✅
            "stack_voltage": dados["stack_voltage"],          # reg 506   ✅ (tensão)
            "stack_current": dados["stack_current"],          # reg 586   ✅ (corrente)
            "h2_flow": dados["h2_flow"],                      # reg 582   ⚠ verificar
            "aim_water_volume": dados["aim_water_volume"],    # reg 580   ✅
            "water_conductivity": dados["water_conductivity"],# reg 689   ✅ (condutiv.)
        }

        resp = client.post(API_URL, json=payload)
        resp.raise_for_status()
        print(f"📡 POST enviado: {payload['timestamp']}")

    except httpx.HTTPError as e:
        print("❌ Erro HTTP:", e)
    except Exception as e:
        print("❌ Erro geral:", e)


if __name__ == "__main__":
    while True:
        enviar_dados_clp()
        time.sleep(1)