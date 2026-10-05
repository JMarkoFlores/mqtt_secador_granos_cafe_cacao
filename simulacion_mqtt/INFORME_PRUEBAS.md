# Informe de Pruebas y Evidencias de Verificación de Punta a Punta

> **Aviso:** El informe completo, actualizado y con la evidencia real de todas las pruebas (Pruebas A a H) se encuentra en la raíz del proyecto:
> [../INFORME_PRUEBAS.md](../INFORME_PRUEBAS.md)

### Resumen de Resultados Verificados:
- **Prueba A (Arranque con 1 comando):** `docker compose up -d --build` levanta los 6 servicios en el orden correcto. Idempotencia y prueba limpia con `-p prueba` superadas exitosamente.
- **Prueba B (Pytest):** 28 de 28 pruebas pasadas (unitarias, umbrales 0.8 / 2.2 °C, hardware DS18B20 85.0/-127.0 °C, convergencia del modelo y formato ISO8601 UTC 'Z').
- **Prueba C (Integración Broker):** Telemetría multi-secador, consignas y confirmación ACK, y Last Will and Testament retenido al desconectar.
- **Prueba D (Base de Datos):** Tasa medida de 0.514 lecturas/segundo por secador (exactamente 1 lectura cada 2 s). Cero nulos.
- **Prueba E (Broker EMQX CLI):** Todos los secadores virtuales y el suscriptor registrados y conectados con sesiones persistentes.
- **Prueba F (Escalabilidad N=20 durante 60 s):** 600 mensajes publicados, 600 entregados y 600 insertados en MySQL (0.0 % de pérdida en régimen estacionario).
- **Prueba G (Interfaces Web):** HTTP 200 en EMQX (18083), phpMyAdmin (8080) y Streamlit (8501).
- **Prueba H (Resiliencia):** Reconexión automática de simulador y suscriptor tras `docker compose restart emqx`.
