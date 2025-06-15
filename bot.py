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
DISCORD_SWORD_WEBHOOK_URL = "https://ptb.discord.com/api/webhooks/1383767117198790727/PKfhWSBQRglLAKYQprS9DVmkh-xVJ3lRmEKWzPqp_VWqIrLqafFoWJrbLlsn7v9lRem-"
GUARDIAN_ROLE_ID = "1377155652480401499"

notified_5_min = set()
notified_3_min = set()
notified_spawned = set()
last_death_record = {}
invalid_data_bosses = set()

sword_notify_flags = {
    "+0": set(),
    "+30": set(),
    "+60": set(),
    "+90": set(),
    "+120": set(),
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
                return data
        except Exception as e:
            logging.error(f"Fetch failed: {e}")
        time.sleep(delay)
    return {}

def notify_discord(message):
    tagged = f"<@&{GUARDIAN_ROLE_ID}>\n\n{message}"
    requests.post(DISCORD_WEBHOOK_URL, json={"content": tagged}, timeout=10)

def notify_sword_discord(message):
    tagged = f"<@&{GUARDIAN_ROLE_ID}>\n\n{message}"
    requests.post(DISCORD_SWORD_WEBHOOK_URL, json={"content": tagged}, timeout=10)

def format_owner(owner):
    return f"\n\n👑 เจ้าของบอส: **{owner.strip()}**" if owner else ""

def format_timestamp(ts_ms):
    tz = pytz.timezone("Asia/Bangkok")
    return datetime.fromtimestamp(ts_ms / 1000, tz).strftime("%H:%M น.")

def process_boss(boss, info, now_ts):
    name = sanitize_boss_name(boss)
    cooldown = info.get("cooldown")
    last_death = info.get("lastDeath")
    owner = info.get("owner", "")

    if cooldown is None or last_death is None:
        return

    try:
        cooldown_ms = float(cooldown) * 1000
        last_death = int(last_death)
    except:
        return

    spawn_time = last_death + cooldown_ms
    diff = spawn_time - now_ts

    if name not in last_death_record or last_death_record[name] != last_death:
        notified_5_min.discard(name)
        notified_3_min.discard(name)
        notified_spawned.discard(name)
        last_death_record[name] = last_death

    if 0 <= diff <= 300000 and name not in notified_5_min:
        notify_discord(f"⏰ **[แจ้งเตือน]** บอส **{name}** จะเกิดใน 5 นาที ({format_timestamp(spawn_time)}) ⚔️{format_owner(owner)}")
        notified_5_min.add(name)

    elif 0 <= diff <= 180000 and name not in notified_3_min:
        notify_discord(f"⌛ **[เตือนอีกครั้ง]** บอส **{name}** จะเกิดใน 3 นาที ({format_timestamp(spawn_time)}) 🛡️{format_owner(owner)}")
        notified_3_min.add(name)

    elif diff <= 0 and name not in notified_spawned:
        notify_discord(f"🎉 **[แจ้งเตือน]** บอส **{name}** เกิดแล้วเมื่อ {format_timestamp(spawn_time)} 💥{format_owner(owner)}")
        notified_spawned.add(name)

def process_sword(sword, info, now_ts):
    name = sanitize_boss_name(sword)
    last_death = info.get("lastDeath")
    cooldown_min = info.get("cooldownMin")
    if last_death is None or cooldown_min is None:
        return

    try:
        last_death = int(last_death)
        cooldown_min_ms = float(cooldown_min) * 1000
    except:
        return

    if name not in last_death_sword_record or last_death_sword_record[name] != last_death:
        for stage in sword_notify_flags:
            sword_notify_flags[stage].discard(name)
        last_death_sword_record[name] = last_death

    elapsed = now_ts - last_death
    alert_stages = {
        "+0": 0,
        "+30": 30 * 1000,
        "+60": 60 * 1000,
        "+90": 90 * 1000,
        "+120": 120 * 1000,
    }

    for label, wait_time in alert_stages.items():
        if elapsed >= cooldown_min_ms + wait_time and name not in sword_notify_flags[label]:
            if label == "+120":
                notify_sword_discord(
                    f"🗡️ **บอสดาบ!** {name}\n\n🕓 ผ่านมาแล้ว **120 นาที** หลังครบ cooldown.\n\n⚠️ หากยังไม่เกิด แสดงว่า **ถูกฆ่าไปแล้ว**"
                )
            else:
                notify_sword_discord(
                    f"🗡️ **บอสดาบ!** {name}\n\n⏳ ผ่านมาแล้ว **{label[1:]} นาที** หลังครบ cooldown."
                )
            sword_notify_flags[label].add(name)

def monitor_bosses():
    tz = pytz.timezone("Asia/Bangkok")
    while True:
        data = fetch_boss_data()
        now_ts = int(datetime.now(tz).timestamp() * 1000)
        for boss, info in data.get("bosses", {}).items():
            process_boss(boss, info, now_ts)
        time.sleep(30)

def monitor_swords():
    tz = pytz.timezone("Asia/Bangkok")
    while True:
        data = fetch_boss_data()
        now_ts = int(datetime.now(tz).timestamp() * 1000)
        for sword, info in data.get("swords", {}).items():
            process_sword(sword, info, now_ts)
        time.sleep(30)

if __name__ == "__main__":
    threading.Thread(target=monitor_bosses, daemon=True).start()
    threading.Thread(target=monitor_swords, daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("🛑 หยุดทำงานแล้ว")
