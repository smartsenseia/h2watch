# -*- coding: utf-8 -*-
"""Leitura periódica do eletrolisador e envio para a API."""

from __future__ import annotations
from datetime import datetime, timezone
import time
import httpx

from connection_clp import abrir_conexao, ler_dados, validar_blocos

API_URL = "http://localhost:8000/api/v1/endpoints/post"

# As grandezas do CLP mudam em escala de minutos (o scan de 21/07 mostrou
# variação relevante só a cada 1-2 min). 1 s não agrega informação e só
# multiplica tráfego e linhas de log.
INTERVALO = 5.0
BACKOFF_MAX = 60.0

CAMPOS = (
    "stack_1_temperature",
    "water_temperature",
    "a_column_temperature",
    "b_column_temperature",
    "h2_pressure",
    "aim_tank_pressure",
    "stack_voltage",
    "stack_current",
    "h2o_flow",
    "aim_water_volume",
    "water_conductivity",
    "stack_load",
    "pump_speed",
    "dryer_cycle",
)


def montar_payload(dados: dict[str, float]) -> dict:
    payload = {"timestamp": datetime.now(timezone.utc).isoformat()}
    payload.update({campo: dados[campo] for campo in CAMPOS})
    return payload


def main() -> None:
    pendentes = validar_blocos()
    if pendentes:
        raise SystemExit(
            "Configuração inválida, sinais fora de BLOCOS_LEITURA: "
            + ", ".join(pendentes)
        )

    http = httpx.Client(timeout=3.0)
    clp = None
    falhas = 0

    try:
        while True:
            inicio = time.monotonic()

            try:
                if clp is None:
                    clp = abrir_conexao()
                    print("Conectado ao CLP.")

                payload = montar_payload(ler_dados(clp))

                resposta = http.post(API_URL, json=payload)
                resposta.raise_for_status()

                if falhas:
                    print(f"Recuperado apos {falhas} falha(s).")
                falhas = 0
                print(f"POST enviado: {payload['timestamp']}")

            except (ConnectionError, RuntimeError, OSError) as erro:
                # Problema no lado do CLP: derruba o socket para reconectar.
                if clp is not None:
                    clp.close()
                    clp = None
                falhas += 1
                if falhas == 1 or falhas % 10 == 0:
                    print(f"Erro no CLP (falha {falhas}): {erro}")

            except httpx.HTTPError as erro:
                # A leitura funcionou, o problema foi na API. Mantém o socket.
                falhas += 1
                if falhas == 1 or falhas % 10 == 0:
                    print(f"Erro HTTP (falha {falhas}): {erro}")

            espera = INTERVALO if falhas == 0 else min(
                BACKOFF_MAX, INTERVALO * (2 ** min(falhas, 6))
            )
            decorrido = time.monotonic() - inicio
            time.sleep(max(0.0, espera - decorrido))

    except KeyboardInterrupt:
        print("\nEncerrando.")
    finally:
        if clp is not None:
            clp.close()
        http.close()


if __name__ == "__main__":
    main()