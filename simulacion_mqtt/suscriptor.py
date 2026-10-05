"""
Servicio Suscriptor y Persistencia MQTT hacia MySQL para Secadores de Granos.
Utiliza paho-mqtt 2.x (CallbackAPIVersion.VERSION2) y mysql-connector-python con pool.

Tópicos suscritos:
- secado/+/telemetria : Inserción en tabla 'lecturas'
- secado/+/estado     : Inserción en tabla 'eventos_estado'
"""

import argparse
import datetime
import json
import logging
import os
import queue
import signal
import sys
import threading
import time
from typing import Optional

import mysql.connector
from mysql.connector import pooling
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

# Configuración de logging estándar
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("SuscriptorMQTT")


def parsear_ts(ts_str: str) -> str:
    """
    Convierte una cadena de timestamp ISO8601 a formato compatible con MySQL DATETIME(3):
    'YYYY-MM-DD HH:MM:SS.mmm'
    """
    if not ts_str:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    try:
        # Remover 'Z' si está presente y parsear
        limpio = ts_str.replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(limpio)
        # Convertir a UTC si tiene timezone
        if dt.tzinfo is not None:
            dt = dt.astimezone(datetime.timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


class GestorBaseDatos:
    """Administra el pool de conexiones y las operaciones relacionales en MySQL."""

    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        pool_size: int = 10,
    ):
        self.host = host
        self.port = port
        self.database = database
        self.user = user
        self.password = password
        self.pool_size = pool_size
        self.pool: Optional[pooling.MySQLConnectionPool] = None
        self.secadores_registrados = set()

    def inicializar_pool(self, max_reintentos: int = 15, espera_segundos: int = 2):
        """Intenta conectar a MySQL y crear el pool con reintentos."""
        for intento in range(1, max_reintentos + 1):
            try:
                logger.info(f"Conectando a MySQL ({self.host}:{self.port}/{self.database}), intento {intento}/{max_reintentos}...")
                self.pool = pooling.MySQLConnectionPool(
                    pool_name="pool_secado",
                    pool_size=self.pool_size,
                    pool_reset_session=True,
                    host=self.host,
                    port=self.port,
                    database=self.database,
                    user=self.user,
                    password=self.password,
                    autocommit=True,
                    charset="utf8mb4",
                )
                logger.info("Pool de conexiones MySQL inicializado exitosamente.")
                return
            except mysql.connector.Error as err:
                logger.warning(f"Error conectando a MySQL: {err}. Reintentando en {espera_segundos}s...")
                time.sleep(espera_segundos)

        raise ConnectionError(f"No se pudo conectar a MySQL tras {max_reintentos} intentos.")

    def asegurar_esquema(self):
        """Crea las tablas necesarias en MySQL de forma idempotente."""
        ddl_statements = [
            """
            CREATE TABLE IF NOT EXISTS secadores (
                id VARCHAR(50) NOT NULL PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                ubicacion VARCHAR(100) DEFAULT 'Módulo Central',
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            """
            CREATE TABLE IF NOT EXISTS lecturas (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                secador_id VARCHAR(50) NOT NULL,
                ts DATETIME(3) NOT NULL,
                t_amb DECIMAL(5, 2) NOT NULL,
                hum DECIMAL(5, 2) NOT NULL,
                t_grano DECIMAL(5, 2) NOT NULL,
                t_ideal DECIMAL(5, 2) NOT NULL,
                led CHAR(1) NOT NULL,
                ventilador_pwm INT NOT NULL,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_lecturas_secador FOREIGN KEY (secador_id)
                    REFERENCES secadores (id) ON DELETE CASCADE,
                INDEX idx_secador_ts (secador_id, ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
            """
            CREATE TABLE IF NOT EXISTS eventos_estado (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                secador_id VARCHAR(50) NOT NULL,
                ts DATETIME(3) NOT NULL,
                estado VARCHAR(20) NOT NULL,
                creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                CONSTRAINT fk_eventos_secador FOREIGN KEY (secador_id)
                    REFERENCES secadores (id) ON DELETE CASCADE,
                INDEX idx_estado_secador_ts (secador_id, ts)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """,
        ]
        conn = None
        try:
            conn = self.pool.get_connection()
            with conn.cursor() as cursor:
                for ddl in ddl_statements:
                    cursor.execute(ddl)
            logger.info("Esquema relacional verificado/creado exitosamente en MySQL.")
        except Exception as e:
            logger.error(f"Error asegurando el esquema de base de datos: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def registrar_secador_si_no_existe(self, secador_id: str):
        """Inserta el secador en la tabla maestra 'secadores' de forma idempotente con caché."""
        if secador_id in self.secadores_registrados:
            return

        query = """
            INSERT INTO secadores (id, nombre, ubicacion)
            VALUES (%s, %s, %s)
            ON DUPLICATE KEY UPDATE id = id;
        """
        conn = None
        try:
            conn = self.pool.get_connection()
            with conn.cursor() as cursor:
                nombre = f"Unidad {secador_id.replace('_', ' ').capitalize()}"
                cursor.execute(query, (secador_id, nombre, "Secadora Automatizada"))
            self.secadores_registrados.add(secador_id)
        except Exception as e:
            logger.error(f"Error registrando secador {secador_id}: {e}")
        finally:
            if conn:
                conn.close()

    def insertar_lectura(self, lectura: dict):
        """Inserta un registro de telemetría en la tabla 'lecturas'."""
        query = """
            INSERT INTO lecturas (
                secador_id, ts, t_amb, hum, t_grano, t_ideal, led, ventilador_pwm
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        """
        conn = None
        try:
            self.registrar_secador_si_no_existe(lectura["id"])
            conn = self.pool.get_connection()
            with conn.cursor() as cursor:
                valores = (
                    lectura["id"],
                    parsear_ts(lectura.get("ts")),
                    lectura["t_amb"],
                    lectura["hum"],
                    lectura["t_grano"],
                    lectura["t_ideal"],
                    lectura["led"],
                    lectura["ventilador_pwm"],
                )
                cursor.execute(query, valores)
        except Exception as e:
            logger.error(f"Error insertando lectura de {lectura.get('id')}: {e}")
        finally:
            if conn:
                conn.close()

    def insertar_evento_estado(self, secador_id: str, estado: str):
        """Inserta un evento de estado (online/offline) en la tabla 'eventos_estado'."""
        query = """
            INSERT INTO eventos_estado (secador_id, ts, estado)
            VALUES (%s, %s, %s);
        """
        conn = None
        try:
            self.registrar_secador_si_no_existe(secador_id)
            conn = self.pool.get_connection()
            with conn.cursor() as cursor:
                ts_actual = parsear_ts(None)
                cursor.execute(query, (secador_id, ts_actual, estado))
        except Exception as e:
            logger.error(f"Error insertando evento de estado de {secador_id}: {e}")
        finally:
            if conn:
                conn.close()


class SuscriptorPersistencia:
    """Servicio que escucha tópicos MQTT y encola mensajes para persistencia."""

    def __init__(
        self,
        broker_host: str,
        broker_port: int,
        db_gestor: GestorBaseDatos,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.db = db_gestor
        self.username = username
        self.password = password

        self.cola_mensajes = queue.Queue(maxsize=10000)
        self.running = False
        self._hilo_persistencia: Optional[threading.Thread] = None

        self.client_id = f"suscriptor_bd_{os.getpid()}"
        self.client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            clean_session=False,  # Sesión persistente para no perder mensajes
        )

        if self.username and self.password:
            self.client.username_pw_set(self.username, self.password)

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info("Suscriptor conectado exitosamente al broker MQTT.")
            # Suscripción con wildcards
            self.client.subscribe("secado/+/telemetria", qos=1)
            self.client.subscribe("secado/+/estado", qos=1)
            logger.info("Suscrito a: 'secado/+/telemetria' y 'secado/+/estado'")
        else:
            logger.error(f"Fallo al conectar al broker: reason_code={reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        logger.warning(f"Suscriptor desconectado del broker MQTT (code: {reason_code})")

    def _on_message(self, client, userdata, msg):
        """Recepción de mensajes MQTT; validación y encolado rápido."""
        topic = msg.topic
        payload_bytes = msg.payload
        try:
            payload_str = payload_bytes.decode("utf-8")
        except UnicodeDecodeError:
            logger.warning(f"Mensaje descartado por codificación UTF-8 inválida en {topic}")
            return

        partes = topic.split("/")
        if len(partes) != 3 or partes[0] != "secado":
            logger.warning(f"Tópico no reconocido: {topic}")
            return

        secador_id = partes[1]
        tipo = partes[2]

        if tipo == "telemetria":
            try:
                datos = json.loads(payload_str)
                # Validar campos requeridos
                campos_obligatorios = ["id", "t_amb", "hum", "t_grano", "t_ideal", "led", "ventilador_pwm"]
                if not all(c in datos for c in campos_obligatorios):
                    logger.warning(f"Telemetría descartada por campos faltantes: {payload_str}")
                    return
                # Validar tipos
                datos["t_amb"] = float(datos["t_amb"])
                datos["hum"] = float(datos["hum"])
                datos["t_grano"] = float(datos["t_grano"])
                datos["t_ideal"] = float(datos["t_ideal"])
                datos["ventilador_pwm"] = int(datos["ventilador_pwm"])
                datos["led"] = str(datos["led"])[:1]

                self.cola_mensajes.put(("telemetria", datos))
            except (json.JSONDecodeError, ValueError) as err:
                logger.warning(f"Telemetría malformada descartada en {topic}: {err} | Raw: {payload_str}")

        elif tipo == "estado":
            estado = payload_str.strip().lower()
            if estado in ("online", "offline"):
                self.cola_mensajes.put(("estado", (secador_id, estado)))
            else:
                logger.warning(f"Estado desconocido ignorado para {secador_id}: '{estado}'")

    def iniciar(self, max_reintentos: int = 15, espera_segundos: int = 2):
        """Inicia el servicio suscriptor y el hilo consumidor de persistencia con reintentos."""
        self.running = True
        self._hilo_persistencia = threading.Thread(
            target=self._bucle_persistencia,
            name="Hilo-Persistencia-DB",
            daemon=True,
        )
        self._hilo_persistencia.start()

        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

        conectado = False
        for intento in range(1, max_reintentos + 1):
            try:
                logger.info(f"Conectando suscriptor a {self.broker_host}:{self.broker_port} (intento {intento}/{max_reintentos})...")
                self.client.connect(self.broker_host, self.broker_port, keepalive=60)
                self.client.loop_start()
                conectado = True
                break
            except Exception as e:
                logger.warning(f"Error conectando suscriptor al broker: {e}. Reintentando en {espera_segundos}s...")
                time.sleep(espera_segundos)

        if not conectado:
            raise ConnectionError(f"No fue posible conectar al broker MQTT tras {max_reintentos} intentos.")

    def _bucle_persistencia(self):
        """Consume mensajes de la cola y los persiste en MySQL."""
        logger.info("Hilo de persistencia iniciado.")
        while self.running or not self.cola_mensajes.empty():
            try:
                tipo, contenido = self.cola_mensajes.get(timeout=1.0)
            except queue.Empty:
                continue

            try:
                if tipo == "telemetria":
                    self.db.insertar_lectura(contenido)
                elif tipo == "estado":
                    sec_id, est = contenido
                    self.db.insertar_evento_estado(sec_id, est)
            except Exception as e:
                logger.error(f"Error procesando guardado en BD: {e}")
            finally:
                self.cola_mensajes.task_done()

    def detener(self):
        """Detiene de forma limpia el cliente MQTT y vacía la cola."""
        logger.info("Deteniendo servicio suscriptor...")
        self.running = False
        self.client.disconnect()
        self.client.loop_stop()
        if self._hilo_persistencia and self._hilo_persistencia.is_alive():
            self._hilo_persistencia.join(timeout=3.0)
        logger.info("Suscriptor detenido exitosamente.")


def main():
    parser = argparse.ArgumentParser(description="Suscriptor MQTT y Persistencia a MySQL.")
    parser.add_argument("--broker-host", type=str, default=os.getenv("MQTT_BROKER_HOST", "localhost"), help="Host del broker MQTT")
    parser.add_argument("--broker-port", type=int, default=int(os.getenv("MQTT_BROKER_PORT", 1883)), help="Puerto del broker MQTT")
    parser.add_argument("--broker-user", type=str, default=os.getenv("MQTT_USER", None), help="Usuario MQTT")
    parser.add_argument("--broker-pass", type=str, default=os.getenv("MQTT_PASSWORD", None), help="Clave MQTT")

    parser.add_argument("--db-host", type=str, default=os.getenv("MYSQL_HOST", "localhost"), help="Host MySQL")
    parser.add_argument("--db-port", type=int, default=int(os.getenv("MYSQL_PORT", 3306)), help="Puerto MySQL")
    parser.add_argument("--db-name", type=str, default=os.getenv("MYSQL_DB", "emqx_db"), help="Nombre base de datos")
    parser.add_argument("--db-user", type=str, default=os.getenv("MYSQL_USER", "emqx_user"), help="Usuario MySQL")
    parser.add_argument("--db-pass", type=str, default=os.getenv("MYSQL_PASSWORD", "emqx_pass"), help="Clave MySQL")
    parser.add_argument("--pool-size", type=int, default=int(os.getenv("MYSQL_POOL_SIZE", 10)), help="Tamaño del pool")

    args = parser.parse_args()

    db_gestor = GestorBaseDatos(
        host=args.db_host,
        port=args.db_port,
        database=args.db_name,
        user=args.db_user,
        password=args.db_pass,
        pool_size=args.pool_size,
    )

    try:
        db_gestor.inicializar_pool()
        db_gestor.asegurar_esquema()
    except Exception as e:
        logger.critical(f"No fue posible conectar o preparar la base de datos: {e}")
        sys.exit(1)

    suscriptor = SuscriptorPersistencia(
        broker_host=args.broker_host,
        broker_port=args.broker_port,
        db_gestor=db_gestor,
        username=args.broker_user,
        password=args.broker_pass,
    )

    def signal_handler(sig, frame):
        logger.info("Interrupción recibida, cerrando suscriptor...")
        suscriptor.detener()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    suscriptor.iniciar()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(None, None)


if __name__ == "__main__":
    main()
