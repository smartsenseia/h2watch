# -*- coding: utf-8 -*-
"""Leitura periódica do eletrolisador e envio para a API.

Expõe duas formas de uso:

    enviar_dados_clp()   uma tentativa de leitura + POST. Não levanta
                         exceção: registra o erro e devolve False. É o que
                         o main.py chama dentro do laço dele.

    main()               laço próprio com intervalo e backoff, para rodar
                         este módulo sozinho (python -m ... / python
                         connection.py).

Nos dois casos a conexão Modbus e o cliente HTTP são reaproveitados entre
as chamadas. Abrir e fechar o socket a cada amostra esgota portas em
TIME_WAIT e alguns CLPs limitam conexões em rajada.
"""

from __future__ import annotations
from datetime import datetime, timezone
import atexit
import time
import httpx

# Import relativo quando este arquivo faz parte de um pacote
# (ALGORITHMS_AND_DATA.connection), absoluto quando é executado direto.
try:
    from .connection_clp import abrir_conexao, ler_dados, validar_blocos
except ImportError:  # pragma: no cover
    from connection_clp import abrir_conexao, ler_dados, validar_blocos

__all__ = ["enviar_dados_clp", "montar_payload", "fechar", "main"]

API_URL = "http://localhost:8000/api/v1/endpoints/post"

# As grandezas do CLP mudam em escala de minutos (o scan de 21/07 mostrou
# variação relevante só a cada 1-2 min). Intervalos menores não agregam
# informação e só multiplicam tráfego e linhas de log.
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

# Recursos reaproveitados entre chamadas.
_http: httpx.Client | None = None
_clp = None
_falhas = 0
_blocos_validados = False


def montar_payload(dados: dict[str, float]) -> dict:
    payload = {"timestamp": datetime.now(timezone.utc).isoformat()}
    payload.update({campo: dados[campo] for campo in CAMPOS})
    return payload


def _http_client() -> httpx.Client:
    global _http
    if _http is None:
        _http = httpx.Client(timeout=3.0)
    return _http


def _validar_uma_vez() -> None:
    """Confere que todo registrador de SINAIS cai dentro de BLOCOS_LEITURA."""
    global _blocos_validados
    if _blocos_validados:
        return
    pendentes = validar_blocos()
    if pendentes:
        raise RuntimeError(
            "Configuração inválida, sinais fora de BLOCOS_LEITURA: "
            + ", ".join(pendentes)
        )
    _blocos_validados = True


def fechar() -> None:
    """Libera a conexão Modbus e o cliente HTTP."""
    global _http, _clp
    if _clp is not None:
        try:
            _clp.close()
        except Exception:
            pass
        _clp = None
    if _http is not None:
        _http.close()
        _http = None


atexit.register(fechar)


def enviar_dados_clp() -> bool:
    """Lê o CLP e publica na API. Devolve True se o POST foi aceito.

    Mantida com o nome e o comportamento tolerante a falha da versão
    anterior, para não quebrar quem já a importa.
    """
    global _clp, _falhas

    try:
        _validar_uma_vez()

        if _clp is None:
            _clp = abrir_conexao()
            print("Conectado ao CLP.")

        payload = montar_payload(ler_dados(_clp))

        resposta = _http_client().post(API_URL, json=payload)
        resposta.raise_for_status()

        if _falhas:
            print(f"Recuperado apos {_falhas} falha(s).")
        _falhas = 0
        print(f"POST enviado: {payload['timestamp']}")
        return True

    except httpx.HTTPError as erro:
        # A leitura funcionou, o problema foi na API. Mantém o socket Modbus.
        _falhas += 1
        if _falhas == 1 or _falhas % 10 == 0:
            print(f"Erro HTTP (falha {_falhas}): {erro}")
        return False

    except (ConnectionError, RuntimeError, OSError) as erro:
        # Problema do lado do CLP: derruba o socket para reconectar na
        # próxima chamada.
        if _clp is not None:
            try:
                _clp.close()
            except Exception:
                pass
            _clp = None
        _falhas += 1
        if _falhas == 1 or _falhas % 10 == 0:
            print(f"Erro no CLP (falha {_falhas}): {erro}")
        return False

    except Exception as erro:  # rede de segurança, o laço não pode morrer
        _falhas += 1
        if _falhas == 1 or _falhas % 10 == 0:
            print(f"Erro inesperado (falha {_falhas}): {erro!r}")
        return False


def main() -> None:
    """Laço próprio, para rodar este módulo sozinho."""
    try:
        while True:
            inicio = time.monotonic()
            enviar_dados_clp()

            espera = INTERVALO if _falhas == 0 else min(
                BACKOFF_MAX, INTERVALO * (2 ** min(_falhas, 6))
            )
            decorrido = time.monotonic() - inicio
            time.sleep(max(0.0, espera - decorrido))
    except KeyboardInterrupt:
        print("\nEncerrando.")
    finally:
        fechar()


if __name__ == "__main__":
    main()