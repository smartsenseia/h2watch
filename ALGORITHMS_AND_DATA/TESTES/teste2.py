from datetime import datetime
from pymodbus.client import ModbusSerialClient
import numpy as np
import time


MODBUS_CONFIG = {
    "port": "/dev/ttyUSB1",
    "baudrate": 19200,
    "bytesize": 8,
    "parity": "N",
    "stopbits": 1,
    "timeout": 2,
    "retries": 1,
}



def testar_portas_analogicas(slave_id, start_address: int = 0, num_entradas: int = 8):
    client = ModbusSerialClient(**MODBUS_CONFIG)
    
    if not client.connect():
        print(f"❌ Falha ao conectar ao cliente Modbus (Slave {slave_id})")
        return

    for i in range(num_entradas):
        endereco = start_address + i
        result = client.read_holding_registers(address=endereco, count=1, slave=slave_id)
        
        
        if result.isError():
            print(f"❌ Erro ao ler porta AI{i+1} (Endereço {endereco})")
        else:
            valor = result.registers[0]
            valor=valor*0.0519-5.4404
            status = "📶 Sinal detectado" if valor > 0 else "⛔ Sem sinal"
            print(f"📟 AI{i+1} | Endereço {endereco} | Valor: {valor} → {status}")

    client.close()

if __name__ == "__main__":
    while True:
        testar_portas_analogicas(slave_id=1)
        time.sleep(2)
