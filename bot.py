import time
import requests
import threading
from datetime import datetime
import pytz

FIREBASE_URL = "https://bosstimer-2a778-default-rtdb.asia-southeast1.firebasedatabase.app/.json"
DISCORD_WEBHOOK_URL = "https://ptb.discord.com/api/webhooks/1382831229681930300/gFhSSjfKBamc9hFGBJ7KEZOEcSpPjBmV3h8t_o5n6pGfCsIWeGFhIZbGYtF9IDlQcZOW"

notified_5_min = set()
notified_3_min = set()
last_death_record = {}

def fetch_boss_data(retries=3, delay=5):
    """ดึงข้อมูลบอสจาก Firebase พร้อม retry เมื่อผิดพลาด"""
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(FIREBASE_URL, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "bosses" in data:
                    return data["bosses"]
                else:
                    print("⚠️ ข้อมูลบอสใน Firebase ไม่มี key 'bosses'")
                    return {}
            else:
                print(f"❌ ดึงข้อมูลล้มเหลว (สถานะ {response.status_code})")
        except Exception as e:
            print(f"❌ ดึงข้อมูลล้มเหลว (ข้อผิดพลาด: {e})")

        if attempt < retries:
            print(f"🔄 กำลังลองใหม่อีกครั้ง (ครั้งที่ {attempt + 1}) หลัง {delay} วินาที...")
            time.sleep(delay)

    print("❌ ดึงข้อมูลบอสล้มเหลวหลังลองหลายครั้ง")
    return {}

def notify_discord(message):
    """ส่งข้อความแจ้งเตือน Discord"""
    print(f"[แจ้งเตือน Discord] {message}")
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10)
        if response.status_code != 204 and response.status_code != 200:
            print(f"❌ แจ้งเตือน Discord ไม่สำเร็จ (สถานะ {response.status_code})")
    except Exception as e:
        print(f"❌ แจ้งเตือนไม่สำเร็จ: {e}")

def process_boss(boss, info, now_ts):
    """ประมวลผลบอสแต่ละตัว"""
    cooldown = info.get("cooldown")
    last_death = info.get("lastDeath")

    if cooldown is None or last_death is None:
        print(f"⚠️ ข้อมูลบอส {boss} ไม่ครบถ้วน (cooldown หรือ lastDeath หายไป)")
        return

    try:
        cooldown_ms = float(cooldown) * 1000
        last_death = int(last_death)
    except Exception as e:
        print(f"⚠️ ข้อมูลบอส {boss} ไม่ถูกต้อง (cooldown หรือ lastDeath ไม่ใช่ตัวเลข): {e}")
        return

    spawn_time = last_death + cooldown_ms
    time_diff = spawn_time - now_ts

    # รีเซ็ตสถานะแจ้งเตือนเมื่อ lastDeath เปลี่ยน
    if boss not in last_death_record or last_death_record[boss] != last_death:
        notified_5_min.discard(boss)
        notified_3_min.discard(boss)
        last_death_record[boss] = last_death
        print(f"🔄 รีเซ็ตสถานะแจ้งเตือนบอส {boss}")

    print(f"[{boss}] cooldown={cooldown_ms} ms, lastDeath={last_death}, spawn_time={spawn_time}, time_diff={time_diff} ms")

    # แจ้งเตือนแค่ 5 และ 3 นาทีก่อนเกิด
    if 0 <= time_diff <= 300000 and boss not in notified_5_min:
        notify_discord(f"🕔 อีก 5 นาที {boss} จะเกิด!")
        notified_5_min.add(boss)
    elif 0 <= time_diff <= 180000 and boss not in notified_3_min:
        notify_discord(f"🕒 อีก 3 นาที {boss} จะเกิด!")
        notified_3_min.add(boss)

def monitor_bosses():
    print("🚀 Bot กำลังทำงาน...")
    tz = pytz.timezone("Asia/Bangkok")

    while True:
        bosses = fetch_boss_data()
        if not bosses:
            print("⚠️ ไม่มีข้อมูลบอสในรอบนี้")
            time.sleep(30)
            continue

        now = datetime.now(tz)
        now_ts = int(now.timestamp() * 1000)

        for boss, info in bosses.items():
            process_boss(boss, info, now_ts)

        time.sleep(30)

if __name__ == "__main__":
    monitor_thread = threading.Thread(target=monitor_bosses)
    monitor_thread.daemon = True
    monitor_thread.start()

    # รันไปเรื่อย ๆ
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("🛑 Bot หยุดทำงานโดยผู้ใช้")
