"""
Módulo de Lógica de Control del Secador de Granos (Café / Cacao)
Reproduce con exactitud el comportamiento del firmware Arduino Nano:
- Control en lazo cerrado hacia tempIdeal (rango 10–50 °C).
- Umbrales de diferencia |T_grano - tempIdeal|:
  * <= 0.8 °C        -> LED Verde ('V'), ventilador 0 PWM (0 %)
  * (0.8, 2.2] °C     -> LED Amarillo ('A'), ventilador 153 PWM (60 %)
  * > 2.2 °C          -> LED Rojo ('R'), ventilador 255 PWM (100 %)
"""

from typing import Tuple

# Constantes de control
PWM_APAGADO = 0
PWM_MEDIO = 153    # 60% de 255
PWM_MAXIMO = 255   # 100% de 255

LED_VERDE = "V"
LED_AMARILLO = "A"
LED_ROJO = "R"

TEMP_IDEAL_MIN = 10.0
TEMP_IDEAL_MAX = 50.0

# Lecturas anómalas típicas de fallo en sensor digital DS18B20
DS18B20_ERROR_DISCONNECTED = -127.0
DS18B20_ERROR_POWERON_RESET = 85.0


def validar_temp_ideal(valor: float) -> Tuple[bool, str]:
    """
    Valida que la temperatura ideal esté dentro del rango operativo (10 - 50 °C).
    Retorna (es_valido, mensaje_error).
    """
    try:
        val = float(valor)
    except (ValueError, TypeError):
        return False, f"El valor '{valor}' no es un número válido."

    if val < TEMP_IDEAL_MIN or val > TEMP_IDEAL_MAX:
        return False, f"Temperatura ideal fuera de rango [{TEMP_IDEAL_MIN}, {TEMP_IDEAL_MAX}] °C: {val}"

    return True, "OK"


def es_lectura_valida(t_grano: float) -> bool:
    """
    Verifica si la lectura del sensor DS18B20 es físicamente válida
    y no corresponde a un código de error de hardware conocido.
    """
    if t_grano is None:
        return False
    # DS18B20 devuelve -127 cuando se pierde la comunicación 1-Wire
    # y 85.0 en el reset de encendido si no completó la conversión.
    if abs(t_grano - DS18B20_ERROR_DISCONNECTED) < 0.01:
        return False
    if abs(t_grano - DS18B20_ERROR_POWERON_RESET) < 0.01:
        return False
    # Rango físico razonable en secado agrícola (-10 a 90 °C)
    if t_grano < -10.0 or t_grano > 90.0:
        return False
    return True


def calcular_actuadores(t_grano: float, t_ideal: float) -> Tuple[str, int]:
    """
    Calcula el estado del semáforo LED y la velocidad del ventilador PWM
    según la diferencia absoluta entre la temperatura del grano y la ideal.

    Reglas:
      <= 0.8 °C       -> LED 'V', ventilador 0
      0.8 a 2.2 °C    -> LED 'A', ventilador 153
      > 2.2 °C        -> LED 'R', ventilador 255

    En caso de lectura de sensor inválida, activa modo de emergencia:
      LED 'R', ventilador 255.
    """
    if not es_lectura_valida(t_grano):
        return LED_ROJO, PWM_MAXIMO

    diferencia = abs(t_grano - t_ideal)
    # Comparación con tolerancia numérica para punto flotante
    epsilon = 1e-7

    if diferencia <= (0.8 + epsilon):
        return LED_VERDE, PWM_APAGADO
    elif diferencia <= (2.2 + epsilon):
        return LED_AMARILLO, PWM_MEDIO
    else:
        return LED_ROJO, PWM_MAXIMO
