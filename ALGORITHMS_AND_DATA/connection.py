# -*- coding: utf-8 -*-
"""Leitura periódica do eletrolisador e da célula e envio para a API.

Fontes de dados:

    connection_clp      eletrolisador, Modbus TCP. É a fonte principal: se
                        ela falhar, a amostra não é enviada.
    connection_celula   célula, Modbus RTU na serial. É complementar: se
                        ela falhar, a amostra vai assim mesmo, com os campos
                        da célula em null (o model aceita buracos).

Expõe duas formas de uso:

    enviar_dados_clp()   uma tentativa de leitura + POST. Não levanta
                         exceção: registra o erro e devolve False. É o que
                         o main.py chama dentro do laço dele.

    main()               laço próprio com intervalo e backoff, para rodar
                         este módulo sozinho (python -m ... / python
                         connection.py).

Nos dois casos as conexões Modbus e o cliente HTTP são reaproveitados entre
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
    from .connection_celula import (
        BLOCOS_CELULA,
        CAMPOS_CELULA,
        abrir_conexao_celula,
        ler_dados_celula,
    )
except ImportError:  # pragma: no cover
    from connection_clp import abrir_conexao, ler_dados, validar_blocos
    from connection_celula import (
        BLOCOS_CELULA,
        CAMPOS_CELULA,
        abrir_conexao_celula,
        ler_dados_celula,
    )

__all__ = ["enviar_dados_clp", "montar_payload", "fechar", "main"]

API_URL = "http://localhost:8000/api/v1/endpoints/post"

# As grandezas do CLP mudam em escala de minutos (o scan de 21/07 mostrou
# variação relevante só a cada 1-2 min). Intervalos menores não agregam
# informação e só multiplicam tráfego e linhas de log.
INTERVALO = 5.0
BACKOFF_MAX = 60.0

# Campos do eletrolisador (connection_clp.SINAIS).
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
_celula = None
_falhas = 0
_falhas_celula = 0
_blocos_validados = False


def montar_payload(
    dados: dict[str, float],
    dados_celula: dict[str, float | None] | None = None,
) -> dict:
    """Monta o JSON do POST.

    Os campos da célula sempre entram no payload. Se a leitura da célula
    falhou (dados_celula None) ou um sinal está sem mapa, vão como null.
    """
    dados_celula = dados_celula or {}
    payload = {"timestamp": datetime.now(timezone.utc).isoformat()}
    payload.update({campo: dados[campo] for campo in CAMPOS})
    payload.update({campo: dados_celula.get(campo) for campo in CAMPOS_CELULA})
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


def _fechar_celula() -> None:
    global _celula
    if _celula is not None:
        try:
            _celula.close()
        except Exception:
            pass
        _celula = None


def _ler_celula() -> dict[str, float | None] | None:
    """Lê a célula sem nunca levantar exceção.

    Devolve None se a leitura falhou por completo; nesse caso a porta é
    fechada para ser reaberta na próxima amostra. Enquanto nenhum sinal da
    célula tiver registrador mapeado, nem abre a serial.
    """
    global _celula, _falhas_celula

    if not BLOCOS_CELULA:
        return None

    try:
        if _celula is None:
            _celula = abrir_conexao_celula()
            print("Conectado à célula (serial).")

        dados = ler_dados_celula(_celula)

        if _falhas_celula:
            print(f"Célula recuperada após {_falhas_celula} falha(s).")
        _falhas_celula = 0
        return dados

    except Exception as erro:
        _fechar_celula()
        _falhas_celula += 1
        if _falhas_celula == 1 or _falhas_celula % 10 == 0:
            print(
                f"Erro na célula (falha {_falhas_celula}), "
                f"enviando sem esses campos: {erro}"
            )
        return None


def fechar() -> None:
    """Libera as conexões Modbus e o cliente HTTP."""
    global _http, _clp
    if _clp is not None:
        try:
            _clp.close()
        except Exception:
            pass
        _clp = None
    _fechar_celula()
    if _http is not None:
        _http.close()
        _http = None


atexit.register(fechar)


def enviar_dados_clp() -> bool:
    """Lê o eletrolisador e a célula e publica na API.

    Devolve True se o POST foi aceito. Mantida com o nome e o
    comportamento tolerante a falha da versão anterior, para não quebrar
    quem já a importa.
    """
    global _clp, _falhas

    try:
        _validar_uma_vez()

        if _clp is None:
            _clp = abrir_conexao()
            print("Conectado ao CLP.")

        dados = ler_dados(_clp)
        dados_celula = _ler_celula()  # nunca levanta; None se falhou

        payload = montar_payload(dados, dados_celula)

        resposta = _http_client().post(API_URL, json=payload)
        resposta.raise_for_status()

        if _falhas:
            print(f"Recuperado apos {_falhas} falha(s).")
        _falhas = 0
        print(f"POST enviado: {payload['timestamp']}")
        return True

    except httpx.HTTPError as erro:
        # A leitura funcionou, o problema foi na API. Mantém as conexões
        # Modbus.
        _falhas += 1
        if _falhas == 1 or _falhas % 10 == 0:
            detalhe = ""
            if isinstance(erro, httpx.HTTPStatusError):
                # Num 422, o corpo diz qual campo o schema recusou.
                detalhe = f" | resposta: {erro.response.text[:500]}"
            print(f"Erro HTTP (falha {_falhas}): {erro}{detalhe}")
        return False

    except (ConnectionError, RuntimeError, OSError) as erro:
        # Problema do lado do CLP do eletrolisador: derruba o socket para
        # reconectar na próxima chamada.
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