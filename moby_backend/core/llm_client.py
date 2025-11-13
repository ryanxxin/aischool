import os
import aiohttp
import logging

logger = logging.getLogger(__name__)

class LLMClient:
    def __init__(self):
        self.url = os.getenv("LLM_API_URL")
        self.api_key = os.getenv("LLM_API_KEY")
        self.model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        if not self.api_key:
            logger.warning("LLM_API_KEY not set. LLM features will be disabled.")
    
    async def generate_alert_summary(self, alert: dict) -> str:
        if not self.api_key:
            return ""
        prompt = f"""
다음 IoT 센서 알람을 분석하고 간단명료하게 요약해주세요:

- 센서 ID: {alert['sensor_id']}
- 경고 레벨: {alert['level']}
- 메트릭: {alert['metric']}
- 현재 값: {alert['value']}
- 임계값: {alert.get('threshold', 'N/A')}

1-2문장으로 상황 설명과 권장 조치사항을 제시해주세요.
"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "당신은 산업 IoT 설비 모니터링 전문가입니다."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 200
                    },
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"LLM API error: {resp.status}")
                        return ""
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            return ""

    async def generate_timeseries_report(self, summary: dict) -> str:
        """Generate a human-readable report (Korean) from aggregated timeseries summary.

        summary format expected:
        {
            "start": "...",
            "end": "...",
            "metrics": {
                "dht11": {"temperature_c": {"min": x, "max": y, "mean": z}, ...},
                ...
            }
        }
        """
        if not self.api_key:
            return ""

        prompt_lines = [
            "다음은 센서 시계열 데이터의 집계(요약)입니다. 이를 바탕으로 운영자용 주간 리포트(3-6문장)를 작성하세요.",
            f"기간: {summary.get('start', 'N/A')} ~ {summary.get('end', 'N/A')}",
            "핵심 포인트: 평균, 최대/최소, 이상징후(급격한 변화나 임계치 초과)가 있으면 강조하세요.",
            "권장 조치: 우선순위별로 1-3개 권장 조치 제안.",
            "\n--- 데이터 요약 ---"
        ]

        for sensor, fields in summary.get('metrics', {}).items():
            prompt_lines.append(f"센서: {sensor}")
            for field, stats in fields.items():
                prompt_lines.append(f" - {field}: mean={stats.get('mean')}, min={stats.get('min')}, max={stats.get('max')}")

        prompt = "\n".join(prompt_lines)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": "당신은 산업 IoT 설비 모니터링 전문가입니다."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.2,
                        "max_tokens": 400
                    },
                    timeout=aiohttp.ClientTimeout(total=20)
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"LLM API error: {resp.status}")
                        return ""
                    data = await resp.json()
                    return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"LLM report generation failed: {e}")
            return ""
