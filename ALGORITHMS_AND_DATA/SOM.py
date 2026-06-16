# =============================
# File: SOM.py  (serviço de inferência/render do SOM)
# =============================
import os
import io
import time
import json
import math
import asyncio
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import RegularPolygon
import joblib
import httpx
import csv
from typing import Tuple, Optional

# -------- Configurações via Variáveis de Ambiente --------
# Define as dimensões do mapa e a dimensionalidade dos dados de entrada
MAP_WIDTH  = int(os.environ.get("SOM_MAP_WIDTH",  "26"))
MAP_HEIGHT = int(os.environ.get("SOM_MAP_HEIGHT", "26"))
DIM         = int(os.environ.get("SOM_DIM",        "8"))

# Endpoints e Caminhos de Sistema
SENSOR_ENDPOINT = os.environ.get(
    "SOM_SENSOR_ENDPOINT",
    "http://localhost:8000/api/v1/endpoints/?_sort=id&_order=desc&_limit=1"
)

ARTIFACT_DIR = os.environ.get(
    "SOM_ARTIFACT_DIR",
    "/home/ramon/DATAQATAR/ALGORITHMS_AND_DATA/MODEL"
)

FRAME_PATH = os.environ.get(
    "SOM_FRAME_PATH",
    "/home/ramon/DATAQATAR/ALGORITHMS_AND_DATA/som_frame.png"
)

STATUS_PATH = os.environ.get(
    "SOM_STATUS_PATH",
    "/home/ramon/DATAQATAR/ALGORITHMS_AND_DATA/som_status.json"
)

ANOMALY_LOG_PATH = os.environ.get(
    "SOM_ANOMALY_LOG_PATH",
    "/home/ramon/DATAQATAR/ALGORITHMS_AND_DATA/som_anomalies.csv"
)

REFRESH_SECONDS = float(os.environ.get("SOM_REFRESH_SECONDS", "1.0"))

# Nomes dos arquivos de artefatos do modelo treinado
WEIGHTS_NAME = os.environ.get("SOM_WEIGHTS_NAME", "som_mahal_full_offline_std_weights.npy")
SCALER_NAME  = os.environ.get("SOM_SCALER_NAME",  "som_mahal_full_offline_std_scaler.pkl")
ATIV_NAME    = os.environ.get("SOM_ATIV_NAME",    "som_mahal_full_offline_std_ativados.npy")
INV_COV_NAME = os.environ.get("SOM_INV_COV_NAME", "som_mahal_full_offline_std_inv_cov.npy")
SCALED_NAME  = os.environ.get("SOM_SCALED_NAME",  "som_mahal_full_offline_std_data_scaled.npy")

W_PATH         = os.path.join(ARTIFACT_DIR, WEIGHTS_NAME)
SCALER_PATH    = os.path.join(ARTIFACT_DIR, SCALER_NAME)
ATIVADOS_PATH = os.path.join(ARTIFACT_DIR, ATIV_NAME)
INV_COV_PATH   = os.path.join(ARTIFACT_DIR, INV_COV_NAME)
SCALED_PATH    = os.path.join(ARTIFACT_DIR, SCALED_NAME)

# Lógica de reconstrução: permite recriar a matriz de covariância ou máscara se os dados originais existirem
REBUILD_FROM_SCALED = os.environ.get("SOM_REBUILD_FROM_SCALED", "0") == "1"
SAVE_DERIVED         = os.environ.get("SOM_SAVE_DERIVED", "1") == "1"

# === Métrica / Sensibilidade ===
# Define como a distância Mahalanobis será calculada (influencia a sensibilidade a anomalias)
SENS_MODE = os.environ.get("SOM_SENS_MODE", "mahal_full").lower()
BETA      = float(os.environ.get("SOM_BETA", "0.5"))  # Parâmetro de têmpera para mahal_beta

