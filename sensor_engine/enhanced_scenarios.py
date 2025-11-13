# backend/alert_engine/enhanced_policy.py

import uuid # [수정] 누락된 uuid 임포트 추가
import asyncio # [수정] 비동기 Mock 구현을 위해 추가
import random # Mock 구현을 위해 추가
from datetime import datetime, timedelta # [수정] datetime, timedelta 임포트 추가
from enum import Enum
from dataclasses import dataclass
from typing import List, Dict, Any, Optional # Any, Optional 임포트 추가

# --- 누락된 외부 클라이언트 (Mock 객체로 대체) ---
# 실제 OpenAI API 키가 없는 경우, 이 Mock 객체가 임시로 응답을 생성합니다.
class MockOpenAI:
    class ChatCompletion:
        @staticmethod
        async def acreate(model: str, messages: List[Dict], temperature: float) -> Dict:
            await asyncio.sleep(0.1) # 비동기 대기 모방
            policy_name = messages[0]['content'].split('정책: ')[1].split('\n')[0]
            return {
                "choices": [{
                    "message": {
                        "content": f"AI 분석 결과: {policy_name} 정책 기반으로, 현재 설비는 {random.choice(['고장 직전', '경고 단계', '안정 단계'])}으로 진단됩니다. 즉시 {random.choice(['작동 정지', '점검 예약', '윤활유 보충'])} 조치 바랍니다."
                    }
                }]
            }

openai = MockOpenAI() 
# ---------------------------------------------------

class AlertSeverity(Enum):
    INFO = 1
    WARNING = 2
    CRITICAL = 3
    EMERGENCY = 4

@dataclass
class AlertPolicy:
    """강화된 알람 정책"""
    name: str
    conditions: List[Dict]
    severity: AlertSeverity
    escalation_time: int  # 미확인 시 에스컬레이션 시간(분)
    notification_channels: List[str]
    auto_actions: List[str]
    
