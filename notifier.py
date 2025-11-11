# backend/notifier.py
import os
import asyncio
import aiohttp
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class SlackNotifier:
    def __init__(self):
        self.webhook_url = os.getenv("SLACK_WEBHOOK_URL")
        if not self.webhook_url:
            logger.info("SLACK_WEBHOOK_URL not set. Slack notifications disabled.")
    
    async def send(self, alert: dict):
        if not self.webhook_url:
            logger.info(f"[Slack 비활성화] {alert['message']}")
            return
        color = "#DC2626" if alert["level"] == "CRITICAL" else "#F59E0B"
        llm_summary = alert.get("llm_summary", "")
        fields = [
            {"title": "센서 ID", "value": alert["sensor_id"], "short": True},
            {"title": "메트릭", "value": alert["metric"], "short": True},
            {"title": "현재 값", "value": str(alert.get("value", "N/A")), "short": True},
            {"title": "임계값", "value": str(alert.get("threshold", "N/A")), "short": True}
        ]
        if llm_summary:
            fields.append({"title": "AI 분석", "value": llm_summary, "short": False})
        payload = {
            "attachments": [{
                "color": color,
                "title": f"{alert['level']} Alert",
                "text": alert["message"],
                "fields": fields,
                "footer": "MOBY Alert System",
                "ts": int(datetime.fromisoformat(alert["timestamp"]).timestamp())
            }]
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(self.webhook_url, json=payload, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status != 200:
                        logger.error(f"Slack notification failed: {resp.status}")
                    else:
                        logger.info(f"Slack notification sent for {alert['id']}")
        except Exception as e:
            logger.error(f"Slack send error: {e}")

class EmailNotifier:
    def __init__(self):
        self.smtp_server = "smtp.gmail.com"
        self.port = 587
        self.sender = os.getenv("EMAIL_SENDER")
        self.password = os.getenv("EMAIL_PASSWORD")
        self.recipient = os.getenv("EMAIL_RECIPIENT", self.sender)
        if not self.sender or not self.password:
            logger.info("Email credentials not set. Email notifications disabled.")
    
    async def send(self, alert: dict):
        if not self.sender or not self.password:
            logger.info(f"[Email 비활성화] {alert['message']}")
            return
        if alert["level"] != "CRITICAL":
            return
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[MOBY] {alert['level']} Alert - {alert['sensor_id']}"
        msg["From"] = self.sender
        msg["To"] = self.recipient
        llm_summary = alert.get("llm_summary", "")
        html = f"""<html><body style="font-family: Arial, sans-serif;">
            <h2 style="color: #DC2626;">🚨 Critical Alert</h2>
            <p><strong>{alert['message']}</strong></p>
            <table style="border-collapse: collapse; margin: 20px 0;">
                <tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>센서 ID</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{alert['sensor_id']}</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>메트릭</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{alert['metric']}</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>현재 값</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{alert.get('value', 'N/A')}</td></tr>
                <tr><td style="padding: 8px; border: 1px solid #ddd;"><strong>임계값</strong></td>
                    <td style="padding: 8px; border: 1px solid #ddd;">{alert.get('threshold', 'N/A')}</td></tr>
            </table>
            {f'<div style="background: #f3f4f6; padding: 15px; border-radius: 5px;"><h3>AI 분석</h3><p>{llm_summary}</p></div>' if llm_summary else ''}
            <p style="color: #666; margin-top: 20px;">시간: {alert['timestamp']}<br>MOBY Alert System</p>
        </body></html>"""
        msg.attach(MIMEText(html, "html"))
        try:
            await asyncio.to_thread(self._send_sync, msg)
            logger.info(f"Email notification sent for {alert['id']}")
        except Exception as e:
            logger.error(f"Email send error: {e}")
    
    def _send_sync(self, msg):
        with smtplib.SMTP(self.smtp_server, self.port) as server:
            server.starttls()
            server.login(self.sender, self.password)
            server.send_message(msg)
