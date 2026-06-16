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
LOOP_SECONDS = float(os.environ.get("LOOP_SECONDS", "1.0"))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ALGO_DIR = os.path.join(BASE_DIR, "ALGORITHMS_AND_DATA")
FASTAPI_DIR = os.path.join(BASE_DIR, "FASTAPI")
REACT_DIR = os.path.join(BASE_DIR, "REACT", "frontend")

SOM_SCRIPT = os.path.join(ALGO_DIR, "SOM.py")

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
            ["npm", "install"],
            cwd=REACT_DIR
        )

        if result.returncode != 0:
            log("❌ Falha ao executar npm install.")
            return False

    log("⚙️ Gerando build de produção do React...")

    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=REACT_DIR
    )

    if result.returncode != 0:
        log("❌ Falha ao gerar build de produção do React.")
        return False

    dist_dir = os.path.join(REACT_DIR, "dist")

    if not os.path.exists(dist_dir):
        log("❌ Build terminou, mas a pasta dist não foi encontrada.")
        return False

    log("✅ Build de produção gerado em REACT/frontend/dist.")
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
        log("🌐 Acesse: http://192.168.0.6:8000")
    else:
        log(f"⚠️ FastAPI falhou: {res}")

    time.sleep(2)

    if processo_esta_vivo(fastapi_proc):
        log("✅ FastAPI está vivo.")
    else:
        log("⚠️ FastAPI parece offline.")

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

    try:

        while True:

            ok_read, res = safe_call(enviar_dados_clp)

            if not ok_read:
                log(f"⚠️ Erro no ciclo PLC: {res}")
            else:
                log("✅ Dados PLC enviados para API")

            time.sleep(LOOP_SECONDS)

    except KeyboardInterrupt:

        log("🛑 Encerrando sistema...")

    finally:

        for proc in (som_proc, fastapi_proc):

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