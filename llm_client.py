# backend/llm_client.py
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
