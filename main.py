# -*- coding: utf-8 -*-
import os
import sys
import time
import platform
import subprocess
from datetime import datetime
from typing import Optional

# ==========================================================
# Config geral
# ==========================================================

ASSET_ID = os.environ.get("ASSET_ID", "MD01BR01")
LOOP_SECONDS = float(os.environ.get("LOOP_SECONDS", "5.0"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ALGO_DIR    = os.path.join(BASE_DIR, "ALGORITHMS_AND_DATA")
FASTAPI_DIR = os.path.join(BASE_DIR, "API", "FASTAPI")
REACT_DIR   = os.path.join(BASE_DIR, "FRONTEND")

SOM_SCRIPT = os.path.join(ALGO_DIR, "SOM.py")

CLOUDFLARED_EXE    = r"C:\Program Files (x86)\cloudflared\cloudflared.exe"
CLOUDFLARED_CONFIG = os.path.join(BASE_DIR, "cloudflared_config.yml")

CLP_IP        = "192.168.0.35"
ETHERNET_IP   = "192.168.0.36"

# A rota é conferida por tempo, não por contagem de ciclos: com
# LOOP_SECONDS variável, contar ciclos dá um intervalo imprevisível.
ROTA_CHECK_SECONDS = 60.0

# Espera extra depois de falhas seguidas do CLP, para não martelar um
# equipamento fora do ar a cada LOOP_SECONDS.
BACKOFF_MAX = 60.0

# ATENÇÃO: não acrescente ALGO_DIR ao sys.path. Com ele no path, um
# "import connection_clp" e um "import ALGORITHMS_AND_DATA.connection_clp"
# criam dois objetos de módulo diferentes, cada um com sua própria conexão
# Modbus e seu próprio contador de falhas. Use sempre o caminho do pacote.
from ALGORITHMS_AND_DATA.connection import enviar_dados_clp, fechar as fechar_clp

# ==========================================================
# SOM
# ==========================================================

SOM_ENV = {
    "SOM_FRAME_PATH": os.path.join(ALGO_DIR, "som_frame.png"),
    "SOM_STATUS_PATH": os.path.join(ALGO_DIR, "som_status.json"),
    "SOM_REFRESH_SECONDS": "1.0",
    "SOM_ARTIFACT_DIR": os.path.join(ALGO_DIR, "MODEL"),
}

# ==========================================================
# Utils
# ==========================================================

def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def safe_call(fn, *args, **kwargs):
    try:
        return True, fn(*args, **kwargs)
    except Exception as e:
        return False, e


def processo_esta_vivo(proc: Optional[subprocess.Popen]) -> bool:
    return proc is not None and proc.poll() is None

# ==========================================================
# Rota estática CLP
# ==========================================================

def rota_clp_existe() -> bool:
    """Verifica se a rota para o CLP já aponta para a Ethernet."""
    try:
        saida = subprocess.run(
            "route print -4", shell=True, capture_output=True
        ).stdout.decode(errors="ignore")

        for linha in saida.splitlines():
            partes = linha.split()
            if len(partes) >= 4 and partes[0] == CLP_IP and ETHERNET_IP in partes:
                return True
        return False
    except Exception:
        return False


def fixar_rota_clp(forcar: bool = False):
    """Garante que o tráfego para o CLP sempre sai pela Ethernet.

    Só recria a rota quando ela está faltando. O par delete+add abre uma
    janela sem rota para o CLP, e como a conexão Modbus é persistente,
    isso derruba o socket e gera falha de leitura sem motivo aparente.
    """
    if not forcar and rota_clp_existe():
        return

    try:
        subprocess.run(
            f"route delete {CLP_IP}",
            shell=True, capture_output=True
        )
        result = subprocess.run(
            f"route add {CLP_IP} mask 255.255.255.255 {ETHERNET_IP} metric 1",
            shell=True, capture_output=True
        )
        if result.returncode == 0:
            log(f"✅ Rota CLP fixada: {CLP_IP} → Ethernet ({ETHERNET_IP})")
        else:
            log(f"⚠️ Falha ao fixar rota CLP: {result.stderr.decode(errors='ignore').strip()}")
            log("   Rodar como administrador costuma resolver.")
    except Exception as e:
        log(f"⚠️ Erro ao fixar rota: {e}")

# ==========================================================
# Kill portas
# ==========================================================

def matar_processos_portas(*portas: int):

    so = platform.system()

    for porta in portas:

        try:

            if so != "Windows":
                subprocess.run(["fuser", "-k", f"{porta}/tcp"], check=True)

            else:
                out = subprocess.check_output(
                    f'netstat -ano | findstr :{porta}', shell=True
                ).decode(errors="ignore")

                pids = {
                    line.split()[-1]
                    for line in out.splitlines()
                    if line.split() and line.split()[-1].isdigit()
                }

                for pid in pids:
                    if pid != "0":
                        subprocess.run(f"taskkill /PID {pid} /F", shell=True)

            log(f"✅ Porta {porta} liberada.")

        except subprocess.CalledProcessError:
            log(f"⚠️ Nenhum processo na porta {porta}.")

# ==========================================================
# React produção
# ==========================================================

def build_react():

    package_json = os.path.join(REACT_DIR, "package.json")

    if not os.path.exists(package_json):
        log(f"❌ package.json não encontrado em: {REACT_DIR}")
        return False

    node_modules = os.path.join(REACT_DIR, "node_modules")

    if not os.path.exists(node_modules):
        log("📦 node_modules não encontrado. Rodando npm install...")

        result = subprocess.run(
            ["npm.cmd", "install"],
            cwd=REACT_DIR
        )

        if result.returncode != 0:
            log("❌ Falha ao executar npm install.")
            return False

    log("⚙️ Gerando build de produção do React...")

    result = subprocess.run(
        ["npm.cmd", "run", "build"],
        cwd=REACT_DIR
    )

    if result.returncode != 0:
        log("❌ Falha ao gerar build de produção do React.")
        return False

    dist_dir = os.path.join(REACT_DIR, "dist")

    if not os.path.exists(dist_dir):
        log("❌ Build terminou, mas a pasta dist não foi encontrada.")
        return False

    log("✅ Build de produção gerado em FRONTEND/dist.")
    return True

# ==========================================================
# FastAPI
# ==========================================================

def iniciar_fastapi():

    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
        ],
        cwd=FASTAPI_DIR,
        shell=False,
    )

