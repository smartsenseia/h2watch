from __future__ import annotations
from datetime import datetime
import time
import httpx

from connection_clp import ler_dados_clp

API_URL = "http://localhost:8000/api/v1/endpoints/post"

client = httpx.Client(timeout=3.0)


def enviar_dados_clp():
    try:
        dados = ler_dados_clp()

        payload = {
            "timestamp": datetime.utcnow().isoformat(),

            # Temperaturas — mapeamento ABB → campos da API
            "temp_1":  dados["stack_1_temperature"],    # reg 1008 LE×4
            "temp_2":  dados["stack_2_temperature"],    # inativo = 0
            "temp_3":  dados["water_temperature"],      # reg 1010 LE×4
            "temp_4":  dados["a_column_temperature"],   # reg 681
            "temp_5":  dados["b_column_temperature"],   # reg 687
            "temp_6":  0,  # não mapeado ainda
            "temp_7":  0,  # não mapeado ainda
            "temp_8":  0,  # não mapeado ainda
            "temp_9":  0,  # não mapeado ainda
            "temp_10": 0,  # não mapeado ainda
            "temp_11": 0,  # não mapeado ainda
            "temp_A":  0,  # não mapeado ainda
            "temp_B":  0,  # não mapeado ainda

            # Pressões
            "pressao_1": dados["h2_pressure"],          # reg 6 BE×4000
            "pressao_2": dados["aim_tank_pressure"],    # reg 526
            "pressao_3": 0,  # não mapeado ainda
            "pressao_4": 0,  # não mapeado ainda
            "pressao_5": 0,  # não mapeado ainda

            # Vazões
            "vazao_1": dados["stack_voltage"],          # reg 506
            "vazao_2": dados["stack_current"],          # reg 586
            "vazao_3": dados["h2_flow"],                # reg 582
            "vazao_4": dados["aim_water_volume"],       # reg 580

            # Atuador
            "valvula": dados["water_conductivity"],     # reg 689
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