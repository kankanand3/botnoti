import logging
import time
import requests
from datetime import datetime
import pytz
import re
import threading

# Logging Setup
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Config
FIREBASE_URL = "https://bosstimer-2a778-default-rtdb.asia-southeast1.firebasedatabase.app/.json"
DISCORD_WEBHOOK_URL = "https://ptb.discord.com/api/webhooks/1382831229681930300/gFhSSjfKBamc9hFGBJ7KEZOEcSpPjBmV3h8t_o5n6pGfCsIWeGFhIZbGYtF9IDlQcZOW"
DISCORD_SWORD_WEBHOOK_URL = "https://ptb.discord.com/api/webhooks/1383767117198790727/PKfhWSBQRglLAKYQprS9DVmkh-xVJ3lRmEKWzPqp_VWqIrLqafFoWJrbLlsn7v9lRem-"
GUARDIAN_ROLE_ID = "1377155652480401499"

# State Tracking
notified_5_min = set()
notified_3_min = set()
notified_spawned = set()
last_death_record = {}

sword_notify_flags = {
    "+0": set(),
    "+30": set(),
    "+60": set(),
    "+90": set(),
    "+max": set(),
}
last_death_sword_record = {}

def sanitize_boss_name(name):
    return re.sub(r'[^\w\sก-๙]', '', name).strip()

def fetch_boss_data(retries=3, delay=5):
    for attempt in range(retries):
        try:
            response = requests.get(FIREBASE_URL, timeout=10)
            if response.status_code == 200:
                data = response.json()
                logging.info("Fetched data from Firebase successfully.")
                return data
            else:
                logging.warning(f"Firebase response status: {response.status_code}")
        except Exception as e:
            logging.error(f"Fetch failed: {e}")
        time.sleep(delay)
    logging.error("Failed to fetch data from Firebase after retries.")
    return {}

def notify_discord(message):
    tagged = f"<@&{GUARDIAN_ROLE_ID}>\n\n{message}"
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": tagged}, timeout=10)
        response.raise_for_status()
        logging.info(f"Notify Discord: {message}")
    except Exception as e:
        logging.error(f"Failed to notify Discord: {e}")

def notify_sword_discord(message):
    tagged = f"<@&{GUARDIAN_ROLE_ID}>\n\n{message}"
    try:
        response = requests.post(DISCORD_SWORD_WEBHOOK_URL, json={"content": tagged}, timeout=10)
        response.raise_for_status()
        logging.info(f"Notify Sword Discord: {message}")
    except Exception as e:
        logging.error(f"Failed to notify Sword Discord: {e}")

def format_owner(owner):
    return f"\n\n👑 เจ้าของบอส: **{owner.strip()}**" if owner else ""

def format_timestamp(ts_ms):
    tz = pytz.timezone("Asia/Bangkok")
    return datetime.fromtimestamp(ts_ms / 1000, tz).strftime("%H:%M น.")

def process_boss(boss, info, now_ts):
    try:
        name = sanitize_boss_name(boss)
        cooldown = info.get("cooldown")
        last_death = info.get("lastDeath")
        owner = info.get("owner", "")

        if cooldown is None or last_death is None:
            return

        cooldown_ms = float(cooldown) * 1000
        last_death = int(last_death)

        spawn_time = last_death + cooldown_ms
        diff = spawn_time - now_ts

        # รีเซตสถานะเมื่อ lastDeath เปลี่ยน
        if name not in last_death_record or last_death_record[name] != last_death:
            notified_5_min.discard(name)
            notified_3_min.discard(name)
            notified_spawned.discard(name)
            last_death_record[name] = last_death
            logging.info(f"Reset notify status for boss {name}")

        # แจ้งเตือน 5 นาที
        if 0 <= diff <= 300000 and name not in notified_5_min:
            notify_discord(f"⏰ **[แจ้งเตือน]** บอส **{name}** จะเกิดใน 5 นาที ({format_timestamp(spawn_time)}) ⚔️{format_owner(owner)}")
            notified_5_min.add(name)

        # แจ้งเตือน 3 นาที (แยกแจ้งซ้อนกับ 5 นาทีได้)
        if 0 <= diff <= 180000 and name not in notified_3_min:
            notify_discord(f"⌛ **[เตือนอีกครั้ง]** บอส **{name}** จะเกิดใน 3 นาที ({format_timestamp(spawn_time)}) 🛡️{format_owner(owner)}")
            notified_3_min.add(name)

        # แจ้งเตือนบอสเกิดแล้ว
        if diff <= 0 and name not in notified_spawned:
            notify_discord(f"🎉 **[แจ้งเตือน]** บอส **{name}** เกิดแล้วเมื่อ {format_timestamp(spawn_time)} 💥{format_owner(owner)}")
            notified_spawned.add(name)

    except Exception as e:
        logging.error(f"Error processing boss {boss}: {e}")

