"""
Simulador de Secadores de Café / Cacao bajo protocolo MQTT.
Soporta N secadores virtuales concurrentes con paho-mqtt 2.x (CallbackAPIVersion.VERSION2).

Tópicos utilizados:
- Publicación de telemetría:  secado/<id_secador>/telemetria (QoS 1)
- Publicación de estado:      secado/<id_secador>/estado (online/offline, retain=True, con Last Will)
- Suscripción a consigna:    secado/<id_secador>/cmd/temp_ideal
- Publicación de respuesta:   secado/<id_secador>/ack
"""

import argparse
import datetime
import json
import logging
import os
import signal
import sys
import threading
import time
from typing import Dict, List, Optional

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from logica_control import validar_temp_ideal
from modelo_fisico import ModeloTermicoSecador

# Configuración de logging estándar
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("SimuladorMQTT")


def get_iso8601_utc() -> str:
    """Retorna la fecha y hora actual en formato ISO8601 UTC con 'Z'."""
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class SecadorVirtual:
    """
    Representa una unidad de secado física virtualizada que gestiona
    su propia conexión MQTT, Last Will, telemetría y recepción de consignas.
    """

    def __init__(
        self,
        secador_id: str,
        broker_host: str,
        broker_port: int,
        username: Optional[str] = None,
        password: Optional[str] = None,
        qos: int = 1,
        intervalo_pub: float = 2.0,
        t_ideal_inicial: float = 38.0,
        inyectar_fallas: bool = False,
    ):
        self.secador_id = secador_id
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.qos = qos
        self.intervalo_pub = intervalo_pub

        self.modelo = ModeloTermicoSecador(
            secador_id=secador_id,
            t_ideal_inicial=t_ideal_inicial,
            inyectar_fallas_automaticas=inyectar_fallas,
        )

        self.topic_telemetria = f"secado/{self.secador_id}/telemetria"
        self.topic_estado = f"secado/{self.secador_id}/estado"
        self.topic_cmd = f"secado/{self.secador_id}/cmd/temp_ideal"
        self.topic_ack = f"secado/{self.secador_id}/ack"

        self.client_id = f"sim_{self.secador_id}_{os.getpid()}"
        self.running = False
        self._thread: Optional[threading.Thread] = None

        # Instancia de cliente Paho MQTT v2
        self.client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=True,
        )

        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        # Configurar Last Will and Testament (LWT) retenido
        self.client.will_set(
            topic=self.topic_estado,
            payload="offline",
            qos=self.qos,
            retain=True,
        )

        # Reintento exponencial de reconexión
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

        # Callbacks de Paho MQTT v2
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info(f"[{self.secador_id}] Conectado al broker MQTT exitosamente (code {reason_code}).")
            # Publicar estado 'online' retenido
            self.client.publish(self.topic_estado, payload="online", qos=self.qos, retain=True)
            # Suscribirse al tópico de comandos de consigna
            self.client.subscribe(self.topic_cmd, qos=self.qos)
            logger.debug(f"[{self.secador_id}] Suscrito a comandos: {self.topic_cmd}")
        else:
            logger.error(f"[{self.secador_id}] Error al conectar al broker: {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        logger.warning(f"[{self.secador_id}] Desconectado del broker (reason_code: {reason_code}).")

    def _on_message(self, client, userdata, msg):
        """Maneja comandos entrantes en secado/<id_secador>/cmd/temp_ideal."""
        payload_str = msg.payload.decode("utf-8", errors="replace").strip()
        logger.info(f"[{self.secador_id}] Comando recibido en {msg.topic}: '{payload_str}'")

        try:
            # Intento de parseo (puede ser número directo o JSON {"t_ideal": 42.0})
            if payload_str.startswith("{"):
                datos = json.loads(payload_str)
                nuevo_valor = datos.get("t_ideal", datos.get("temp_ideal"))
            else:
                nuevo_valor = float(payload_str)

            valido, detalle = self.modelo.set_temp_ideal(nuevo_valor)

            if valido:
                logger.info(f"[{self.secador_id}] Consigna de temperatura actualizada a {nuevo_valor} °C.")
                ack_payload = {
                    "secador_id": self.secador_id,
                    "status": "ok",
                    "t_ideal": float(nuevo_valor),
                    "ts": get_iso8601_utc(),
                    "mensaje": "Consigna actualizada exitosamente",
                }
            else:
                logger.warning(f"[{self.secador_id}] Consigna rechazada: {detalle}")
                ack_payload = {
                    "secador_id": self.secador_id,
                    "status": "error",
                    "valor_rechazado": nuevo_valor,
                    "ts": get_iso8601_utc(),
                    "mensaje": detalle,
                }
        except Exception as e:
            logger.error(f"[{self.secador_id}] Error procesando comando: {e}")
            ack_payload = {
                "secador_id": self.secador_id,
                "status": "error",
                "ts": get_iso8601_utc(),
                "mensaje": f"Formato inválido: {str(e)}",
            }

        self.client.publish(self.topic_ack, payload=json.dumps(ack_payload), qos=self.qos)

    def iniciar(self, offset_arranque_segundos: float = 0.0):
        """Inicia el bucle de simulación en un hilo independiente con arranque escalonado."""
        self.running = True
        self._thread = threading.Thread(
            target=self._bucle_simulacion,
            args=(offset_arranque_segundos,),
            name=f"Thread-{self.secador_id}",
            daemon=True,
        )
        self._thread.start()

    def _bucle_simulacion(self, offset_arranque: float):
        if offset_arranque > 0:
            time.sleep(offset_arranque)

        conectado = False
        while self.running and not conectado:
            try:
                logger.info(f"[{self.secador_id}] Conectando a {self.broker_host}:{self.broker_port}...")
                self.client.connect(self.broker_host, self.broker_port, keepalive=60)
                self.client.loop_start()
                conectado = True
            except Exception as e:
                logger.warning(f"[{self.secador_id}] Error conectando al broker: {e}. Reintentando en 2s...")
                time.sleep(2.0)

        while self.running:
            # Si se forzó desconexión abrupta para prueba de LWT
            if self.modelo.falla_forzada == "desconexion":
                logger.warning(f"[{self.secador_id}] Simulando caída abrupta (LWT test)...")
                # Detener loop sin enviar disconnect para que el broker dispare el LWT
                self.client.loop_stop()
                try:
                    self.client._sock.close()
                except Exception:
                    pass
                break

            paso = self.modelo.simular_paso(delta_t_segundos=self.intervalo_pub)

            mensaje_telemetria = {
                "id": self.secador_id,
                "ts": get_iso8601_utc(),
                "t_amb": paso["t_amb"],
                "hum": paso["hum"],
                "t_grano": paso["t_grano"],
                "t_ideal": paso["t_ideal"],
                "led": paso["led"],
                "ventilador_pwm": paso["ventilador_pwm"],
            }

            payload_json = json.dumps(mensaje_telemetria)
            try:
                info = self.client.publish(self.topic_telemetria, payload=payload_json, qos=self.qos)
                if info.rc != mqtt.MQTT_ERR_SUCCESS:
                    logger.warning(f"[{self.secador_id}] Fallo al publicar telemetría (rc={info.rc})")
                else:
                    logger.debug(f"[{self.secador_id}] Pub -> {payload_json}")
            except Exception as e:
                logger.warning(f"[{self.secador_id}] Excepción publicando telemetría: {e}")

            time.sleep(self.intervalo_pub)

    def detener(self):
        """Detiene de forma limpia el secador publicando estado 'offline'."""
        self.running = False
        if self.client.is_connected():
            logger.info(f"[{self.secador_id}] Marcando estado offline y cerrando conexión...")
            # Publicación de offline retenido antes de desconexión limpia
            self.client.publish(self.topic_estado, payload="offline", qos=self.qos, retain=True)
            time.sleep(0.1)
            self.client.disconnect()
        self.client.loop_stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)


