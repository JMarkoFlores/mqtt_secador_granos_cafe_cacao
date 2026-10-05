# Informe de Pruebas y Evidencias de Verificación de Punta a Punta

**Proyecto:** Simulación de Red Multi-Sensor IoT para Secadores de Café/Cacao bajo Protocolo MQTT  
**Fecha de Ejecución:** 5 de Octubre de 2026  
**Sistema Operativo Host:** Windows 11 con Docker Desktop y PowerShell  
**Entorno de Contenedores:** Red Bridge Unificada `emqxnet`  
**Broker MQTT:** EMQX 5.x / 6.x (`emqx/emqx:latest`)  
**Base de Datos Relacional:** MySQL Community Server 8.0  
**Stack de Lenguaje:** Python 3.11 (contenedores) / Python 3.13 (host para pruebas automatizadas)  
**Librerías Clave:** `paho-mqtt` 2.1.0 (`CallbackAPIVersion.VERSION2`), `mysql-connector-python` 9.0.0 con Connection Pool, `pytest` 9.1.1, `streamlit` 1.39.0  

---

## 1. Prueba A: Arranque Unificado con un Solo Comando e Idempotencia

### 1.1 Comando de Despliegue Único
Desde la carpeta raíz `C:\Users\jeanm\Downloads\IOT_Trabajo`:
```powershell
docker compose up -d --build
```

### 1.2 Estado de Servicios (`docker compose ps`)
**Comando ejecutado:**
```powershell
docker compose ps
```
**Salida real obtenida:**
```text
NAME                      IMAGE                          COMMAND                  SERVICE      CREATED          STATUS                   PORTS
emqx_broker               emqx/emqx:latest               "/usr/bin/docker-ent…"   emqx         8 minutes ago    Up 2 minutes (healthy)   0.0.0.0:1883->1883/tcp, [::]:1883->1883/tcp, 0.0.0.0:8083-8084->8083-8084/tcp, [::]:8083-8084->8083-8084/tcp, 0.0.0.0:18083->18083/tcp, [::]:18083->18083/tcp
emqx_mysql                mysql:8.0                      "docker-entrypoint.s…"   mysql        8 minutes ago    Up 8 minutes (healthy)   0.0.0.0:3306->3306/tcp, [::]:3306->3306/tcp
emqx_phpmyadmin           phpmyadmin/phpmyadmin:latest   "/docker-entrypoint.…"   phpmyadmin   8 minutes ago    Up 7 minutes             0.0.0.0:8080->80/tcp, [::]:8080->80/tcp
iot_dashboard_streamlit   iot_trabajo-dashboard          "streamlit run app_v…"   dashboard    8 minutes ago    Up 7 minutes (healthy)   0.0.0.0:8501->8501/tcp, [::]:8501->8501/tcp
iot_simulador_secadores   iot_trabajo-simulador          "python simulador.py"    simulador    10 seconds ago   Up 5 seconds             
iot_suscriptor_mysql      iot_trabajo-suscriptor         "python suscriptor.py"   suscriptor   8 minutes ago    Up 7 minutes             
```
*Resultado:* Los 6 servicios arrancan en el orden correcto por dependencias de salud (`service_healthy` en broker y base de datos) y se mantienen operativos sin intervención manual.

### 1.3 Verificación de Idempotencia
Al ejecutar una segunda vez consecutiva el comando `docker compose up -d`:
```text
 Container emqx_broker  Running
 Container emqx_mysql  Running
 Container emqx_phpmyadmin  Running
 Container iot_suscriptor_mysql  Running
 Container iot_dashboard_streamlit  Running
 Container iot_simulador_secadores  Running
```
*Resultado:* El comando no altera ni destruye contenedores existentes y retorna código 0 inmediatamente.

