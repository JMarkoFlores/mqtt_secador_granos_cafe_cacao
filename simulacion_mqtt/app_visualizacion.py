"""
Panel de Visualización y Control en Tiempo Real para Secadores de Granos.
Desarrollado con Streamlit. Lee telemetría histórica de MySQL y permite enviar consignas MQTT.
"""

import os
import json
import time
import pandas as pd
import streamlit as st
import mysql.connector
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

# Configuración de página
st.set_page_config(
    page_title="Monitor Secadores IoT",
    page_icon="☕",
    layout="wide",
)

# Parámetros desde variables de entorno
DB_HOST = os.getenv("MYSQL_HOST", "localhost")
DB_PORT = int(os.getenv("MYSQL_PORT", 3306))
DB_NAME = os.getenv("MYSQL_DB", "emqx_db")
DB_USER = os.getenv("MYSQL_USER", "emqx_user")
DB_PASS = os.getenv("MYSQL_PASSWORD", "emqx_pass")

MQTT_HOST = os.getenv("MQTT_BROKER_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_BROKER_PORT", 1883))


def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASS,
        connect_timeout=3,
    )


def cargar_secadores():
    try:
        conn = get_db_connection()
        query = "SELECT DISTINCT secador_id FROM lecturas ORDER BY secador_id;"
        df = pd.read_sql(query, conn)
        conn.close()
        return df["secador_id"].tolist()
    except Exception:
        return []


def cargar_lecturas(secador_id, limite=100):
    try:
        conn = get_db_connection()
        query = """
            SELECT ts, t_amb, hum, t_grano, t_ideal, led, ventilador_pwm
            FROM lecturas
            WHERE secador_id = %s
            ORDER BY ts DESC
            LIMIT %s;
        """
        df = pd.read_sql(query, conn, params=(secador_id, limite))
        conn.close()
        df = df.sort_values(by="ts", ascending=True)
        return df
    except Exception as e:
        st.error(f"Error cargando lecturas: {e}")
        return pd.DataFrame()


def enviar_consigna_mqtt(secador_id, temp_ideal):
    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id="streamlit_control")
    try:
        client.connect(MQTT_HOST, MQTT_PORT, keepalive=10)
        topic = f"secado/{secador_id}/cmd/temp_ideal"
        client.publish(topic, payload=str(temp_ideal), qos=1)
        client.disconnect()
        return True, "Comando MQTT enviado exitosamente."
    except Exception as e:
        return False, f"Fallo al enviar comando MQTT: {e}"


# Interfaz Gráfica
st.title("☕ Sistema IoT de Supervisión de Secadores de Café / Cacao")
st.markdown("Virtualización y Monitoreo Multi-Sensor bajo protocolo MQTT y Base de Datos MySQL.")

# Sidebar de selección y control
st.sidebar.header("Configuración y Filtros")
secadores_disponibles = cargar_secadores()

if not secadores_disponibles:
    st.sidebar.warning("Esperando telemetría en MySQL...")
    secador_seleccionado = "secador_01"
else:
    secador_seleccionado = st.sidebar.selectbox("Seleccione Secador:", secadores_disponibles)

# Control de Consigna
st.sidebar.subheader("Ajustar Consigna (ML / Operador)")
nueva_consigna = st.sidebar.slider("Temperatura Ideal (°C):", min_value=10.0, max_value=50.0, value=38.0, step=0.5)
if st.sidebar.button("Enviar Nueva Consigna"):
    exito, msg = enviar_consigna_mqtt(secador_seleccionado, nueva_consigna)
    if exito:
        st.sidebar.success(msg)
    else:
        st.sidebar.error(msg)

# Opciones de visualización
st.sidebar.subheader("Opciones de Pantalla")
auto_refresh = st.sidebar.checkbox("Refresco automático (cada 2 s)", value=True)

# Cargar datos del secador seleccionado
df_lecturas = cargar_lecturas(secador_seleccionado, limite=60)

if not df_lecturas.empty:
    ultima = df_lecturas.iloc[-1]
    diff = abs(ultima["t_grano"] - ultima["t_ideal"])

    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("T. Grano (DS18B20)", f"{ultima['t_grano']:.2f} °C", delta=f"{ultima['t_grano'] - ultima['t_ideal']:.2f} vs Ideal")
    col2.metric("T. Ideal", f"{ultima['t_ideal']:.2f} °C")
    col3.metric("T. Ambiente (DHT)", f"{ultima['t_amb']:.2f} °C")
    col4.metric("Humedad Relativa", f"{ultima['hum']:.1f} %")

    # Mapeo de semáforo
    color_map = {"V": "🟢 Verde (Óptimo)", "A": "🟡 Amarillo (Precaución)", "R": "🔴 Rojo (Crítico)"}
    col5.metric("Semáforo & Vent.", color_map.get(ultima["led"], ultima["led"]), f"PWM {ultima['ventilador_pwm']}")

    st.subheader(f"Evolución Térmica en Vivo: {secador_seleccionado}")
    chart_data = df_lecturas.set_index("ts")[["t_grano", "t_ideal", "t_amb"]]
    st.line_chart(chart_data)

    st.subheader(f"Actuación del Ventilador (PWM: 0 = 0%, 153 = 60%, 255 = 100%)")
    st.area_chart(df_lecturas.set_index("ts")[["ventilador_pwm"]])

    with st.expander("Ver últimas lecturas en crudo"):
        st.dataframe(df_lecturas.tail(15))
else:
    st.info("Aún no se registran datos para la unidad seleccionada.")

if st.button("Actualizar Vista"):
    st.rerun()

if auto_refresh:
    time.sleep(2)
    st.rerun()
