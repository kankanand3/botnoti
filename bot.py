import logging
import time
import requests
import threading
from datetime import datetime
import pytz

# ตั้งค่า logging
logging.basicConfig(
    level=logging.INFO,  # เปลี่ยนเป็น logging.DEBUG เพื่อดู log เยอะขึ้น
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
                    logging.warning("ข้อมูลบอสใน Firebase ไม่มี key 'bosses'")
                    return {}
            else:
                logging.error(f"ดึงข้อมูลล้มเหลว (สถานะ {response.status_code})")
        except Exception as e:
            logging.error(f"ดึงข้อมูลล้มเหลว (ข้อผิดพลาด: {e})")

        if attempt < retries:
            logging.info(f"กำลังลองใหม่ครั้งที่ {attempt + 1} หลัง {delay} วินาที...")
            time.sleep(delay)

    logging.error("ดึงข้อมูลบอสล้มเหลวหลังลองหลายครั้ง")
    return {}

def notify_discord(message):
    tagged_message = f"<@&{GUARDIAN_ROLE_ID}>\n\n{message}\n"
    logging.info(f"ส่งแจ้งเตือน Discord: {message}")
    try:
        response = requests.post(DISCORD_WEBHOOK_URL, json={"content": tagged_message}, timeout=10)
        if response.status_code not in (200, 204):
            logging.error(f"แจ้งเตือน Discord ไม่สำเร็จ (สถานะ {response.status_code})")
    except Exception as e:
        logging.error(f"แจ้งเตือนไม่สำเร็จ: {e}")

def format_owner(owner):
    if owner and owner.strip():
        return f"\n👑 เจ้าของบอส: **{owner.strip()}**"
    return ""

def format_timestamp(ts_ms):
    if ts_ms is None:
        return "-"
    tz = pytz.timezone("Asia/Bangkok")
    dt = datetime.fromtimestamp(ts_ms / 1000, tz)
    return dt.strftime("%H:%M น.")

def process_boss(boss, info, now_ts):
    cooldown = info.get("cooldown")
    last_death = info.get("lastDeath")
    owner = info.get("owner", "").strip() if info.get("owner") else ""

    if cooldown is None or last_death is None:
        if boss not in invalid_data_bosses:
            logging.warning(f"ข้อมูลบอส {boss} ไม่ครบถ้วน (cooldown หรือ lastDeath หายไป)")
            notify_discord(f"⚠️ ข้อมูลบอส **{boss}** ไม่ครบถ้วน (cooldown หรือ lastDeath หายไป) กรุณาตรวจสอบข้อมูลใน Firebase")
            invalid_data_bosses.add(boss)
        return
    else:
        if boss in invalid_data_bosses:
            logging.info(f"ข้อมูลบอส {boss} กลับมาครบถ้วนแล้ว")
            invalid_data_bosses.remove(boss)

    try:
        cooldown_ms = float(cooldown) * 1000
        last_death = int(last_death)
        if cooldown_ms <= 0 or last_death <= 0:
            logging.warning(f"ข้อมูลบอส {boss} ผิดพลาด: cooldown หรือ lastDeath ต้องเป็นค่าบวก")
            if boss not in invalid_data_bosses:
                notify_discord(f"⚠️ ข้อมูลบอส **{boss}** ผิดพลาด: cooldown หรือ lastDeath ต้องเป็นค่าบวก กรุณาตรวจสอบข้อมูลใน Firebase")
                invalid_data_bosses.add(boss)
            return

    except Exception as e:
        logging.warning(f"ข้อมูลบอส {boss} ไม่ถูกต้อง (cooldown หรือ lastDeath ไม่ใช่ตัวเลข): {e}")
        return

    spawn_time = last_death + cooldown_ms
    time_diff = spawn_time - now_ts

    spawn_time_str = format_timestamp(spawn_time)
    last_death_str = format_timestamp(last_death)

    if boss not in last_death_record or last_death_record[boss] != last_death:
        notified_5_min.discard(boss)
        notified_3_min.discard(boss)
        notified_spawned.discard(boss)
        last_death_record[boss] = last_death
        logging.info(f"รีเซ็ตสถานะแจ้งเตือนบอส {boss}")

    logging.debug(f"[{boss}] cooldown={cooldown_ms} ms, lastDeath={last_death}, spawn_time={spawn_time}, time_diff={time_diff} ms")

    if 0 <= time_diff <= 300000 and boss not in notified_5_min:
        notify_discord(
            f"⏰ **[แจ้งเตือน]** บอส **{boss}** กำลังจะเกิดในอีก 5 นาที ({spawn_time_str})! เตรียมตัวให้พร้อม! ⚔️{format_owner(owner)}"
        )
        notified_5_min.add(boss)
    elif 0 <= time_diff <= 180000 and boss not in notified_3_min:
        notify_discord(
            f"⌛ **[เตือนอีกครั้ง]** บอส **{boss}** กำลังจะเกิดใน 3 นาที ({spawn_time_str})! 🛡️ อย่าพลาดโอกาส! 🔥{format_owner(owner)}"
        )
        notified_3_min.add(boss)
    elif time_diff <= 0 and boss not in notified_spawned:
        notify_discord(
            f"🎉 **[แจ้งเตือน]** บอส **{boss}** เกิดแล้วเวลา {spawn_time_str}! พร้อมลุย! 💥{format_owner(owner)}"
        )
        notified_spawned.add(boss)

def monitor_bosses():
    logging.info("Bot กำลังทำงาน...")
    tz = pytz.timezone("Asia/Bangkok")

    while True:
        bosses = fetch_boss_data()
        if not bosses:
            logging.warning("ไม่มีข้อมูลบอสในรอบนี้")
            time.sleep(30)  # ดึงข้อมูลทุก 30 วินาที
            continue

        logging.info(f"ดึงข้อมูลบอสได้ {len(bosses)} ตัว")
        for boss, info in bosses.items():
            logging.debug(f"  - {boss}: cooldown={info.get('cooldown')}, lastDeath={info.get('lastDeath')}, owner={info.get('owner', '')}")

        now = datetime.now(tz)
        now_ts = int(now.timestamp() * 1000)

        for boss, info in bosses.items():
            process_boss(boss, info, now_ts)

        logging.debug("รอ 30 วินาที ก่อนตรวจรอบถัดไป")
        time.sleep(30)  # ดึงข้อมูลทุก 30 วินาที

if __name__ == "__main__":
    monitor_thread = threading.Thread(target=monitor_bosses)
    monitor_thread.daemon = True
    monitor_thread.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logging.info("Bot หยุดทำงานโดยผู้ใช้")
