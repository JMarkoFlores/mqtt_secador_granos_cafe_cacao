"""
Pruebas Unitarias para el Modelo Físico Térmico.
Verifica la simulación paso a paso, convergencia hacia la consigna y la inyección de fallas.
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from modelo_fisico import ModeloTermicoSecador
from logica_control import DS18B20_ERROR_DISCONNECTED, DS18B20_ERROR_POWERON_RESET, LED_ROJO, PWM_MAXIMO


class TestModeloFisicoTermico:

    def test_estructura_datos_paso(self):
        secador = ModeloTermicoSecador(secador_id="secador_test_01", t_ideal_inicial=38.0)
        paso = secador.simular_paso(delta_t_segundos=2.0)

        claves_esperadas = {"secador_id", "t_amb", "hum", "t_grano", "t_ideal", "led", "ventilador_pwm"}
        assert set(paso.keys()) == claves_esperadas
        assert paso["secador_id"] == "secador_test_01"
        assert paso["t_ideal"] == 38.0
        assert 15.0 <= paso["t_amb"] <= 45.0
        assert 20.0 <= paso["hum"] <= 100.0

    def test_convergencia_hacia_consigna(self):
        """Si la masa de grano inicia en 25 °C y la consigna es 40 °C, debe tender hacia 40 °C."""
        secador = ModeloTermicoSecador(
            secador_id="secador_conv",
            t_ideal_inicial=40.0,
            t_grano_inicial=25.0,
            inercia_alfa=0.1,
        )

        diferencia_inicial = abs(secador.t_grano - 40.0)

        # Ejecutar 30 pasos de simulación
        for _ in range(30):
            secador.simular_paso(delta_t_segundos=2.0)

        diferencia_final = abs(secador.t_grano - 40.0)
        # La distancia a la consigna debe haberse reducido sustancialmente
        assert diferencia_final < diferencia_inicial
        assert diferencia_final < 1.5  # Converge a menos de 1.5 °C de error

    def test_inyeccion_falla_85(self):
        secador = ModeloTermicoSecador(secador_id="secador_falla_85", t_ideal_inicial=38.0)
        secador.falla_forzada = "85"
        paso = secador.simular_paso()

        assert paso["t_grano"] == DS18B20_ERROR_POWERON_RESET
        assert paso["led"] == LED_ROJO
        assert paso["ventilador_pwm"] == PWM_MAXIMO

    def test_inyeccion_falla_desconectado(self):
        secador = ModeloTermicoSecador(secador_id="secador_falla_disc", t_ideal_inicial=38.0)
        secador.falla_forzada = "-127"
        paso = secador.simular_paso()

        assert paso["t_grano"] == DS18B20_ERROR_DISCONNECTED
        assert paso["led"] == LED_ROJO
        assert paso["ventilador_pwm"] == PWM_MAXIMO

    def test_cambio_consigna(self):
        secador = ModeloTermicoSecador(secador_id="secador_cmd", t_ideal_inicial=38.0)
        valido, _ = secador.set_temp_ideal(44.0)
        assert valido is True
        assert secador.t_ideal == 44.0

        valido_invalido, _ = secador.set_temp_ideal(99.0)
        assert valido_invalido is False
        assert secador.t_ideal == 44.0  # Mantiene la anterior
