
# -*- coding: utf-8 -*-
import os
import sys
import time
import platform
import subprocess
import webbrowser
from datetime import datetime
from typing import Optional

# ==========================================================
# Config geral
# ==========================================================

ASSET_ID = os.environ.get("ASSET_ID", "MD01BR01")
LOOP_SECONDS = float(os.environ.get("LOOP_SECONDS", "3.0"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ALGO_DIR    = os.path.join(BASE_DIR, "ALGORITHMS_AND_DATA")
FASTAPI_DIR = os.path.join(BASE_DIR, "API", "FASTAPI")
REACT_DIR   = os.path.join(BASE_DIR, "FRONTEND")

SOM_SCRIPT = os.path.join(ALGO_DIR, "SOM.py")

CLOUDFLARED_EXE    = r"C:\cloudflared\cloudflared.exe"
CLOUDFLARED_CONFIG = os.path.join(BASE_DIR, "cloudflared_config.yml")

CLP_IP        = "192.168.0.35"
ETHERNET_IP   = "192.168.0.36"

sys.path.append(ALGO_DIR)

from ALGORITHMS_AND_DATA.connection import enviar_dados_clp

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

def fixar_rota_clp():
    """Garante que o tráfego para o CLP sempre sai pela Ethernet."""
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
            log(f"⚠️ Falha ao fixar rota CLP: {result.stderr.decode(errors='ignore')}")
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
    fixar_rota_clp()

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
    # Loop principal — refixar rota periodicamente
    # ------------------------------------------------------

    try:

        ciclo = 0

        while True:

            # Refixar rota a cada 60 ciclos (~60s) para garantir
            if ciclo % 60 == 0:
                fixar_rota_clp()

            ok_read, res = safe_call(enviar_dados_clp)

            if not ok_read:
                log(f"⚠️ Erro no ciclo PLC: {res}")
            else:
                log("✅ Dados PLC enviados para API")

            ciclo += 1
            time.sleep(LOOP_SECONDS)

    except KeyboardInterrupt:

        log("🛑 Encerrando sistema...")

    finally:

        for proc in (som_proc, cloudflared_proc, fastapi_proc):

            try:
                if proc and proc.poll() is None:
                    proc.terminate()
            except Exception:
                pass


# ==========================================================
# Start
# ==========================================================

if __name__ == "__main__":
    main()