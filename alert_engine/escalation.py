# backend/alert_engine/escalation.py
class AlertEscalationManager:
    """알람 에스컬레이션 관리"""
    
    async def monitor_escalations(self):
        """미확인 알람 에스컬레이션"""
        while True:
            pending_alerts = await self.get_pending_alerts()
            
            for alert in pending_alerts:
                elapsed = self._get_elapsed_time(alert)
                policy = self._get_policy(alert['policy_name'])
                
                if elapsed >= policy.escalation_time:
                    await self._escalate_alert(alert, policy)
                    
            await asyncio.sleep(60)  # 1분마다 체크
    
    async def _escalate_alert(self, alert: Dict, policy: AlertPolicy):
        """알람 에스컬레이션"""
        # 상위 관리자에게 알림
        await self._notify_manager(alert)
        
        # 심각도 상승
        alert['severity'] = self._increase_severity(alert['severity'])
        
        # 추가 채널로 알림
        await self._send_emergency_notifications(alert)
        
        # 로그 기록
        logger.warning(f"Alert escalated: {alert['id']}")