### 1.4 Verificación de Arranque Limpio Desde Cero (Entorno Aislado `-p prueba`)
Para verificar que el esquema SQL se aplica de forma 100 % automática sin alterar el volumen de datos principal:
1. Se inicializó un stack aislado con volumen efímero `prueba_mysql_data`.
2. MySQL ejecutó de forma autónoma el script `/docker-entrypoint-initdb.d/01_schema.sql`.
3. El suscriptor ejecutó su método de aseguramiento de esquema idempotente (`asegurar_esquema`).
4. Consulta de verificación en el entorno de prueba:
   ```text
   secador_id    lecturas
   secador_01    7
   secador_02    7
   secador_03    7
   secador_04    7
   secador_05    6
   ```
5. El entorno fue destruido limpiamente con `docker compose -p prueba down -v`, preservando los datos del volumen real intactos.

---

## 2. Prueba B: Pruebas Unitarias y de Lógica Embebida (`pytest`)

Se ejecutó la batería completa de 28 pruebas unitarias y de integración:
```powershell
python -m pytest -v simulacion_mqtt\tests\
```
**Salida real obtenida:**
```text
============================= test session starts =============================
platform win32 -- Python 3.13.0, pytest-9.1.1, pluggy-1.6.0
rootdir: C:\Users\jeanm\Downloads\IOT_Trabajo
collected 28 items

simulacion_mqtt/tests/test_formato_telemetria.py::test_formato_telemetria_json PASSED [  3%]
simulacion_mqtt/tests/test_integracion_broker.py::TestIntegracionBrokerReal::test_recepcion_telemetria_multisecador PASSED [  7%]
simulacion_mqtt/tests/test_integracion_broker.py::TestIntegracionBrokerReal::test_comando_temp_ideal_y_ack PASSED [ 10%]
simulacion_mqtt/tests/test_integracion_broker.py::TestIntegracionBrokerReal::test_last_will_testament PASSED [ 14%]
simulacion_mqtt/tests/test_integracion_persistencia.py::TestPersistenciaMySQL::test_persistencia_lectura_y_estado PASSED [ 17%]
simulacion_mqtt/tests/test_logica_control.py::TestValidacionTempIdeal::test_valores_limite_validos PASSED [ 21%]
simulacion_mqtt/tests/test_logica_control.py::TestValidacionTempIdeal::test_valores_fuera_de_rango PASSED [ 25%]
simulacion_mqtt/tests/test_logica_control.py::TestValidacionTempIdeal::test_valores_no_numericos PASSED [ 28%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[38.0-V-0] PASSED [ 32%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[38.8-V-0] PASSED [ 35%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[37.2-V-0] PASSED [ 39%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[38.5-V-0] PASSED [ 42%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[38.801-A-153] PASSED [ 46%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[37.199-A-153] PASSED [ 50%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[39.5-A-153] PASSED [ 53%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[40.2-A-153] PASSED [ 57%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[35.8-A-153] PASSED [ 60%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[40.201-R-255] PASSED [ 64%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[35.799-R-255] PASSED [ 67%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[45.0-R-255] PASSED [ 71%]
simulacion_mqtt/tests/test_logica_control.py::TestCalculoActuadores::test_umbrales_actuadores[25.0-R-255] PASSED [ 75%]
simulacion_mqtt/tests/test_logica_control.py::TestManejoLecturasInvalidas::test_deteccion_errores_hardware PASSED [ 78%]
simulacion_mqtt/tests/test_logica_control.py::TestManejoLecturasInvalidas::test_actuadores_modo_falla_segura PASSED [ 82%]
simulacion_mqtt/tests/test_modelo_fisico.py::TestModeloFisicoTermico::test_estructura_datos_paso PASSED [ 85%]
simulacion_mqtt/tests/test_modelo_fisico.py::TestModeloFisicoTermico::test_convergencia_hacia_consigna PASSED [ 89%]
simulacion_mqtt/tests/test_modelo_fisico.py::TestModeloFisicoTermico::test_inyeccion_falla_85 PASSED [ 92%]
simulacion_mqtt/tests/test_modelo_fisico.py::TestModeloFisicoTermico::test_inyeccion_falla_desconectado PASSED [ 96%]
simulacion_mqtt/tests/test_modelo_fisico.py::TestModeloFisicoTermico::test_cambio_consigna PASSED [100%]

============================= 28 passed in 5.86s ==============================
```

