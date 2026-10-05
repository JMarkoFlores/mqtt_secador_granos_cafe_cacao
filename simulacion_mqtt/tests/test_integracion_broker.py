"""
Pruebas de Integración contra el Broker Real EMQX (127.0.0.1:1883).
Verifica:
1. Recepción y validación de telemetría multi-secador en tiempo real.
2. Envío de consigna cmd/temp_ideal y recepción de ACK.
3. Desconexión abrupta y activación de Last Will and Testament (LWT) retenido.
"""

import json
import os
import sys
import time
import pytest
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from simulador import SecadorVirtual

BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "127.0.0.1")
if BROKER_HOST == "emqx":
    BROKER_HOST = "127.0.0.1"
BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", 1883))


class TestIntegracionBrokerReal:

    def test_recepcion_telemetria_multisecador(self):
        """Verifica que un suscriptor reciba telemetría de secadores distintos con JSON válido."""
        mensajes_recibidos = {}

        def on_message(client, userdata, msg):
            try:
                datos = json.loads(msg.payload.decode("utf-8"))
                sec_id = datos.get("id", "")
                if sec_id.startswith("secador_integ_"):
                    mensajes_recibidos[sec_id] = datos
            except Exception as e:
                print(f"Error parseando mensaje: {e}")

        # Cliente suscriptor de prueba
        sub_client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id="test_integ_sub",
            clean_session=True,
        )
        sub_client.on_message = on_message
        sub_client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
        sub_client.subscribe("secado/+/telemetria", qos=1)
        sub_client.loop_start()

        # Iniciar 3 secadores virtuales para el test
        secadores = []
        for i in range(1, 4):
            sec_id = f"secador_integ_{i:02d}"
            sec = SecadorVirtual(
                secador_id=sec_id,
                broker_host=BROKER_HOST,
                broker_port=BROKER_PORT,
                intervalo_pub=0.5,
                t_ideal_inicial=38.0,
            )
            secadores.append(sec)
            sec.iniciar()

        # Esperar hasta recibir mensajes de los 3 secadores (máximo 6 segundos)
        t_inicio = time.time()
        while len(mensajes_recibidos) < 3 and (time.time() - t_inicio) < 6.0:
            time.sleep(0.2)

        # Detener secadores y suscriptor
        for s in secadores:
            s.detener()
        sub_client.loop_stop()
        sub_client.disconnect()

        # Verificaciones
        assert len(mensajes_recibidos) == 3, f"Se esperaban 3 secadores, recibidos: {list(mensajes_recibidos.keys())}"
        for sec_id, datos in mensajes_recibidos.items():
            assert datos["id"] == sec_id
            assert "t_amb" in datos
            assert "hum" in datos
            assert "t_grano" in datos
            assert "t_ideal" in datos
            assert datos["led"] in ("V", "A", "R")
            assert datos["ventilador_pwm"] in (0, 153, 255)

    def test_comando_temp_ideal_y_ack(self):
        """Verifica que al enviar un comando a cmd/temp_ideal el secador responde con ACK."""
        sec_id = "secador_integ_cmd"
        sec = SecadorVirtual(
            secador_id=sec_id,
            broker_host=BROKER_HOST,
            broker_port=BROKER_PORT,
            intervalo_pub=1.0,
            t_ideal_inicial=35.0,
        )
        sec.iniciar()
        time.sleep(0.5)

        ack_recibidos = []

        def on_ack_message(client, userdata, msg):
            try:
                ack_datos = json.loads(msg.payload.decode("utf-8"))
                ack_recibidos.append(ack_datos)
            except Exception as e:
                print(f"Error ACK: {e}")

        test_client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id="test_cmd_ack_client",
            clean_session=True,
        )
        test_client.on_message = on_ack_message
        test_client.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
        test_client.subscribe(f"secado/{sec_id}/ack", qos=1)
        test_client.loop_start()

        time.sleep(0.5)

        # 1. Enviar comando válido (42.0)
        test_client.publish(f"secado/{sec_id}/cmd/temp_ideal", payload="42.0", qos=1)

        t_inicio = time.time()
        while len(ack_recibidos) == 0 and (time.time() - t_inicio) < 4.0:
            time.sleep(0.1)

        assert len(ack_recibidos) >= 1
        ack_valido = ack_recibidos[-1]
        assert ack_valido["status"] == "ok"
        assert ack_valido["t_ideal"] == 42.0
        assert sec.modelo.t_ideal == 42.0

        # 2. Enviar comando inválido fuera de rango (88.0)
        ack_recibidos.clear()
        test_client.publish(f"secado/{sec_id}/cmd/temp_ideal", payload="88.0", qos=1)

        t_inicio = time.time()
        while len(ack_recibidos) == 0 and (time.time() - t_inicio) < 4.0:
            time.sleep(0.1)

        assert len(ack_recibidos) >= 1
        ack_invalido = ack_recibidos[-1]
        assert ack_invalido["status"] == "error"
        assert "fuera de rango" in ack_invalido["mensaje"]

        sec.detener()
        test_client.loop_stop()
        test_client.disconnect()

    def test_last_will_testament(self):
        """Verifica que el broker publica Last Will ('offline') si un secador cae abruptamente."""
        sec_id = "secador_lwt_check"
        estados_recibidos = []

        def on_estado(client, userdata, msg):
            payload = msg.payload.decode("utf-8").strip()
            estados_recibidos.append(payload)

        monitor = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id="monitor_lwt",
            clean_session=True,
        )
        monitor.on_message = on_estado
        monitor.connect(BROKER_HOST, BROKER_PORT, keepalive=30)
        monitor.subscribe(f"secado/{sec_id}/estado", qos=1)
        monitor.loop_start()

        # Iniciar secador
        sec = SecadorVirtual(
            secador_id=sec_id,
            broker_host=BROKER_HOST,
            broker_port=BROKER_PORT,
            intervalo_pub=1.0,
        )
        sec.iniciar()

        # Esperar a recibir 'online'
        t_inicio = time.time()
        while "online" not in estados_recibidos and (time.time() - t_inicio) < 4.0:
            time.sleep(0.1)

        assert "online" in estados_recibidos

        # Provocar caída abrupta del socket (simula pérdida de energía o kernel panic)
        # Esto debe hacer que el broker dispare el LWT ('offline')
        estados_recibidos.clear()
        sec.modelo.falla_forzada = "desconexion"

        # Esperar a que el broker detecte el cierre del socket TCP y dispare el Last Will
        t_inicio = time.time()
        while "offline" not in estados_recibidos and (time.time() - t_inicio) < 6.0:
            time.sleep(0.2)

        assert "offline" in estados_recibidos

        monitor.loop_stop()
        monitor.disconnect()
