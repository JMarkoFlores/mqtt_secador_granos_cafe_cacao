"""
Pruebas de Esquema y Validación de Telemetría JSON.
Verifica que la salida cumpla con la especificación de diseño del proyecto.
"""

import datetime
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modelo_fisico import ModeloTermicoSecador
from simulador import get_iso8601_utc


def test_formato_telemetria_json():
    modelo = ModeloTermicoSecador("secador_01", t_ideal_inicial=38.0)
    paso = modelo.simular_paso()

    mensaje = {
        "id": modelo.secador_id,
        "ts": get_iso8601_utc(),
        "t_amb": paso["t_amb"],
        "hum": paso["hum"],
        "t_grano": paso["t_grano"],
        "t_ideal": paso["t_ideal"],
        "led": paso["led"],
        "ventilador_pwm": paso["ventilador_pwm"],
    }

    # Serializar y deserializar
    serializado = json.dumps(mensaje)
    recuperado = json.loads(serializado)

    assert recuperado["id"] == "secador_01"
    assert "ts" in recuperado
    assert recuperado["ts"].endswith("Z")

    # Verificar que el ts sea un ISO8601 UTC válido
    ts_limpio = recuperado["ts"].replace("Z", "+00:00")
    dt = datetime.datetime.fromisoformat(ts_limpio)
    assert dt.tzinfo is not None

    assert isinstance(recuperado["t_amb"], (int, float))
    assert isinstance(recuperado["hum"], (int, float))
    assert isinstance(recuperado["t_grano"], (int, float))
    assert isinstance(recuperado["t_ideal"], (int, float))
    assert recuperado["led"] in ("V", "A", "R")
    assert recuperado["ventilador_pwm"] in (0, 153, 255)