# === Critérios de anomalia ===
USE_MASK_FINAL   = os.environ.get("SOM_USE_MASK_FINAL", "1") == "1"
USE_THRESHOLD    = os.environ.get("SOM_USE_THRESHOLD",  "1") == "1"
THRESH_PERCENTIL = float(os.environ.get("SOM_THRESH_PERCENTIL", "99.8"))
COMBINE_RULE     = os.environ.get("SOM_COMBINE_RULE", "or").lower()   # "or" (qualquer um) | "and" (ambos)

# -------- Utilidades --------

def atomic_write_bytes(path: str, data: bytes):
    """
    Escreve dados em um arquivo de forma atômica para evitar corrupção de leitura 
    por outros processos (escreve em .tmp e depois renomeia).
    """
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)

def json_default(o):
    """Tratamento de tipos NumPy para serialização JSON."""
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.ndarray,)):
        return o.tolist()
    return str(o)

def write_status(payload: dict):
    """Publica o estado atual do serviço em um arquivo JSON."""
    atomic_write_bytes(STATUS_PATH, json.dumps(payload, ensure_ascii=False, default=json_default).encode("utf-8"))

def exists_or_report(path: str) -> bool:
    """Verifica existência de arquivos e reporta erro no status JSON caso faltem."""
    if os.path.exists(path):
        return True
    err = {
        "error": f"Arquivo não encontrado: {path}",
        "hint": (
            f"Verifique SOM_ARTIFACT_DIR='{ARTIFACT_DIR}' e os nomes dos arquivos.\n"
            f"Esperados: {WEIGHTS_NAME}, {SCALER_NAME}, {ATIV_NAME}, {INV_COV_NAME}\n"
            f"Conteúdo do diretório: {os.listdir(ARTIFACT_DIR) if os.path.isdir(ARTIFACT_DIR) else 'Diretório inválido'}"
        ),
        "timestamp": float(time.time())
    }
    write_status(err)
    return False

def render_frame(ativados: np.ndarray, bmu: Tuple[int, int], anomaly_count: int) -> bytes:
    """
    Gera uma visualização em grade hexagonal do SOM.
    Azul: Neurônios que foram ativados no treino.
    Preto: Neurônios 'vazios'.
    Ponto Vermelho: BMU (Best Matching Unit) do dado atual.
    """
    fig, ax = plt.subplots(figsize=(8, 8))
    for i in range(MAP_WIDTH):
        for j in range(MAP_HEIGHT):
            # Cálculo de coordenadas para grade hexagonal (honeycomb)
            x = i * math.sqrt(3)
            y = j * 1.5 + (i % 2) * 0.75
            
            face_color = (0.2, 0.4, 1.0) if ativados[i, j] else (0.1, 0.1, 0.1)
            hexagon = RegularPolygon(
                (x, y), numVertices=6, radius=0.9,
                orientation=math.radians(30),
                facecolor=face_color, edgecolor='k', linewidth=1
            )
            ax.add_patch(hexagon)

    # Plota a posição do dado atual (BMU)
    i, j = bmu
    x = i * math.sqrt(3)
    y = j * 1.5 + (i % 2) * 0.75
    ax.plot(x, y, 'ro')
    
    ax.set_xlim(-1, MAP_WIDTH * math.sqrt(3))
    ax.set_ylim(-1, MAP_HEIGHT * 1.8)
    ax.set_aspect('equal')
    ax.set_title(f'SOM — Anomalias detectadas: {anomaly_count}')
    ax.axis('off')

    # Converte o plot para bytes PNG sem salvar no disco diretamente
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", dpi=120)
    plt.close(fig)
    buf.seek(0)
    return buf.read()

def log_anomaly(timestamp: float, bmu: Tuple[int, int], features: np.ndarray,
                dist: float, dist2: float, flags: dict):
    """
    Registra os detalhes técnicos de uma detecção de anomalia em arquivo CSV.
    """
    file_exists = os.path.exists(ANOMALY_LOG_PATH)
    with open(ANOMALY_LOG_PATH, "a", newline="") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            header = ["timestamp", "bmu_i", "bmu_j", "dist", "dist2",
                      "flag_mask", "flag_thresh", "combine_rule"] + [f"feature_{k+1}" for k in range(features.shape[0])]
            writer.writerow(header)
        row = [timestamp, int(bmu[0]), int(bmu[1]), float(dist), float(dist2),
               int(flags.get("mask", 0)), int(flags.get("thresh", 0)), COMBINE_RULE] + features.tolist()
        writer.writerow(row)

