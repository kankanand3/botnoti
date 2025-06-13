import time
import requests
import threading
from datetime import datetime
import pytz

FIREBASE_URL = "https://bosstimer-2a778-default-rtdb.asia-southeast1.firebasedatabase.app/.json"
DISCORD_WEBHOOK_URL = "https://ptb.discord.com/api/webhooks/1382831229681930300/gFhSSjfKBamc9hFGBJ7KEZOEcSpPjBmV3h8t_o5n6pGfCsIWeGFhIZbGYtF9IDlQcZOW"  # <-- ใส่ Webhook ของคุณ

def fetch_boss_data():
    response = requests.get(FIREBASE_URL)
    if response.status_code == 200:
        return response.json()
    return {}

notified_5_min = set()
notified_3_min = set()
spawned = set()

def monitor_bosses():
    while True:
        data = fetch_boss_data()
        if not data:
            print("⚠️ ไม่พบข้อมูลบอส")
            time.sleep(30)
            continue

        now = datetime.now(pytz.timezone("Asia/Bangkok"))
        now_ts = int(now.timestamp() * 1000)

        for boss, info in data.items():
            cooldown = info.get("cooldown", 0) * 1000
            last_death = info.get("lastDeath", 0)
            spawn_time = last_death + cooldown

            time_diff = spawn_time - now_ts

            if 0 <= time_diff <= 300000 and boss not in notified_5_min:
                notify_discord(f"🕔 อีก 5 นาที {boss} จะเกิด!")
                notified_5_min.add(boss)
            elif 0 <= time_diff <= 180000 and boss not in notified_3_min:
                notify_discord(f"🕒 อีก 3 นาที {boss} จะเกิด!")
                notified_3_min.add(boss)
            elif time_diff <= 0 and boss not in spawned:
                notify_discord(f"✅ บอส {boss} เกิดแล้ว!")
                spawned.add(boss)

        time.sleep(30)

def notify_discord(message):
    print(message)
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message})
    except Exception as e:
        print("❌ แจ้งเตือนไม่สำเร็จ:", e)

if __name__ == "__main__":
    print("🚀 Bot กำลังทำงาน...")
    monitor_thread = threading.Thread(target=monitor_bosses)
    monitor_thread.start()