from __future__ import annotations
from datetime import datetime
import time
import httpx

from connection_clp import ler_dados_clp

API_URL = "http://localhost:8000/api/v1/endpoints/post"

# cliente HTTP persistente
client = httpx.Client(timeout=3.0)


def enviar_dados_clp():

    try:

        # -----------------------------
        # Ler dados do PLC
        # -----------------------------
        dados = ler_dados_clp()

        T = dados["temperaturas"]
        P = dados["pressoes"]
        F = dados["vazoes"]

        # -----------------------------
        # Montar payload
        # -----------------------------
        payload = {

            "timestamp": datetime.utcnow().isoformat(),

            # Temperaturas
            "temp_1": T["TI01"],
            "temp_2": T["TI02"],
            "temp_3": T["TI03"],
            "temp_4": T["TI04"],
            "temp_5": T["TI05"],
            "temp_6": T["TI06"],
            "temp_7": T["TI07"],
            "temp_8": T["TI08"],
            "temp_9": T["TI09"],
            "temp_10": T["TI10"],
            "temp_11": T["TI11"],
            "temp_A": T["TI_A"],
            "temp_B": T["TI_B"],

            # Pressões
            "pressao_1": P["PI01"],
            "pressao_2": P["PI02"],
            "pressao_3": P["PI03"],
            "pressao_4": P["PI04"],
            "pressao_5": P["PI05"],

            # Vazões
            "vazao_1": F["FI01"],
            "vazao_2": F["FI02"],
            "vazao_3": F["FI03"],
            "vazao_4": F["FI04"],

            # Atuador
            "valvula": dados["valvula"]
        }

        # -----------------------------
        # Enviar para API (POST)
        # -----------------------------
        resp = client.post(API_URL, json=payload)

        resp.raise_for_status()

        print("📡 POST enviado:", payload["timestamp"])

    except httpx.HTTPError as e:
        print("❌ Erro HTTP:", e)

    except Exception as e:
        print("❌ Erro geral:", e)


# -----------------------------
# Loop contínuo
# -----------------------------

if __name__ == "__main__":

    while True:

        enviar_dados_clp()

        time.sleep(1)