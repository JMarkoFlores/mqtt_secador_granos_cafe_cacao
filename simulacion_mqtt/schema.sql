-- =====================================================================
-- Esquema relacional para persistencia de telemetría y eventos MQTT
-- Proyecto: Simulación de Secadores de Café/Cacao
-- =====================================================================

CREATE DATABASE IF NOT EXISTS emqx_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE emqx_db;

-- 1. Tabla de Secadores registrados
CREATE TABLE IF NOT EXISTS secadores (
    id VARCHAR(50) NOT NULL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL,
    ubicacion VARCHAR(100) DEFAULT 'Módulo Central',
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. Tabla de Lecturas de Telemetría (DHT + DS18B20 + Actuadores)
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

-- 3. Tabla de Eventos de Estado (online/offline con Last Will)
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