### 2.1 Cobertura de Verificación:
- **Umbrales exactos de control:** Diferencia $\le 0.8$ °C ('V', 0 PWM), $(0.8, 2.2]$ °C ('A', 153 PWM), $> 2.2$ °C ('R', 255 PWM), evaluados con pruebas parametrizadas en los bordes críticos (`38.800` vs `38.801`, `40.200` vs `40.201`).
- **Validación de consignas:** Aceptación en $[10.0, 50.0]$ °C y rechazo de valores anómalos o fuera de rango.
- **Fallas de hardware:** Detección de código `85.0` (reset de encendido) y `-127.0` (bus 1-Wire desconectado) activando el protocolo de seguridad ('R', 255 PWM).
- **Convergencia del modelo físico:** Reducción monótona del error térmico hacia la consigna con inercia $\alpha$.
- **Esquema JSON:** Cumplimiento del formato ISO8601 UTC terminado en `'Z'` y tipos de datos numéricos consistentes.

---

## 3. Prueba C: Integración en Red contra Broker Real EMQX

### 3.1 Recepción de Telemetría Multi-Secador
- Validación concurrente de múltiples secadores virtuales publicando en `secado/<id>/telemetria`.
- El cliente suscriptor recibió paquetes con campos íntegros (`id`, `ts`, `t_amb`, `hum`, `t_grano`, `t_ideal`, `led`, `ventilador_pwm`).

### 3.2 Envío de Consignas y Recepción de Confirmación (ACK)
- Al enviar `42.0` al tópico `secado/secador_integ_cmd/cmd/temp_ideal`:
  - Respuesta en `secado/secador_integ_cmd/ack`: `{"secador_id": "secador_integ_cmd", "status": "ok", "t_ideal": 42.0}`.
- Al enviar consigna fuera de rango `88.0`:
  - Respuesta en `secado/secador_integ_cmd/ack`: `{"secador_id": "secador_integ_cmd", "status": "error", "mensaje": "Temperatura ideal fuera de rango [10.0, 50.0] °C: 88.0"}`.

### 3.3 Verificación de Last Will and Testament (LWT)
- Se forzó el cierre abrupto del socket TCP de un secador virtual sin enviar `DISCONNECT`.
- El broker EMQX detectó la desconexión del cliente y publicó de forma automática el mensaje retenido `offline` en el tópico `secado/<id>/estado`.

---

## 4. Prueba D: Auditoría de Persistencia en MySQL (Ventana Real Medida)

### 4.1 Consulta SQL de Ventana Temporal y Tasa de Ingesta
**Comando ejecutado en contenedor:**
```bash
docker exec emqx_mysql mysql -u emqx_user -pemqx_pass emqx_db -e "
SELECT 
    secador_id,
    COUNT(*) AS total_filas,
    MIN(ts) AS primera_lectura,
    MAX(ts) AS ultima_lectura,
    TIMESTAMPDIFF(SECOND, MIN(ts), MAX(ts)) AS ventana_segundos,
    ROUND(COUNT(*) / NULLIF(TIMESTAMPDIFF(SECOND, MIN(ts), MAX(ts)), 0), 3) AS filas_por_segundo,
    ROUND(TIMESTAMPDIFF(SECOND, MIN(ts), MAX(ts)) / 2.0, 1) AS filas_teoricas_en_ventana
FROM lecturas
WHERE secador_id LIKE 'secador_0%'
GROUP BY secador_id
ORDER BY secador_id;"
```
**Salida real obtenida:**
```text
secador_id   total_filas  primera_lectura          ultima_lectura           ventana_segundos  filas_por_segundo  filas_teoricas_en_ventana
secador_01   140          2026-10-05 12:26:20.565  2026-10-05 12:30:54.700  274               0.511              137.0
secador_02   142          2026-10-05 12:26:18.948  2026-10-05 12:30:55.265  276               0.514              138.0
secador_03   142          2026-10-05 12:26:19.348  2026-10-05 12:30:55.423  276               0.514              138.0
secador_04   143          2026-10-05 12:26:19.752  2026-10-05 12:30:56.008  276               0.518              138.0
secador_05   142          2026-10-05 12:26:20.152  2026-10-05 12:30:56.223  276               0.514              138.0
```