# ==========================================================
# Cloudflare Tunnel
# ==========================================================

def iniciar_cloudflared():

    if not os.path.exists(CLOUDFLARED_EXE):
        log(f"❌ cloudflared.exe não encontrado em: {CLOUDFLARED_EXE}")
        return None

    if not os.path.exists(CLOUDFLARED_CONFIG):
        log(f"❌ config.yml não encontrado em: {CLOUDFLARED_CONFIG}")
        return None

    return subprocess.Popen(
        [
            CLOUDFLARED_EXE,
            "tunnel",
            "--config", CLOUDFLARED_CONFIG,
            "run",
        ],
        shell=False,
    )

# ==========================================================
# SOM
# ==========================================================

def iniciar_som_service():

    env = os.environ.copy()
    env.update(SOM_ENV)

    return subprocess.Popen(
        [sys.executable, SOM_SCRIPT],
        env=env
    )

# ==========================================================
# Main
# ==========================================================

def main():

    # Fixa rota do CLP antes de qualquer coisa
    fixar_rota_clp(forcar=True)

    matar_processos_portas(8000)

    # ------------------------------------------------------
    # React build produção
    # ------------------------------------------------------

    if not build_react():
        log("🛑 Sistema interrompido porque o build do React falhou.")
        return

    # ------------------------------------------------------
    # FastAPI
    # ------------------------------------------------------

    fastapi_proc = None

    ok, res = safe_call(iniciar_fastapi)

    if ok:
        fastapi_proc = res
        log("✅ FastAPI iniciado.")
        log("🌐 Local:  http://localhost:8000")
        log("🌐 Nuvem:  https://smartsenseiah2watch.org")
    else:
        log(f"⚠️ FastAPI falhou: {res}")

    time.sleep(2)

    if processo_esta_vivo(fastapi_proc):
        log("✅ FastAPI está vivo.")
        subprocess.Popen(['cmd', '/c', 'start', 'http://localhost:8000'], shell=False)
    else:
        log("⚠️ FastAPI parece offline.")

    # ------------------------------------------------------
    # Cloudflare Tunnel
    # ------------------------------------------------------

    cloudflared_proc = None

    ok, res = safe_call(iniciar_cloudflared)

    if ok and res is not None:
        cloudflared_proc = res
        log("✅ Cloudflare tunnel iniciado.")
        log("🌐 Acesse externamente: https://smartsenseiah2watch.org")
    else:
        log(f"⚠️ Cloudflare tunnel falhou: {res}")

    # ------------------------------------------------------
    # SOM
    # ------------------------------------------------------

    som_proc = None

    ok, res = safe_call(iniciar_som_service)

    if ok:
        som_proc = res
        log("✅ SOM iniciado.")
    else:
        log(f"⚠️ SOM falhou: {res}")

    log(f"📡 Sistema ativo | asset={ASSET_ID} | loop={LOOP_SECONDS}s")

    # ------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------

    proxima_rota = time.monotonic() + ROTA_CHECK_SECONDS
    falhas = 0

    try:

        while True:

            inicio = time.monotonic()

            if inicio >= proxima_rota:
                fixar_rota_clp()
                proxima_rota = inicio + ROTA_CHECK_SECONDS

            # enviar_dados_clp trata os próprios erros e devolve bool.
            # O safe_call fica só como rede contra falha inesperada; o
            # resultado do envio está em "res", não em "ok_chamada".
            ok_chamada, res = safe_call(enviar_dados_clp)

            if not ok_chamada:
                falhas += 1
                log(f"⚠️ Erro inesperado no ciclo PLC: {res!r}")
            elif res:
                if falhas:
                    log(f"✅ CLP recuperado após {falhas} ciclo(s) com falha.")
                falhas = 0
                # O próprio connection.py já loga o POST enviado; não
                # repetir aqui para não duplicar cada linha do log.
            else:
                falhas += 1
                if falhas == 1 or falhas % 10 == 0:
                    log(f"⚠️ Ciclo PLC sem envio (falha {falhas}).")
                # A rota pode ter caído junto: revalida na próxima volta.
                proxima_rota = 0.0

            espera = LOOP_SECONDS if falhas == 0 else min(
                BACKOFF_MAX, LOOP_SECONDS * (2 ** min(falhas, 6))
            )
            decorrido = time.monotonic() - inicio
            time.sleep(max(0.0, espera - decorrido))

    except KeyboardInterrupt:

        log("🛑 Encerrando sistema...")

    finally:

        # Fecha o socket Modbus antes dos subprocessos.
        try:
            fechar_clp()
        except Exception:
            pass

        for proc in (som_proc, cloudflared_proc, fastapi_proc):

            try:
                if proc and proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass

        for proc in (som_proc, cloudflared_proc, fastapi_proc):

            try:
                if proc:
                    proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass


# ==========================================================
# Start
# ==========================================================

if __name__ == "__main__":
    main()