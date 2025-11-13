## 개요
이 프로젝트는 MOBY 서비스용 IoT 센서 모니터링 백엔드 서버입니다.  
Raspberry Pi 센서 데이터를 수집, 저장, 분석하고 실시간 알람을 제공하는 RESTful API 및 WebSocket 서버입니다.

## 주요 기능
- MQTT 기반 센서 데이터 수집
  - DHT11 (온도/습도)
  - SEN0209 (진동 센서)
  - SZH-EK087 (사운드 센서)
  - MPU-6050 (가속도계/자이로스코프)
  - BMP180 (압력/온도 센서)
- InfluxDB를 통한 시계열 데이터 저장
- 실시간 WebSocket 데이터 스트리밍
- AI 기반 알람 분석 및 자동 알림 (Email)
- 온도/진동 임계값 기반 자동 알람 감지
  - 온도: BMP180 센서 기준
  - 진동: 전압 기준 지속 감지

## 개발 환경
- Python 3.10+
- FastAPI (웹 프레임워크)
- InfluxDB (시계열 데이터베이스)
- MQTT Broker (Mosquitto)
- OpenAI API (LLM 분석)

## 시작하기

### 1. 의존성 설치
```bash
pip install -r requirements.txt
```

### 2. 환경 변수 설정
`.env` 파일을 생성하고 다음 변수들을 설정하세요:
```env
# InfluxDB 설정
INFLUX_URL=http://localhost:8086
INFLUX_ORG=your-org
INFLUX_BUCKET=your-bucket
INFLUX_TOKEN=your-token

# MQTT 브로커 설정 (라즈베리파이 IP 주소)
MQTT_BROKER=192.168.x.x  # 라즈베리파이에서 MQTT 브로커 실행 시 IP 주소
MQTT_PORT=1883

# 알람 임계값
TEMP_CRITICAL_THRESHOLD=50  # BMP180 온도 임계값 (°C)
VIBRATION_WARNING_THRESHOLD=2.0  # 진동 전압 임계값 (V)
VIBRATION_DURATION_MINUTES=5  # 진동 지속 시간 (분)

# LLM 설정 (선택사항)
LLM_API_URL=https://api.openai.com/v1/chat/completions
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4o-mini

# Email 알림 (선택사항, Critical 알람만)
EMAIL_SENDER=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
EMAIL_RECIPIENT=recipient@example.com
```

### 3. MQTT Broker 실행
MQTT 브로커는 라즈베리파이에서 실행됩니다.

**라즈베리파이에서:**
```bash
# Mosquitto 설치
sudo apt-get install mosquitto mosquitto-clients
sudo systemctl start mosquitto
sudo systemctl enable mosquitto

# 브로커 실행 확인
sudo systemctl status mosquitto
```

**로컬 테스트용 (Docker):**
```bash
docker run -it -p 1883:1883 eclipse-mosquitto
```

### 4. 개발 서버 실행
```bash
python main.py
# 또는
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 5. 센서 시뮬레이터 실행 (테스트용)
```bash
python rpi_sensor.py
```

## MQTT 토픽 구조
센서 데이터는 다음 토픽으로 발행됩니다:
- `factory/sensor/dht11` - DHT11 온도/습도 데이터
- `factory/sensor/vibration` - SEN0209 진동 센서 데이터
- `factory/sensor/sound` - SZH-EK087 사운드 센서 데이터
- `factory/sensor/accel_gyro` - MPU-6050 가속도/자이로 데이터
- `factory/sensor/pressure` - BMP180 압력/온도 데이터

## 센서 데이터 구조
각 센서는 다음과 같은 JSON 형식으로 데이터를 발행합니다:
```json
{
  "sensor_type": "vibration",
  "sensor_model": "SEN0209",
  "fields": {
    "vibration_raw": 12345,
    "vibration_voltage": 1.234567
  },
  "timestamp_ns": 1234567890123456789
}
```

## 알람 시스템
- **온도 알람**: BMP180(pressure) 센서의 온도가 임계값을 초과하면 Critical 알람 발생
- **진동 알람**: 진동 센서의 전압이 임계값을 초과한 상태가 일정 시간 지속되면 Warning 알람 발생
- 알람 발생 시 Email로 자동 알림 발송 (Critical 알람만)
- AI(LLM)를 통한 알람 상황 분석 및 권장 조치 제시

## API 엔드포인트
- `GET /api/alerts/history?hours=24` - 알람 히스토리 조회
- `WebSocket /ws/sensor` - 실시간 센서 데이터 스트리밍

## 프로젝트 구조
- `main.py` - FastAPI 메인 서버 및 MQTT 구독, WebSocket 브로드캐스트
- `alert_engine.py` - 알람 감지 엔진 (온도/진동 임계값 체크)
- `llm_client.py` - AI 알람 분석 클라이언트 (OpenAI API)
- `notifier.py` - Email 알림 발송 모듈
- `rpi_sensor.py` - Raspberry Pi 센서 시뮬레이터 (테스트용)
- `mock_sensor_alerts.py` - 개발용 모의 데이터 서버