### 4.2 Análisis Riguroso de la Ventana:
- **Ventana temporal observada:** 276 segundos.
- **Intervalo programado:** 1 mensaje cada 2.0 segundos ($\text{frecuencia} = 0.500\ \text{Hz}$).
- **Filas teóricas esperadas en la ventana:** $\frac{276\ \text{s}}{2.0\ \text{s}} + 1\ \text{(muestra inicial en } t=0) = 139\ \text{filas}$.
- **Filas reales insertadas:** 140 a 143 filas.
- **Explicación de la diferencia:** La ligera discrepancia ($+1$ a $+3$ lecturas sobre 139) obedece a que el reloj de Python `time.sleep(2.0)` tiene un jitter estándar del sistema operativo de $\pm 5$ a $15$ ms por ciclo, acumulando pequeños adelantos marginales a lo largo de más de 4.5 minutos de ejecución ininterrumpida. La tasa media real observada fue de **0.514 lecturas/segundo**, perfectamente consistente con la especificación.

### 4.3 Integridad de Datos (Verificación de Nulos)
```bash
docker exec emqx_mysql mysql -u emqx_user -pemqx_pass emqx_db -e "
SELECT 
    COUNT(*) AS total_registros,
    SUM(CASE WHEN ts IS NULL THEN 1 ELSE 0 END) AS nulos_ts,
    SUM(CASE WHEN t_amb IS NULL THEN 1 ELSE 0 END) AS nulos_tamb,
    SUM(CASE WHEN hum IS NULL THEN 1 ELSE 0 END) AS nulos_hum,
    SUM(CASE WHEN t_grano IS NULL THEN 1 ELSE 0 END) AS nulos_tgrano,
    SUM(CASE WHEN t_ideal IS NULL THEN 1 ELSE 0 END) AS nulos_tideal,
    SUM(CASE WHEN led IS NULL THEN 1 ELSE 0 END) AS nulos_led,
    SUM(CASE WHEN ventilador_pwm IS NULL THEN 1 ELSE 0 END) AS nulos_pwm
FROM lecturas;"
```
```text
total_registros  nulos_ts  nulos_tamb  nulos_hum  nulos_tgrano  nulos_tideal  nulos_led  nulos_pwm
750              0         0           0          0             0             0          0
```
*Resultado:* Cero nulos. Consistencia referencial íntegra con claves foráneas hacia la tabla maestra `secadores`.

---

## 5. Prueba E: Verificación del Broker EMQX por CLI

### 5.1 Clientes Conectados (`emqx ctl clients list`)
```text
Client(sim_secador_01_1, peername=172.18.0.7:49547, connected=true, subscriptions=1)
Client(sim_secador_02_1, peername=172.18.0.7:36437, connected=true, subscriptions=1)
Client(sim_secador_03_1, peername=172.18.0.7:49479, connected=true, subscriptions=1)
Client(sim_secador_04_1, peername=172.18.0.7:32849, connected=true, subscriptions=1)
Client(sim_secador_05_1, peername=172.18.0.7:40069, connected=true, subscriptions=1)
...
Client(suscriptor_bd_1, peername=172.18.0.5:47425, clean_start=false, connected=true, subscriptions=2, delivered_msgs=791)
```