# -------- SOM NumPy Implementation --------

class SelfOrganizingMapNP:
    """
    Implementação otimizada em NumPy para inferência de Mapas Auto-Organizáveis.
    Focada em cálculo de distância Mahalanobis para detecção de anomalias.
    """
    def __init__(self, m: int, n: int, dim: int):
        self.m, self.n, self.dim = m, n, dim
        # Pré-calcula coordenadas (i, j) para mapeamento de índice -> grade
        self.locations = np.array([[i, j] for i in range(m) for j in range(n)], dtype=np.int32)
        self.som_weights = np.zeros((m * n, dim), dtype=np.float32)
        self.inv_cov = np.eye(dim, dtype=np.float32)       # Matriz de covariância inversa original
        self.inv_cov_eff = np.eye(dim, dtype=np.float32)   # Métrica efetiva após aplicação de SENS_MODE

    def set_weights(self, w: np.ndarray):
        """Carrega os pesos (codebooks) do mapa treinado."""
        assert w.shape == (self.m * self.n, self.dim)
        self.som_weights = w.astype(np.float32, copy=False)

    def set_inv_cov(self, inv_cov_like: np.ndarray):
        """Carrega a matriz inversa de covariância."""
        if inv_cov_like.ndim == 1:
            inv_cov = np.diag(inv_cov_like)
        else:
            inv_cov = inv_cov_like
        self.inv_cov = inv_cov.astype(np.float32, copy=False)

    def build_metric(self, sens_mode: str, beta: float = 0.5):
        """
        Configura a métrica de distância Mahalanobis baseada na sensibilidade desejada.
        - euclid: Distância Euclidiana padrão.
        - diag: Considera apenas variâncias individuais (Mahalanobis diagonal).
        - mahal_full: Mahalanobis completa (correlações inclusas).
        - mahal_beta: Suaviza a métrica elevando os autovalores a beta (têmpera).
        """
        sens_mode = sens_mode.lower()
        if sens_mode == "euclid":
            self.inv_cov_eff = np.eye(self.dim, dtype=np.float32)
        elif sens_mode == "diag":
            self.inv_cov_eff = np.diag(np.diag(self.inv_cov)).astype(np.float32)
        elif sens_mode == "mahal_full":
            self.inv_cov_eff = self.inv_cov.astype(np.float32, copy=False)
        elif sens_mode == "mahal_beta":
            # Decomposição para elevar a matriz a uma potência fracionária
            mu, U = np.linalg.eigh(self.inv_cov)
            mu = np.clip(mu, 1e-12, None)
            mu_beta = np.power(mu, float(beta))
            self.inv_cov_eff = (U * mu_beta) @ U.T
            self.inv_cov_eff = self.inv_cov_eff.astype(np.float32, copy=False)
        else:
            raise ValueError(f"sens_mode inválido: {sens_mode}")

    def find_bmu_d2(self, sample: np.ndarray) -> Tuple[int, float]:
        """
        Calcula a unidade de melhor ajuste (BMU) usando a distância quadrática de Mahalanobis.
        d² = (x - w)ᵀ Σ⁻¹ (x - w)
        """
        diffs = self.som_weights - sample[None, :]      # Diferença vetorizada entre entrada e todos os pesos
        left  = diffs @ self.inv_cov_eff                # Produto com a matriz métrica
        d2    = np.sum(left * diffs, axis=1)            # Resultado escalar por neurônio
        idx   = int(np.argmin(d2))
        return idx, float(d2[idx])

# -------- Funções de Processamento de Dados Scaled --------

