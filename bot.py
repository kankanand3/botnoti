import time
import requests
import threading
from datetime import datetime
import pytz

FIREBASE_URL = "https://bosstimer-2a778-default-rtdb.asia-southeast1.firebasedatabase.app/.json"
DISCORD_WEBHOOK_URL = "https://ptb.discord.com/api/webhooks/1382831229681930300/gFhSSjfKBamc9hFGBJ7KEZOEcSpPjBmV3h8t_o5n6pGfCsIWeGFhIZbGYtF9IDlQcZOW"
GUARDIAN_ROLE_ID = "1377155652480401499"  # Role ID ของ @guardian

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
    """ส่งข้อความแจ้งเตือน Discord พร้อมแท็ก @guardian"""
    tagged_message = f"<@&{GUARDIAN_ROLE_ID}> {message}"  # เพิ่มการแท็ก Role
    print(f"[แจ้งเตือน Discord] {tagged_message}")
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": tagged_message}, timeout=10)
        if response.status_code != 204 and response.status_code != 200:
            print(f"❌ แจ้งเตือน Discord ไม่สำเร็จ (สถานะ {response.status_code})")
    except Exception as e:
        print(f"❌ แจ้งเตือนไม่สำเร็จ: {e}")

def format_owner(owner):
    """ถ้ามีเจ้าของ ส่งชื่อเจ้าของให้ดูสวยงาม"""
    if owner and owner.strip():
        return f"\n👑 เจ้าของบอส: **{owner.strip()}**"
    return ""

def process_boss(boss, info, now_ts):
    """ประมวลผลบอสแต่ละตัว"""
    cooldown = info.get("cooldown")
    last_death = info.get("lastDeath")
    owner = info.get("owner", "").strip() if info.get("owner") else ""

    if cooldown is None or last_death is None:
        print(f"⚠️ ข้อมูลบอส {boss} ไม่ครบถ้วน (cooldown หรือ lastDeath หายไป)")
        return

    try:
        cooldown_ms = float(cooldown) * 1000
        last_death = int(last_death)
    except Exception as e:
        print(f"⚠️ ข้อมูลบอส {boss} ไม่ถูกต้อง (cooldown หรือ lastDeath ไม่ใช่ตัวเลข): {e}")
        return

    spawn_time = las_