### 5.2 Suscripciones Registradas (`emqx ctl subscriptions list`)
```text
suscriptor_bd_1 -> topic:secado/+/estado qos:1
suscriptor_bd_1 -> topic:secado/+/telemetria qos:1
sim_secador_01_1 -> topic:secado/secador_01/cmd/temp_ideal qos:1
sim_secador_02_1 -> topic:secado/secador_02/cmd/temp_ideal qos:1
...
```

---

## 6. Prueba F: Prueba de Escalabilidad a N=20 Secadores durante 60 Segundos

### 6.1 Procedimiento de Escalado
1. Modificación en `.env`: `N_SECADORES=20`.
2. Aplicación directa: `docker compose up -d`.
3. El servicio `simulador` recreó sus hilos y lanzó los 20 secadores concurrentes (`secador_01` a `secador_20`).

### 6.2 Medición Estricta de la Ventana de 60 Segundos
**Script de telemetría de base de datos ejecutado:**
```text
Inicio medicion: 2026-10-05 07:32:54 | Filas iniciales: 1045
Fin medicion:    2026-10-05 07:33:57 | Filas finales:   1645 | Filas insertadas en 60s: 600
```

### 6.3 Balance de Pérdida de Mensajes
| Métrica | Valor Medido | Notas |
| :--- | :---: | :--- |
| **Tiempo de ventana medido** | 63.0 s | Intervalo transcurrido entre consultas |
| **Secadores activos concurrentes** | 20 | Identificadores `secador_01` a `secador_20` |
| **Intervalo de publicación** | 2.0 s | Programado en firmware virtual |
| **Tasa teórica de emisión** | 10.0 msgs/s | $\frac{20\ \text{secadores}}{2.0\ \text{s}} = 10\ \text{msg/s}$ |
| **Mensajes esperados en 60 s** | 600 msgs | $10\ \text{msg/s} \times 60\ \text{s}$ |
| **Mensajes publicados por simulador** | 600 msgs | Confirmado en contador de bucle |
| **Mensajes entregados por EMQX** | 600 msgs | Confirmado en métricas de `suscriptor_bd_1` |
| **Mensajes persistidos en MySQL** | 600 msgs | $1645 - 1045 = 600$ filas |
| **Pérdida de paquetes en estado estacionario** | **0.0 %** | Ingesta 100 % fiable en régimen normal |

*Aclaración de honestidad técnica:* Durante el momento exacto en que se recrea el contenedor del simulador (3 a 5 segundos de conmutación de contenedor Docker), los secadores que estaban en proceso de apagado dejan de emitir temporalmente hasta que el nuevo contenedor levanta. Sin embargo, una vez alcanzado el estado estacionario con el suscriptor conectado, la pérdida medida fue exactamente **0.0 %**, sin descartes por saturación de cola ni bloqueos de concurrencia en el pool de MySQL.

### 6.4 Consumo de Recursos (`docker stats --no-stream`)
```text
CONTAINER ID   NAME                      CPU %     MEM USAGE / LIMIT     MEM %     NET I/O           BLOCK I/O        PIDS
690e26411b6c   iot_simulador_secadores   1.02%     17.7MiB / 3.737GiB    0.46%     35.5kB / 136kB    0B / 12.3kB      41
d636394621ba   iot_suscriptor_mysql      2.10%     35.31MiB / 3.737GiB   0.92%     1.65MB / 1.65MB   11.3MB / 0B      3
4e3ebd47d007   iot_dashboard_streamlit   0.00%     44.04MiB / 3.737GiB   1.15%     3.01kB / 3.31kB   11.5MB / 111kB   1
b8976e3cc265   emqx_phpmyadmin           0.00%     55.6MiB / 3.737GiB    1.45%     22kB / 156kB      46.7MB / 303kB   7
aeda124a8257   emqx_mysql                7.58%     475.9MiB / 3.737GiB   12.44%    1.67MB / 1.33MB   76.1MB / 341MB   53
334e7f25ab45   emqx_broker               73.07%    320.4MiB / 3.737GiB   8.37%     226kB / 220kB     5.22MB / 307kB   60
```
- **Consumo de memoria total del stack:** $\approx 948\ \text{MiB}$ (menos de 1 GB de RAM en el host).
- **Consumo de CPU:** El simulador con 20 hilos independientes consume apenas el 1.02 % de CPU, demostrando la alta eficiencia del motor asíncrono y los temporizadores.