def compute_inv_cov_from_scaled(X: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Calcula a inversa da matriz de covariância com regularização para estabilidade numérica."""
    cov = np.cov(X, rowvar=False)
    cov_reg = cov + eps * np.eye(cov.shape[0], dtype=cov.dtype)
    inv_cov = np.linalg.pinv(cov_reg)
    return inv_cov

def compute_ativados_from_scaled(X: np.ndarray, som: SelfOrganizingMapNP) -> np.ndarray:
    """Mapeia quais neurônios da grade 'ganharam' algum dado durante o treinamento."""
    m, n = som.m, som.n
    ativ = np.zeros((m, n), dtype=bool)
    bs = 2048
    K = X.shape[0]
    for start in range(0, K, bs):
        chunk = X[start:start+bs]
        for x in chunk:
            idx, _ = som.find_bmu_d2(x)
            i, j = int(som.locations[idx][0]), int(som.locations[idx][1])
            ativ[i, j] = True
    return ativ

def compute_threshold_from_scaled(X: np.ndarray, som: SelfOrganizingMapNP,
                                  percentil: int = 99) -> float:
    """Calcula um valor de corte (threshold) baseado no percentil das distâncias do treino."""
    d2_vals = np.empty(X.shape[0], dtype=np.float64)
    bs = 2048
    K = X.shape[0]
    c = 0
    for start in range(0, K, bs):
        chunk = X[start:start+bs]
        for x in chunk:
            _, d2 = som.find_bmu_d2(x)
            d2_vals[c] = d2
            c += 1
    q = float(np.percentile(d2_vals[:c], percentil))
    return q

# -------- Loop Principal Assíncrono --------

async def main():
    """
    Função principal: 
    1. Carrega artefatos do modelo.
    2. Inicializa o SOM.
    3. Monitora o endpoint de sensores em tempo real.
    4. Detecta anomalias e gera frames de visualização.
    """
    # Aguarda arquivos básicos estarem disponíveis
    need_base = [W_PATH, SCALER_PATH]
    if not all(exists_or_report(p) for p in need_base):
        while not all(os.path.exists(p) for p in need_base):
            await asyncio.sleep(2.0)

    loaded_weights = np.load(W_PATH)
    scaler = joblib.load(SCALER_PATH)

    # Tenta carregar dados escalados para cálculos dinâmicos
    X_scaled = None
    if os.path.exists(SCALED_PATH):
        try:
            X_scaled = np.load(SCALED_PATH)
            if X_scaled.ndim != 2 or X_scaled.shape[1] != DIM:
                write_status({
                    "error": f"Dimensão inconsistente em {SCALED_PATH}: {X_scaled.shape}, esperado (?, {DIM})",
                    "timestamp": float(time.time())
                })
                X_scaled = None
        except Exception as e:
            write_status({"error": f"Falha ao carregar {SCALED_PATH}: {e}", "timestamp": float(time.time())})
            X_scaled = None

    # Lógica de Inicialização da Matriz de Covariância
    if os.path.exists(INV_COV_PATH) and not REBUILD_FROM_SCALED:
        inv_cov = np.load(INV_COV_PATH)
    else:
        if X_scaled is None:
            if not exists_or_report(INV_COV_PATH):
                while not os.path.exists(INV_COV_PATH):
                    await asyncio.sleep(2.0)
            inv_cov = np.load(INV_COV_PATH)
        else:
            inv_cov = compute_inv_cov_from_scaled(X_scaled, eps=1e-6)
            if SAVE_DERIVED:
                try:
                    np.save(INV_COV_PATH, inv_cov)
                except Exception as e:
                    write_status({"error": f"Falha ao salvar inv_cov: {e}", "timestamp": float(time.time())})

    # Instanciação do SOM e construção da métrica
    som = SelfOrganizingMapNP(MAP_WIDTH, MAP_HEIGHT, DIM)
    som.set_weights(loaded_weights)
    som.set_inv_cov(inv_cov)
    som.build_metric(SENS_MODE, BETA)

    # Lógica de Inicialização da Máscara de Ativação
    if os.path.exists(ATIVADOS_PATH) and not REBUILD_FROM_SCALED:
        ativados = np.load(ATIVADOS_PATH)
    else:
        if X_scaled is None:
            if not exists_or_report(ATIVADOS_PATH):
                while not os.path.exists(ATIVADOS_PATH):
                    await asyncio.sleep(2.0)
            ativados = np.load(ATIVADOS_PATH)
        else:
            ativados = compute_ativados_from_scaled(X_scaled, som)
            if SAVE_DERIVED:
                try:
                    np.save(ATIVADOS_PATH, ativados)
                except Exception as e:
                    write_status({"error": f"Falha ao salvar ativados: {e}", "timestamp": float(time.time())})

    # Cálculo do Threshold Empírico (valor de d² máximo esperado)
    q_emp: Optional[float] = None
    if USE_THRESHOLD:
        if X_scaled is None:
            write_status({"error": "SCALED_PATH ausente para calcular limiar empírico.",
                          "timestamp": float(time.time())})
        else:
            q_emp = compute_threshold_from_scaled(X_scaled, som, THRESH_PERCENTIL)

    anomaly_count = 0
    latest_bmu = (0, 0)

    # Loop de Inferência Contínua
    async with httpx.AsyncClient() as client:
        while True:
            try:
                r = await client.get(SENSOR_ENDPOINT, timeout=2.0)
                r.raise_for_status()
                data = r.json()
                measurement = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else None)
                
                if not measurement:
                    await asyncio.sleep(REFRESH_SECONDS); continue

                # Extração das features (sensores de temperatura e pressão)
                features = np.array([
                    measurement.get('temp_1'), measurement.get('temp_2'),
                    measurement.get('temp_3'), measurement.get('temp_4'),
                    measurement.get('pressao_1'), measurement.get('pressao_2'),
                    measurement.get('pressao_3'), measurement.get('pressao_4'),
                ], dtype=float).reshape(1, -1)

                if np.isnan(features).any():
                    await asyncio.sleep(REFRESH_SECONDS); continue

                # Transformação e Busca da BMU
                features_scaled = scaler.transform(features).astype(np.float32)
                idx, d2min = som.find_bmu_d2(features_scaled[0])
                dist = float(np.sqrt(max(d2min, 0.0)))
                latest_bmu = (int(som.locations[idx][0]), int(som.locations[idx][1]))

                # Verificação de Anomalia
                # 1. Mask Check: Caiu em um neurônio que nunca foi ativado no treino?
                flag_mask = False
                if USE_MASK_FINAL:
                    flag_mask = not bool(ativados[latest_bmu[0], latest_bmu[1]])
                
                # 2. Threshold Check: A distância para o peso mais próximo é maior que o percentil limite?
                flag_thresh = False
                if USE_THRESHOLD and (q_emp is not None):
                    flag_thresh = (d2min > q_emp)

                # Regra de Combinação (OR/AND)
                if COMBINE_RULE == "and":
                    is_anom = (flag_mask and flag_thresh)
                else:
                    is_anom = (flag_mask or flag_thresh)

                if is_anom:
                    anomaly_count += 1
                    log_anomaly(
                        time.time(), latest_bmu, features.flatten(),
                        dist=dist, dist2=d2min,
                        flags={"mask": int(flag_mask), "thresh": int(flag_thresh)}
                    )

                # Renderização e Escrita de Arquivos de Saída
                frame_bytes = render_frame(ativados, latest_bmu, anomaly_count)
                atomic_write_bytes(FRAME_PATH, frame_bytes)

                status = {
                    "bmu": [int(latest_bmu[0]), int(latest_bmu[1])],
                    "anomaly_count": int(anomaly_count),
                    "dist": dist,
                    "dist2": d2min,
                    "q_percentil": THRESH_PERCENTIL if q_emp is not None else None,
                    "q_value": q_emp,
                    "sens_mode": SENS_MODE,
                    "beta": BETA if SENS_MODE == "mahal_beta" else None,
                    "use_mask_final": USE_MASK_FINAL,
                    "use_threshold": USE_THRESHOLD,
                    "combine_rule": COMBINE_RULE,
                    "timestamp": float(time.time()),
                }
                write_status(status)

            except Exception as e:
                write_status({"error": str(e), "timestamp": float(time.time())})

            await asyncio.sleep(REFRESH_SECONDS)


if __name__ == "__main__":
    asyncio.run(main())