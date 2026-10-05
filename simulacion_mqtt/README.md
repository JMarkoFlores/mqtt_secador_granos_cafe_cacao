# Módulo de Simulación MQTT, Lógica Embebida y Persistencia

> **Aviso de Ubicación:** La orquestación completa del proyecto se ejecuta desde la raíz `IOT_Trabajo` mediante:
> ```bash
> cd ..
> docker compose up -d --build
> ```
> Consulte la documentación completa y detallada en [../README.md](../README.md).

---

## Contenido de esta Carpeta:
- `simulador.py`: Flota de secadores virtuales concurrentes con protocolo MQTT (paho-mqtt 2.x), Last Will and Testament, arranque escalonado y recepción de consignas con ACK.
- `suscriptor.py`: Servicio de persistencia resiliente hacia MySQL 8.0 con pool de conexiones, colas y aseguramiento idempotente del esquema.
- `logica_control.py`: Reproducción fiel del firmware Arduino Nano (umbrales $\le 0.8$, $0.8$–$2.2$, $> 2.2$ °C, PWM 0, 153, 255 y detección de fallas DS18B20 85.0 y -127.0).
- `modelo_fisico.py`: Modelo termodinámico de primer orden con inercia térmica, disipación por ventilador PWM y deriva ambiental estocástica.
- `app_visualizacion.py`: Dashboard interactivo desarrollado en Streamlit con gráficos de series de tiempo y actuador de consigna remota.
- `inspeccionar_mensajes.py`: CLI para monitoreo de tráfico MQTT en vivo.
- `schema.sql`: DDL relacional idempotente para MySQL.
- `Dockerfile.simulador`, `Dockerfile.suscriptor`, `Dockerfile.streamlit`: Definición de imágenes de contenedores ligeras basadas en `python:3.11-slim`.
- `tests/`: Batería de 28 pruebas automatizadas (`pytest`) unitarias y de integración contra broker y base de datos reales.
