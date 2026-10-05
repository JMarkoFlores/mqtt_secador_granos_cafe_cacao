"""
Módulo de Modelo Físico Térmico del Secador de Granos (Café / Cacao)
Simula el comportamiento termodinámico creíble de la masa de grano:
- Inercia térmica de primer orden hacia tempIdeal.
- Deriva ambiental suave de temperatura y humedad (sensor DHT).
- Influencia del ventilador PWM en la tasa de enfriamiento/disipación.
- Ruido gaussiano de medición.
- Capacidad de inyección de anomalías y fallas de hardware (DS18B20 85°C / -127°C, picos).
"""

import math
import random
from typing import Optional, Tuple
from logica_control import (
    calcular_actuadores,
    validar_temp_ideal,
    DS18B20_ERROR_DISCONNECTED,
    DS18B20_ERROR_POWERON_RESET,
)


class ModeloTermicoSecador:
    def __init__(
        self,
        secador_id: str,
        t_ideal_inicial: float = 38.0,
        t_grano_inicial: Optional[float] = None,
        t_amb_inicial: Optional[float] = None,
        hum_inicial: Optional[float] = None,
        inercia_alfa: float = 0.05,
        inyectar_fallas_automaticas: bool = False,
    ):
        self.secador_id = secador_id
        valido, _ = validar_temp_ideal(t_ideal_inicial)
        self.t_ideal = float(t_ideal_inicial) if valido else 38.0

        # Para que cada secador tenga valores iniciales y trayectorias distintas
        hash_id = sum(ord(c) for c in secador_id)
        random.seed(hash_id + 42)

        # Inicialización de temperaturas diferenciadas
        if t_grano_inicial is not None:
            self.t_grano = float(t_grano_inicial)
        else:
            # Rango inicial disperso entre 26°C y 44°C según el secador
            self.t_grano = 28.0 + (hash_id % 15) * 1.1

        if t_amb_inicial is not None:
            self.t_amb = float(t_amb_inicial)
        else:
            self.t_amb = 24.0 + (hash_id % 7) * 0.8

        if hum_inicial is not None:
            self.hum = float(hum_inicial)
        else:
            self.hum = 60.0 + (hash_id % 9) * 2.0

        self.inercia_alfa = inercia_alfa
        self.inyectar_fallas_automaticas = inyectar_fallas_automaticas

        # Flags para inyección de fallas controladas (manuales o de test)
        self.falla_forzada: Optional[str] = None  # '85', '-127', 'pico', 'desconexion'
        self.paso_contador = 0

        # Estado inicial de actuadores
        self.led, self.ventilador_pwm = calcular_actuadores(self.t_grano, self.t_ideal)

    def set_temp_ideal(self, nueva_temp: float) -> Tuple[bool, str]:
        """Actualiza la temperatura ideal si pasa la validación."""
        valido, msg = validar_temp_ideal(nueva_temp)
        if valido:
            self.t_ideal = float(nueva_temp)
        return valido, msg

    def simular_paso(self, delta_t_segundos: float = 2.0) -> dict:
        """
        Avanza el modelo termodinámico un intervalo delta_t y retorna
        la lectura generada con el estado de sensores y actuadores.
        """
        self.paso_contador += 1

        # 1. Deriva ambiental suave (DHT)
        ruido_amb = random.gauss(0.0, 0.05)
        # Ciclo diurno simulado muy lento + ruido
        self.t_amb = max(18.0, min(40.0, self.t_amb + 0.01 * math.sin(self.paso_contador / 50.0) + ruido_amb))

        ruido_hum = random.gauss(0.0, 0.15)
        self.hum = max(30.0, min(95.0, self.hum - 0.02 * math.sin(self.paso_contador / 50.0) + ruido_hum))

        # 2. Conducción térmica hacia t_ideal
        # Si t_grano < t_ideal: el sistema de calefacción calienta hacia t_ideal.
        # Si t_grano > t_ideal: el enfriamiento natural + ventilador disipan calor.
        error_temp = self.t_ideal - self.t_grano

        # Tasa de disipación adicional aportada por el ventilador PWM
        factor_ventilador = 1.0 + (self.ventilador_pwm / 255.0) * 1.5

        if error_temp < 0:
            # Grano más caliente que la consigna -> ventilador acelera enfriamiento
            delta_termico = self.inercia_alfa * error_temp * delta_t_segundos * factor_ventilador
        else:
            # Grano más frío -> calefacción activa convergencia
            delta_termico = self.inercia_alfa * error_temp * delta_t_segundos

        ruido_sensor = random.gauss(0.0, 0.04)
        self.t_grano += delta_termico + ruido_sensor

        # 3. Aplicación o inyección de fallas
        t_grano_emitida = self.t_grano

        if self.falla_forzada == "85":
            t_grano_emitida = DS18B20_ERROR_POWERON_RESET
        elif self.falla_forzada == "-127":
            t_grano_emitida = DS18B20_ERROR_DISCONNECTED
        elif self.falla_forzada == "pico":
            t_grano_emitida += 15.0
        elif self.inyectar_fallas_automaticas and (self.paso_contador % 60 == 0):
            # Inyección esporádica si el flag general está activo
            t_grano_emitida = random.choice([DS18B20_ERROR_POWERON_RESET, DS18B20_ERROR_DISCONNECTED])

        # 4. Cálculo de actuadores con la lectura percibida
        self.led, self.ventilador_pwm = calcular_actuadores(t_grano_emitida, self.t_ideal)

        return {
            "secador_id": self.secador_id,
            "t_amb": round(self.t_amb, 2),
            "hum": round(self.hum, 2),
            "t_grano": round(t_grano_emitida, 2),
            "t_ideal": round(self.t_ideal, 2),
            "led": self.led,
            "ventilador_pwm": self.ventilador_pwm,
        }
