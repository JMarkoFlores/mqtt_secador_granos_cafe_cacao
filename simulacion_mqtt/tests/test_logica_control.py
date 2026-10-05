"""
Pruebas Unitarias para la Lógica de Control del Secador de Granos (Café / Cacao).
Verifica los umbrales de decisión, validación de consignas y manejo de fallas de sensores.
"""

import pytest
import sys
import os

# Asegurar que la ruta base esté en sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from logica_control import (
    calcular_actuadores,
    validar_temp_ideal,
    es_lectura_valida,
    LED_VERDE,
    LED_AMARILLO,
    LED_ROJO,
    PWM_APAGADO,
    PWM_MEDIO,
    PWM_MAXIMO,
)


class TestValidacionTempIdeal:
    """Verificación del rango de consigna permitido [10.0 - 50.0] °C."""

    def test_valores_limite_validos(self):
        valido, _ = validar_temp_ideal(10.0)
        assert valido is True
        valido, _ = validar_temp_ideal(50.0)
        assert valido is True
        valido, _ = validar_temp_ideal(38.0)
        assert valido is True
        valido, _ = validar_temp_ideal("42.5")
        assert valido is True

    def test_valores_fuera_de_rango(self):
        valido, msg = validar_temp_ideal(9.99)
        assert valido is False
        assert "fuera de rango" in msg

        valido, msg = validar_temp_ideal(50.01)
        assert valido is False
        assert "fuera de rango" in msg

        valido, _ = validar_temp_ideal(-10.0)
        assert valido is False

        valido, _ = validar_temp_ideal(100.0)
        assert valido is False

    def test_valores_no_numericos(self):
        valido, msg = validar_temp_ideal("invalido")
        assert valido is False
        assert "no es un número válido" in msg


class TestCalculoActuadores:
    """Verificación exacta de umbrales |T_grano - tempIdeal|: <=0.8, (0.8, 2.2], >2.2."""

    t_ideal = 38.0

    @pytest.mark.parametrize(
        "t_grano,expected_led,expected_pwm",
        [
            # Caso diferencia exactamente 0.0 °C
            (38.0, LED_VERDE, PWM_APAGADO),
            # Caso diferencia <= 0.8 °C (límite superior exacto)
            (38.8, LED_VERDE, PWM_APAGADO),
            (37.2, LED_VERDE, PWM_APAGADO),
            # Caso diferencia intermedia en zona verde
            (38.5, LED_VERDE, PWM_APAGADO),
            # Caso apenas por encima de 0.8 °C (transición a amarillo)
            (38.801, LED_AMARILLO, PWM_MEDIO),
            (37.199, LED_AMARILLO, PWM_MEDIO),
            # Caso zona amarilla
            (39.5, LED_AMARILLO, PWM_MEDIO),
            # Caso límite superior exacto de zona amarilla (2.2 °C)
            (40.2, LED_AMARILLO, PWM_MEDIO),
            (35.8, LED_AMARILLO, PWM_MEDIO),
            # Caso apenas por encima de 2.2 °C (transición a rojo)
            (40.201, LED_ROJO, PWM_MAXIMO),
            (35.799, LED_ROJO, PWM_MAXIMO),
            # Caso zona roja
            (45.0, LED_ROJO, PWM_MAXIMO),
            (25.0, LED_ROJO, PWM_MAXIMO),
        ],
    )
    def test_umbrales_actuadores(self, t_grano, expected_led, expected_pwm):
        led, pwm = calcular_actuadores(t_grano, self.t_ideal)
        assert led == expected_led, f"Fallo LED para t_grano={t_grano}"
        assert pwm == expected_pwm, f"Fallo PWM para t_grano={t_grano}"


class TestManejoLecturasInvalidas:
    """Verificación de detección de fallas típicas en sensor digital DS18B20."""

    def test_deteccion_errores_hardware(self):
        assert es_lectura_valida(85.0) is False  # Error Power-on Reset
        assert es_lectura_valida(-127.0) is False  # Error bus desconectado
        assert es_lectura_valida(None) is False
        assert es_lectura_valida(36.5) is True

    def test_actuadores_modo_falla_segura(self):
        # Ante sensor desconectado (-127) o en reset (85), debe activar emergencia: Rojo + 100% PWM
        led, pwm = calcular_actuadores(-127.0, 38.0)
        assert led == LED_ROJO
        assert pwm == PWM_MAXIMO

        led, pwm = calcular_actuadores(85.0, 38.0)
        assert led == LED_ROJO
        assert pwm == PWM_MAXIMO
