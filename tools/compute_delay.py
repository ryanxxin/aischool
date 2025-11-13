from datetime import datetime, timezone, timedelta
import sys
import pathlib
# ensure repo root in sys.path so we can import main
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import main

sec = main.seconds_until_next(0, 9, 0, 'Asia/Seoul')
now = datetime.now(timezone.utc)
target = now + timedelta(seconds=sec)
print(sec)
print('Now (UTC):', now.isoformat())
print('Target (UTC):', target.isoformat())
try:
    from zoneinfo import ZoneInfo
    print('Target (KST):', target.astimezone(ZoneInfo('Asia/Seoul')).isoformat())
except Exception as e:
    print('ZoneInfo not available:', e)
