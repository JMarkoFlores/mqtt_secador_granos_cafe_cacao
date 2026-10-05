"""
Pruebas de Integración para el Suscriptor y Persistencia en MySQL.
Verifica que las lecturas y eventos de estado enviados a MQTT se inserten
fielmente en la base de datos MySQL 'emqx_db'.
"""

import json
import os
import sys
import time
import pytest
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from suscriptor import GestorBaseDatos, SuscriptorPersistencia

BROKER_HOST = os.getenv("MQTT_BROKER_HOST", "127.0.0.1")
if BROKER_HOST == "emqx":
    BROKER_HOST = "127.0.0.1"
BROKER_PORT = int(os.getenv("MQTT_BROKER_PORT", 1883))
MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
if MYSQL_HOST == "mysql":
    MYSQL_HOST = "127.0.0.1"
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_DB = os.getenv("MYSQL_DB", "emqx_db")
MYSQL_USER = os.getenv("MYSQL_USER", "emqx_user")
MYSQL_PASS = os.getenv("MYSQL_PASSWORD", "emqx_pass")


class TestPersistenciaMySQL:

    def setup_method(self):
        self.db = GestorBaseDatos(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            database=MYSQL_DB,
            user=MYSQL_USER,
            password=MYSQL_PASS,
            pool_size=5,
        )
        self.db.inicializar_pool()
        self.db.asegurar_esquema()

    def test_persistencia_lectura_y_estado(self):
        """Verifica que un mensaje publicado en MQTT se inserte en MySQL."""
        suscriptor = SuscriptorPersistencia(
            broker_host=BROKER_HOST,
            broker_port=BROKER_PORT,
            db_gestor=self.db,
        )
        suscriptor.iniciar()
        time.sleep(1.0)

        publisher = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id="pub_test_persistencia",
            clean_session=True,
        )
        publisher.connect(BROKER_HOST, BROKER_PORT)

        sec_id = "secador_db_test_01"

        # 1. Publicar evento de estado
        publisher.publish(f"secado/{sec_id}/estado", payload="online", qos=1)

        # 2. Publicar lectura de telemetría válida
        payload_telemetria = {
            "id": sec_id,
            "ts": "2026-10-05T05:30:00.000Z",
            "t_amb": 27.5,
            "hum": 68.0,
            "t_grano": 34.0,
            "t_ideal": 38.0,
            "led": "A",
            "ventilador_pwm": 153,
        }
        publisher.publish(f"secado/{sec_id}/telemetria", payload=json.dumps(payload_telemetria), qos=1)

        # 3. Publicar mensaje malformado (debe ser descartado sin tumbar el servicio)
        publisher.publish(f"secado/{sec_id}/telemetria", payload="{corrupt_json:!!", qos=1)
        publisher.publish(f"secado/{sec_id}/telemetria", payload=json.dumps({"id": sec_id}), qos=1)

        # Esperar a que el hilo de persistencia procese
        time.sleep(2.0)

        # Verificar en base de datos
        conn = self.db.pool.get_connection()
        try:
            with conn.cursor(dictionary=True) as cursor:
                # Verificar secador registrado
                cursor.execute("SELECT * FROM secadores WHERE id = %s;", (sec_id,))
                sec = cursor.fetchone()
                assert sec is not None
                assert sec["id"] == sec_id

                # Verificar evento de estado registrado
                cursor.execute("SELECT * FROM eventos_estado WHERE secador_id = %s;", (sec_id,))
                eventos = cursor.fetchall()
                assert len(eventos) >= 1
                assert eventos[-1]["estado"] == "online"

                # Verificar lectura registrada
                cursor.execute("SELECT * FROM lecturas WHERE secador_id = %s;", (sec_id,))
                lecturas = cursor.fetchall()
                assert len(lecturas) >= 1
                lec = lecturas[-1]
                assert float(lec["t_amb"]) == 27.5
                assert float(lec["hum"]) == 68.0
                assert float(lec["t_grano"]) == 34.0
                assert float(lec["t_ideal"]) == 38.0
                assert lec["led"] == "A"
                assert lec["ventilador_pwm"] == 153
        finally:
            conn.close()
            suscriptor.detener()
            publisher.disconnect()