def process_sword(sword, info, now_ts):
    try:
        name = sanitize_boss_name(sword)
        last_death = info.get("lastDeath")
        cooldown_min = info.get("cooldownMin")
        cooldown_max = info.get("cooldownMax")

        if last_death is None or cooldown_min is None or cooldown_max is None:
            return

        last_death_ms = int(last_death)
        cooldown_min_ms = float(cooldown_min) * 1000
        cooldown_max_ms = float(cooldown_max) * 1000

        # รีเซตสถานะเมื่อ lastDeath เปลี่ยน
        if name not in last_death_sword_record or last_death_sword_record[name] != last_death_ms:
            for stage_set in sword_notify_flags.values():
                stage_set.discard(name)
            last_death_sword_record[name] = last_death_ms
            logging.info(f"Reset sword notify status for {name}")

        elapsed = now_ts - last_death_ms

        alert_stages = {
            "+0": cooldown_min_ms,
            "+30": cooldown_min_ms + 30 * 60 * 1000,
            "+60": cooldown_min_ms + 60 * 60 * 1000,
            "+90": cooldown_min_ms + 90 * 60 * 1000,
            "+max": cooldown_max_ms,
        }

        tz = pytz.timezone("Asia/Bangkok")
        last_death_str = datetime.fromtimestamp(last_death_ms / 1000, tz).strftime("%H:%M น.")
        cooldown_min_done_str = datetime.fromtimestamp((last_death_ms + cooldown_min_ms) / 1000, tz).strftime("%H:%M น.")
        now_str = datetime.fromtimestamp(now_ts / 1000, tz).strftime("%H:%M น.")

        for label, wait_time in alert_stages.items():
            if elapsed >= wait_time and name not in sword_notify_flags[label]:
                if label == "+max":
                    message = (
                        f"🗡️ บอสดาบ! {name}\n\n"
                        f"🕒 บอสตายล่าสุด: {last_death_str}\n"
                        f"⏳ คูลดาวน์ขั้นต่ำครบเวลา: {cooldown_min_done_str}\n"
                        f"🕔 แจ้งเตือนตอนนี้: {now_str} (ผ่านมา {int((wait_time - cooldown_min_ms) / 60000)} นาทีหลัง cooldown ขั้นต่ำ)\n\n"
                        f"⚠️ หากยังไม่เกิด แสดงว่า ถูกฆ่าไปแล้ว"
                    )
                else:
                    # แก้ตรงนี้ให้ +0 แจ้งผ่าน 0 นาที (คูลดาวน์ขั้นต่ำครบพอดี)
                    if label == "+0":
                        minutes_passed = 0
                    else:
                        minutes_passed = int(label[1:])
                    message = (
                        f"🗡️ บอสดาบ! {name}\n\n"
                        f"🕒 บอสตายล่าสุด: {last_death_str}\n"
                        f"⏳ คูลดาวน์ขั้นต่ำครบเวลา: {cooldown_min_done_str}\n"
                        f"🕔 แจ้งเตือนตอนนี้: {now_str} (ผ่านมา {minutes_passed} นาทีหลัง cooldown ขั้นต่ำ)"
                    )
                notify_sword_discord(message)
                sword_notify_flags[label].add(name)

    except Exception as e:
        logging.error(f"Error processing sword {sword}: {e}")

def monitor_all():
    tz = pytz.timezone("Asia/Bangkok")
    while True:
        data = fetch_boss_data()
        now_ts = int(datetime.now(tz).timestamp() * 1000)

        bosses = data.get("bosses", {})
        swords = data.get("swords", {})

        if not bosses:
            logging.warning("No bosses data found in Firebase.")
        else:
            for boss, info in bosses.items():
                process_boss(boss, info, now_ts)

        if not swords:
            logging.warning("No swords data found in Firebase.")
        else:
            for sword, info in swords.items():
                process_sword(sword, info, now_ts)

        time.sleep(30)

if __name__ == "__main__":
    logging.info("Starting boss monitor (single thread fetch)...")
    threading.Thread(target=monitor_all, daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("🛑 Stopped")
