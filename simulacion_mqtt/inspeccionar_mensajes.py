"""
Script de Inspección de Mensajes MQTT en Vivo.
Permite visualizar la telemetría, estados y respuestas ACK formateadas en consola.

Uso equivalente con mosquitto_sub:
  mosquitto_sub -h localhost -p 1883 -t "secado/#" -v
"""

import argparse
import json
import os
import sys
import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

def main():
    parser = argparse.ArgumentParser(description="Monitor MQTT en vivo")
    parser.add_argument("--host", default=os.getenv("MQTT_BROKER_HOST", "localhost"), help="Host broker")
    parser.add_argument("--port", type=int, default=int(os.getenv("MQTT_BROKER_PORT", 1883)), help="Puerto broker")
    parser.add_argument("--topic", default="secado/#", help="Tópico o wildcard a suscribirse")
    args = parser.parse_args()

    def on_connect(client, userdata, flags, rc, properties):
        print(f"[*] Conectado al broker {args.host}:{args.port}")
        print(f"[*] Suscrito al tópico: '{args.topic}'")
        print("=" * 70)
        client.subscribe(args.topic, qos=1)

    def on_message(client, userdata, msg):
        topic = msg.topic
        try:
            payload_str = msg.payload.decode("utf-8")
            try:
                datos = json.loads(payload_str)
                formato = json.dumps(datos, indent=2, ensure_ascii=False)
                print(f"\n[MSG] Tópico: {topic} (QoS: {msg.qos}, Retain: {msg.retain})")
                print(formato)
            except json.JSONDecodeError:
                print(f"\n[MSG RAW] Tópico: {topic} -> {payload_str}")
        except Exception as e:
            print(f"[ERROR] Decodificando: {e}")

    client = mqtt.Client(callback_api_version=CallbackAPIVersion.VERSION2, client_id="cli_inspector")
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.host, args.port, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\n[*] Cerrando inspector.")
        client.disconnect()
        sys.exit(0)

if __name__ == "__main__":
    main()