class EnhancedAlertEngine:
    def __init__(self):
        self.policies = self._load_policies()
        self.alert_history: List[Dict] = []
        self.duplicate_check_window = timedelta(minutes=5) # [수정] 중복 체크 시간 정의
        
    def _load_policies(self) -> List[AlertPolicy]:
        """알람 정책 로드"""
        return [
            # 복합 조건 정책
            AlertPolicy(
                name="설비 과열 경고",
                conditions=[
                    {"metric": "temperature", "operator": ">", "value": 80},
                    {"metric": "humidity", "operator": "<", "value": 30}
                ],
                severity=AlertSeverity.WARNING,
                escalation_time=15,
                notification_channels=["slack", "email"],
                auto_actions=["log", "notify_operator"]
            ),
            
            # 긴급 정책
            AlertPolicy(
                name="설비 임계 상태",
                conditions=[
                    {"metric": "temperature", "operator": ">", "value": 90},
                    {"metric": "vibration", "operator": ">", "value": 85}
                ],
                severity=AlertSeverity.EMERGENCY,
                escalation_time=5,
                notification_channels=["slack", "email", "sms", "call"],
                auto_actions=["log", "emergency_shutdown", "notify_manager"]
            ),
            
            # 예측 정책 (AI 기반)
            AlertPolicy(
                name="예측적 유지보수 알림",
                conditions=[
                    {"metric": "vibration_trend", "operator": "increasing", "window": "7d"},
                    {"metric": "temperature_stddev", "operator": ">", "value": 5}
                ],
                severity=AlertSeverity.INFO,
                escalation_time=60,
                notification_channels=["email"],
                auto_actions=["log", "schedule_maintenance"]
            )
        ]
        
    async def evaluate_policies(self, sensor_data: Dict) -> List[Dict]:
        """정책 평가 및 알람 생성"""
        triggered_alerts = []
        
        for policy in self.policies:
            # None 체크를 포함하여 안정적인 비교
            if self._check_conditions(sensor_data, policy.conditions): 
                alert = await self._create_alert(policy, sensor_data)
                
                # 중복 알람 방지
                if not self._is_duplicate(alert): # [수정] self._is_duplicate 호출
                    triggered_alerts.append(alert)
                    self.alert_history.append(alert) # [수정] 히스토리에 추가
                    await self._execute_actions(policy, alert)
                    
        return triggered_alerts
        
    def _check_conditions(self, data: Dict, conditions: List[Dict]) -> bool:
        """조건 체크 (AND 로직)"""
        for condition in conditions:
            metric = condition['metric']
            operator = condition['operator']
            threshold = condition['value']
            
            if metric not in data and operator not in ["increasing"]: # [수정] metric 없는 경우 처리
                return False
                
            current_value = data.get(metric)
            
            # None 체크를 포함한 비교
            if operator == ">":
                if not (current_value is not None and current_value > threshold): return False
            elif operator == "<":
                if not (current_value is not None and current_value < threshold): return False
            elif operator == "increasing":
                window = condition.get('window', '1h')
                if not self._check_trend(metric, window):
                    return False
                    
        return True

    # --- 누락된 내부 함수들 추가 (작동을 위해 필수) ---

    def _is_duplicate(self, new_alert: Dict) -> bool:
        """[추가] 중복 알람 체크 로직 (더미)"""
        current_time = datetime.utcnow()
        for alert in reversed(self.alert_history):
            alert_ts = datetime.fromisoformat(alert['timestamp'].replace("Z", "+00:00")) # ISO 파싱
            if current_time - alert_ts < self.duplicate_check_window:
                if alert['policy_name'] == new_alert['policy_name'] and \
                   alert['severity'] == new_alert['severity']:
                    return True
            else:
                break
        return False
        
    def _check_trend(self, metric: str, window: str) -> bool:
        """[추가] 트렌드 체크 로직 (더미)"""
        return False 
    
    def _get_recent_trends(self, data: Dict) -> str:
        """[추가] AI 분석을 위한 최근 트렌드 (더미)"""
        return "데이터가 충분하지 않아 트렌드 분석 불가."

    def _get_recommended_actions(self, policy: AlertPolicy) -> List[str]:
        """[추가] 권장 조치 반환"""
        return policy.auto_actions

    async def _log_alert(self, alert: Dict):
        """[추가] 알람 로깅 (더미)"""
        print(f"[ACTION] Alert Logged: {alert['policy_name']}")
        await asyncio.sleep(0.01)

    async def _send_notifications(self, channels: List[str], alert: Dict):
        """[추가] 알림 전송 (더미)"""
        print(f"[ACTION] Notification Sent via {', '.join(channels)}")
        await asyncio.sleep(0.01)

    async def _trigger_emergency_shutdown(self, equipment_id: str):
        """[추가] 긴급 정지 (더미)"""
        print(f"[ACTION] EMERGENCY SHUTDOWN triggered for {equipment_id}")
        await asyncio.sleep(0.01)

    async def _schedule_maintenance(self, equipment_id: str):
        """[추가] 유지보수 일정 등록 (더미)"""
        print(f"[ACTION] Maintenance scheduled for {equipment_id}")
        await asyncio.sleep(0.01)

    # --- _create_alert와 _generate_ai_analysis는 유지 ---
    async def _create_alert(self, policy: AlertPolicy, data: Dict) -> Dict:
        """알람 생성 with AI 분석"""
        ai_analysis = await self._generate_ai_analysis(policy, data)
        
        alert = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat(), # [수정] datetime.now() -> datetime.utcnow()
            "policy_name": policy.name,
            "severity": policy.severity.name,
            "equipment_id": data.get('equipment_id'),
            "sensor_values": {
                "temperature": data.get('temperature'),
                "humidity": data.get('humidity'),
                "vibration": data.get('vibration'),
                "noise": data.get('noise')
            },
            "llm_summary": ai_analysis,
            "recommended_actions": self._get_recommended_actions(policy),
            "escalation_time": policy.escalation_time,
            "status": "pending"
        }
        return alert
        
    async def _generate_ai_analysis(self, policy: AlertPolicy, data: Dict) -> str:
        """OpenAI (Mock)를 통한 상황 분석"""
        prompt = f"""
        설비 모니터링 알람 분석:
        
        정책: {policy.name}
        심각도: {policy.severity.name}
        
        현재 센서 값:
        - 온도: {data.get('temperature')}°C
        - 습도: {data.get('humidity')}%
        - 진동: {data.get('vibration')}
        - 소음: {data.get('noise')}dB
        
        최근 트렌드: {self._get_recent_trends(data)}
        
        다음 내용을 2-3문장으로 요약해주세요:
        1. 현재 상황 진단
        2. 잠재적 원인
        3. 즉각 조치사항
        """
        
        try:
            response = await openai.ChatCompletion.acreate(
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3
            )
            return response.choices[0]['message']['content'] 
        except Exception as e:
            return f"AI 분석 오류: {e}"