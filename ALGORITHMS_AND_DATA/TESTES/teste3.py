# ALGORITHMS_AND_DATA/teste3.py
from FP import FP
from Config_modbus import MODBUS_CONFIG
import time, math

fp = FP(modbus_kw=MODBUS_CONFIG, unit_id=1, addr=0, count=4, rho=997.0, G=9.80665, AB=0.058)

for _ in range(3):  # 2+ chamadas para ter base
    fp_val = fp.step()
    if isinstance(fp_val, float):
        print(f"FP={fp_val:.6f}  dt_s={fp.last_dt_s:.3f}")
    else:
        print("Aguardando amostras suficientes...")
    time.sleep(1.0)
