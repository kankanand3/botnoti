import logging
import time
import requests
import threading
from datetime import datetime
import pytz
import re

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

FIREBASE_URL = "https://bosstimer-2a778-default-rtdb.asia-southeast1.firebasedatabase.app/.json"
DISCORD_WEBHOOK_URL = "https://ptb.discord.com/api/webhooks/1382831229681930300/gFhSSjfKBamc9hFGBJ7KEZOEcSpPjBmV3h8t_o5n6pGfCsIWeGFhIZbGYtF9IDlQcZOW"
GUARDIAN_ROLE_ID = "1377155652480401499"

notified_5_min = set()
notified_3_min = set()
notified_spawned = set()
last_death_record = {}
invalid_data_bosses = set()

def sanitize_boss_name(name):
    return re.sub(r'[^\w\sก-๙]', '', name).strip()

def fetch_boss_data(retries=3, delay=5):
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(FIREBASE_URL, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "bosses" in data:
                    logging.debug(f"ดึงข้อมูลบอสสำเร็จ: พบ {len(data['bosses'])} ตัว")
                    return data["bosses"]
                else:
                    logging.warning("ข้อมูลบอสไม่มี key 'bosses'")
                    return {}
            else:
                logging.error(f"HTTP Error {response.status_code}")
        except Exception as e:
            logging.error(f"ดึงข้อมูลล้มเหลว: {e}")
        if attempt < retries:
            logging.info(f"ลองใหม่อีก {attempt + 1} ใน {delay} วิ...")
            time.sleep(delay)
    return {}

def notify_discord(message):
    tagged = f"<@&{GUARDIAN_ROLE_ID}>\n\n{message}"
    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json={"content": tagged}, timeout=10)
        if res.status_code not in (200, 204):
            logging.error(f"แจ้ง Discord ล้มเหลว: {res.status_code}")
    except Exception as e:
        logging.error(f"แจ้งเตือน Discord error: {e}")

def format_owner(owner):
    return f"\n👑 เจ้าของบอส: **{owner.strip()}**" if owner else ""

def format_timestamp(ts_ms):
    if ts_ms is None: return "-"
    tz = pytz.timezone("Asia/Bangkok")
    return datetime.fromtimestamp(ts_ms / 1000, tz).strftime("%H:%M น.")

def process_boss(boss, info, now_ts):
    raw_boss = boss  # Keep original for logging
    boss = sanitize_boss_name(boss)

    cooldown = info.get("cooldown")
    last_death = info.get("lastDeath")
    owner = info.get("owner", "").strip()

    if cooldown is None or last_death is None:
        if boss not in invalid_data_bosses:
            logging.warning(f"{boss}: ข้อมูลไม่ครบ")
            notify_discord(f"⚠️ ข้อมูลบอส **{boss}** ไม่ครบ (cooldown หรือ lastDeath หาย) กรุณาตรวจสอบ")
            invalid_data_bosses.add(boss)
        return
    else:
        invalid_data_bosses.discard(boss)

    try:
        cooldown_ms = float(cooldown) * 1000
        last_death = int(last_death)
        if cooldown_ms <= 0 or last_death <= 0:
            raise ValueError("ค่าต้องมากกว่า 0")
    except Exception as e:
        logging.warning(f"{boss}: cooldown/lastDeath ไม่ถูกต้อง: {e}")
        return

    spawn_time = last_death + cooldown_ms
    time_diff = spawn_time - now_ts

    # Debug log for time sync
    logging.debug(
        f"[{boss}] now_ts={now_ts} | last_death={last_death} ({format_timestamp(last_death)}) | "
        f"spawn_time={spawn_time} ({format_timestamp(spawn_time)}) | time_diff={time_diff} ms"
    )

    # Reset alert flags if lastDeath changed
    if boss not in last_death_record or last_death_record[boss] != last_death:
        logging.info(f"{boss}: lastDeath เปลี่ยน รีเซ็ตสถานะแจ้งเตือน")
        notified_5_min.discard(boss)
        notified_3_min.discard(boss)
        notified_spawned.discard(boss)
        last_death_record[boss] = last_death

    # Trigger notifications
    if 0 <= time_diff <= 300000 and boss not in notified_5_min:
        notify_discord(f"⏰ **[แจ้งเตือน]** บอส **{boss}** จะเกิดใน 5 นาที ({format_timestamp(spawn_time)}) ⚔️{format_owner(owner)}")
        notified_5_min.add(boss)

    elif 0 <= time_diff <= 180000 and boss not in notified_3_min:
        notify_discord(f"⌛ **[เตือนอีกครั้ง]** บอส **{boss}** จะเกิดใน 3 นาที ({format_timestamp(spawn_time)}) 🛡️{format_owner(owner)}")
        notified_3_min.add(boss)

    elif time_diff <= 0 and boss not in notified_spawned:
        notify_discord(f"🎉 **[แจ้งเตือน]** บอส **{boss}** เกิดแล้วเมื่อ {format_timestamp(spawn_time)} 💥{format_owner(owner)}")
        notified_spawned.add(boss)

def monitor_bosses():
    tz = pytz.timezone("Asia/Bangkok")
    logging.info("🔄 เริ่มทำงาน Boss Timer Monitor")
    while True:
        bosses = fetch_boss_data()
        if not bosses:
            logging.warning("❌ ไม่พบข้อมูลบอส")
            time.sleep(30)
            continue

        now_ts = int(datetime.now(tz).timestamp() * 1000)

        for boss, info in bosses.items():
            process_boss(boss, info, now_ts)

        time.sleep(30)

if __name__ == "__main__":
    thread = threading.Thread(target=monitor_bosses)
    thread.daemon = True
    thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("🛑 หยุดทำงานแล้ว")
