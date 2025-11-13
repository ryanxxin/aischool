## 개요
이 프로젝트는 MOBY 서비스용 IoT 센서 모니터링 백엔드 서버입니다.  
Raspberry Pi 센서 데이터를 수집, 저장, 분석하고 실시간 알람을 제공하는 RESTful API 및 WebSocket 서버입니다.

## 주요 기능
- MQTT 기반 센서 데이터 수집 (진동, 온도, RPM)
- InfluxDB를 통한 시계열 데이터 저장
- 실시간 WebSocket 데이터 스트리밍
- AI 기반 알람 분석 및 자동 알림 (Slack, Email)
- 온도/진동 임계값 기반 자동 알람 감지

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

# 알람 임계값
TEMP_CRITICAL_THRESHOLD=50
VIBRATION_WARNING_THRESHOLD=3.5
VIBRATION_DURATION_MINUTES=5

# LLM 설정 (선택사항)
LLM_API_URL=https://api.openai.com/v1/chat/completions
LLM_API_KEY=your-api-key
LLM_MODEL=gpt-4o-mini

# Slack 알림 (선택사항)
SLACK_WEBHOOK_URL=your-webhook-url

# Email 알림 (선택사항, Critical 알람만)
EMAIL_SENDER=your-email@gmail.com
EMAIL_PASSWORD=your-app-password
EMAIL_RECIPIENT=recipient@example.com
```

### 3. MQTT Broker 실행
```bash
# Mosquitto 설치 (Ubuntu/Debian)
sudo apt-get install mosquitto mosquitto-clients
sudo systemctl start mosquitto

# 또는 Docker로 실행
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

## API 엔드포인트
- `GET /api/alerts/history?hours=24` - 알람 히스토리 조회
- `WebSocket /ws/sensor` - 실시간 센서 데이터 스트리밍

## 프로젝트 구조
- `main.py` - FastAPI 메인 서버 및 MQTT 구독
- `alert_engine.py` - 알람 감지 엔진
- `llm_client.py` - AI 알람 분석 클라이언트
- `notifier.py` - Slack/Email 알림 발송
- `rpi_sensor.py` - Raspberry Pi 센서 시뮬레이터
- `mock_sensor_alerts.py` - 개발용 모의 데이터 서버