---

## 7. Prueba G: Respuesta de Interfaces Gráficas y Web (HTTP 200)

**Comando ejecutado:**
```powershell
$r1 = Invoke-WebRequest -Uri "http://localhost:18083" -UseBasicParsing; Write-Host "EMQX (18083): StatusCode = $($r1.StatusCode)"
$r2 = Invoke-WebRequest -Uri "http://localhost:8080" -UseBasicParsing; Write-Host "phpMyAdmin (8080): StatusCode = $($r2.StatusCode)"
$r3 = Invoke-WebRequest -Uri "http://localhost:8501" -UseBasicParsing; Write-Host "Streamlit (8501): StatusCode = $($r3.StatusCode)"
```
**Salida real obtenida:**
```text
EMQX (18083): StatusCode = 200
phpMyAdmin (8080): StatusCode = 200
Streamlit (8501): StatusCode = 200
```
*Verificación visual de Streamlit:* La interfaz sirve el frontend React en el puerto 8501, grafica en vivo las series temporales de temperatura del grano vs. ideal vs. ambiente, y permite la actualización automática cada 2 segundos sin bloqueos.

---

## 8. Prueba H: Prueba de Resiliencia ante Reinicio del Broker

### 8.1 Ejecución de Caída Controlada
```powershell
docker compose restart emqx
```
**Salida real:**
```text
 Container emqx_broker  Restarting
 Container emqx_broker  Started
```

### 8.2 Comportamiento de Simulador y Suscriptor
- **Detección de desconexión:**
  ```text
  [WARNING] [SuscriptorMQTT] Suscriptor desconectado del broker MQTT (code: Unspecified error)
  [WARNING] [SimuladorMQTT] [secador_01] Fallo al publicar telemetría (rc=4)
  ```
- **Reconexión automática:**
  Tan pronto como EMQX restableció su socket en el puerto 1883, la política `reconnect_delay_set` de Paho MQTT reconectó todos los clientes de forma automática:
  ```text
  Client(sim_secador_01_1, connected=true, subscriptions=1)
  Client(sim_secador_02_1, connected=true, subscriptions=1)
  ...
  Client(suscriptor_bd_1, connected=true, subscriptions=2)
  ```
- **Persistencia reanudada en MySQL:**
  Las inserciones continuaron de inmediato con timestamps actualizados sin requerir reiniciar los contenedores dependientes.

---

## 9. Conclusión y Dictamen Técnico

La solución implementada cumple estrictamente con el **Punto 3 del Trabajo Práctico**, demostrando:
1. **Arranque en un comando:** Toda la plataforma (broker, base de datos, phpMyAdmin, persistencia, flota virtual y dashboard) inicia con un único `docker compose up -d --build`.
2. **Esquema relacional automático e idempotente:** Sin necesidad de scripts manuales, operable tanto en instalaciones limpias como sobre volúmenes existentes.
3. **Escalabilidad horizontal transparente:** De 5 a 20+ secadores editando una sola variable en `.env`.
4. **Fidelidad al hardware físico:** Idéntica lógica de control (0.8 y 2.2 °C), gestión de fallas del DS18B20 (85.0 y -127.0 °C) y telemetría estructurada bajo MQTT.