class GestorSimulacion:
    """Gestiona la flota de N secadores virtuales."""

    def __init__(
        self,
        n_secadores: int = 5,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
        intervalo_pub: float = 2.0,
        t_ideal_inicial: float = 38.0,
        inyectar_fallas: bool = False,
    ):
        self.n_secadores = n_secadores
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.username = username
        self.password = password
        self.intervalo_pub = intervalo_pub
        self.t_ideal_inicial = t_ideal_inicial
        self.inyectar_fallas = inyectar_fallas
        self.secadores: List[SecadorVirtual] = []
        self._running = False

    def iniciar(self):
        self._running = True
        logger.info(f"Iniciando simulación de {self.n_secadores} secadores hacia {self.broker_host}:{self.broker_port}...")

        # Arranque escalonado distribuido en el intervalo de publicación
        paso_escalon = self.intervalo_pub / max(1, self.n_secadores)

        for i in range(1, self.n_secadores + 1):
            sec_id = f"secador_{i:02d}"
            secador = SecadorVirtual(
                secador_id=sec_id,
                broker_host=self.broker_host,
                broker_port=self.broker_port,
                username=self.username,
                password=self.password,
                qos=1,
                intervalo_pub=self.intervalo_pub,
                t_ideal_inicial=self.t_ideal_inicial,
                inyectar_fallas=self.inyectar_fallas,
            )
            self.secadores.append(secador)
            offset = (i - 1) * paso_escalon
            secador.iniciar(offset_arranque_segundos=offset)

        logger.info(f"Flota de {self.n_secadores} secadores arrancada exitosamente.")

    def detener(self):
        if not self._running:
            return
        logger.info("Deteniendo todos los secadores virtuales...")
        self._running = False
        for sec in self.secadores:
            sec.detener()
        logger.info("Todos los secadores han sido detenidos limpiamente.")


def main():
    parser = argparse.ArgumentParser(description="Simulador MQTT de secadores de café/cacao.")
    parser.add_argument("--n-secadores", type=int, default=int(os.getenv("N_SECADORES", 5)), help="Número de secadores virtuales")
    parser.add_argument("--host", type=str, default=os.getenv("MQTT_BROKER_HOST", "localhost"), help="Host del broker MQTT")
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_BROKER_PORT", 1883)), help="Puerto del broker MQTT")
    parser.add_argument("--user", type=str, default=os.getenv("MQTT_USER", None), help="Usuario MQTT")
    parser.add_argument("--password", type=str, default=os.getenv("MQTT_PASSWORD", None), help="Contraseña MQTT")
    parser.add_argument("--intervalo", type=float, default=float(os.getenv("INTERVALO_PUB_SEC", 2.0)), help="Intervalo de publicación en segundos")
    parser.add_argument("--temp-ideal", type=float, default=float(os.getenv("TEMP_IDEAL_DEFAULT", 38.0)), help="Temperatura ideal inicial")
    parser.add_argument("--fallas", action="store_true", default=os.getenv("INYECTAR_FALLAS", "false").lower() == "true", help="Inyectar fallas esporádicas")

    args = parser.parse_args()

    gestor = GestorSimulacion(
        n_secadores=args.n_secadores,
        broker_host=args.host,
        broker_port=args.port,
        username=args.user,
        password=args.password,
        intervalo_pub=args.intervalo,
        t_ideal_inicial=args.temp_ideal,
        inyectar_fallas=args.fallas,
    )

    def signal_handler(sig, frame):
        logger.info("Señal de interrupción recibida (Ctrl+C o SIGTERM).")
        gestor.detener()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    gestor.iniciar()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
