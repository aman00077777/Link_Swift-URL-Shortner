import random
import string
import base64
import contextlib
import requests
import os
from io import BytesIO
from datetime import datetime, timedelta
import qrcode
from config import Config

USE_POSTGRES = bool(Config.DATABASE_URL)

if USE_POSTGRES:
    import psycopg2
    import psycopg2.extras
else:
    import sqlite3


@contextlib.contextmanager
def get_db_conn():
    if USE_POSTGRES:
        conn = psycopg2.connect(Config.DATABASE_URL)
        conn.autocommit = False
        try:
            yield conn
        finally:
            conn.close()
    else:
        import sqlite3
        conn = sqlite3.connect(Config.DATABASE_FILE, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()


def fetchone(cursor):
    row = cursor.fetchone()
    if row is None:
        return None
    if USE_POSTGRES:
        cols = [desc[0] for desc in cursor.description]
        return dict(zip(cols, row))
    return dict(row)


def fetchall(cursor):
    rows = cursor.fetchall()
    if USE_POSTGRES:
        cols = [desc[0] for desc in cursor.description]
        return [dict(zip(cols, row)) for row in rows]
    return [dict(row) for row in rows]


def db_init():
    with get_db_conn() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS urls (
                    id SERIAL PRIMARY KEY,
                    original_url TEXT NOT NULL,
                    short_code TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    qr_code_base64 TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS clicks (
                    id SERIAL PRIMARY KEY,
                    url_id INTEGER NOT NULL REFERENCES urls(id) ON DELETE CASCADE,
                    timestamp TEXT NOT NULL,
                    ip_address TEXT,
                    country TEXT,
                    device TEXT,
                    browser TEXT,
                    referrer TEXT
                )
            """)
        else:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS urls (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    original_url TEXT NOT NULL,
                    short_code TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL,
                    qr_code_base64 TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS clicks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url_id INTEGER NOT NULL,
                    timestamp TEXT NOT NULL,
                    ip_address TEXT,
                    country TEXT,
                    device TEXT,
                    browser TEXT,
                    referrer TEXT,
                    FOREIGN KEY (url_id) REFERENCES urls(id) ON DELETE CASCADE
                )
            """)
        conn.commit()


def generate_short_code(length=6):
    characters = string.ascii_letters + string.digits
    while True:
        code = "".join(random.choices(characters, k=length))
        with get_db_conn() as conn:
            cur = conn.cursor()
            if USE_POSTGRES:
                cur.execute("SELECT 1 FROM urls WHERE short_code = %s", (code,))
            else:
                cur.execute("SELECT 1 FROM urls WHERE short_code = ?", (code,))
            if not cur.fetchone():
                return code


def generate_qr_base64(target_url):
    try:
        qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#2b2d42", back_color="#ffffff")
        buffered = BytesIO()
        try:
            save_func = getattr(img, "save")
            save_func(buffered, format="PNG")
        except TypeError:
            img.save(buffered)
        img_str = base64.b64encode(buffered.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{img_str}"
    except Exception as e:
        print(f"Error generating QR code: {e}")
        return ""


def create_short_url(original_url, custom_code=None):
    if custom_code:
        with get_db_conn() as conn:
            cur = conn.cursor()
            if USE_POSTGRES:
                cur.execute("SELECT 1 FROM urls WHERE short_code = %s", (custom_code,))
            else:
                cur.execute("SELECT 1 FROM urls WHERE short_code = ?", (custom_code,))
            if cur.fetchone():
                return None
        short_code = custom_code
    else:
        short_code = generate_short_code()

    shortened_link = f"{Config.BASE_URL}/{short_code}"
    qr_base64 = generate_qr_base64(shortened_link)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db_conn() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute(
                "INSERT INTO urls (original_url, short_code, created_at, qr_code_base64) VALUES (%s, %s, %s, %s) RETURNING id",
                (original_url, short_code, created_at, qr_base64)
            )
            url_id = cur.fetchone()[0]
            conn.commit()
            cur.execute("SELECT * FROM urls WHERE id = %s", (url_id,))
        else:
            cur.execute(
                "INSERT INTO urls (original_url, short_code, created_at, qr_code_base64) VALUES (?, ?, ?, ?)",
                (original_url, short_code, created_at, qr_base64)
            )
            conn.commit()
            url_id = cur.lastrowid
            cur.execute("SELECT * FROM urls WHERE id = ?", (url_id,))
        return fetchone(cur)


def get_url_by_code(short_code):
    with get_db_conn() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute("SELECT * FROM urls WHERE short_code = %s", (short_code,))
        else:
            cur.execute("SELECT * FROM urls WHERE short_code = ?", (short_code,))
        return fetchone(cur)


def get_url_by_id(url_id):
    with get_db_conn() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute("SELECT * FROM urls WHERE id = %s", (url_id,))
        else:
            cur.execute("SELECT * FROM urls WHERE id = ?", (url_id,))
        return fetchone(cur)


def get_recent_urls(limit=10):
    with get_db_conn() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute("SELECT * FROM urls ORDER BY id DESC LIMIT %s", (limit,))
        else:
            cur.execute("SELECT * FROM urls ORDER BY id DESC LIMIT ?", (limit,))
        return fetchall(cur)


def parse_user_agent(ua_string):
    if not ua_string:
        return "Unknown", "Unknown"
    ua = ua_string.lower()
    if "windows" in ua:
        device = "Windows"
    elif "iphone" in ua:
        device = "iPhone"
    elif "ipad" in ua:
        device = "iPad"
    elif "android" in ua:
        device = "Android"
    elif "macintosh" in ua or "mac os" in ua:
        device = "macOS"
    elif "linux" in ua:
        device = "Linux"
    else:
        device = "Other"

    if "edg/" in ua or "edge" in ua:
        browser = "Edge"
    elif "opr/" in ua or "opera" in ua:
        browser = "Opera"
    elif "chrome" in ua or "crios" in ua:
        browser = "Chrome"
    elif "firefox" in ua or "fxios" in ua:
        browser = "Firefox"
    elif "safari" in ua:
        browser = "Safari"
    elif "msie" in ua or "trident" in ua:
        browser = "Internet Explorer"
    else:
        browser = "Other"

    return device, browser


def get_country_from_ip(ip):
    if not ip or ip in ("127.0.0.1", "::1", "localhost"):
        return "Localhost"
    ip_parts = ip.split(".")
    if len(ip_parts) == 4:
        try:
            p1, p2 = int(ip_parts[0]), int(ip_parts[1])
            if p1 == 10 or (p1 == 172 and 16 <= p2 <= 31) or (p1 == 192 and p2 == 168):
                return "Localhost"
        except ValueError:
            pass
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=1.5)
        if response.status_code == 200:
            data = response.json()
            if data.get("status") == "success":
                return data.get("country", "Unknown")
    except Exception:
        pass
    return "Unknown"


def record_click(url_id, ip_address, user_agent_string, referrer):
    device, browser = parse_user_agent(user_agent_string)
    country = get_country_from_ip(ip_address)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    referrer = referrer.strip().rstrip("/") if referrer else "Direct"

    with get_db_conn() as conn:
        cur = conn.cursor()
        if USE_POSTGRES:
            cur.execute("""
                INSERT INTO clicks (url_id, timestamp, ip_address, country, device, browser, referrer)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (url_id, timestamp, ip_address, country, device, browser, referrer))
        else:
            cur.execute("""
                INSERT INTO clicks (url_id, timestamp, ip_address, country, device, browser, referrer)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (url_id, timestamp, ip_address, country, device, browser, referrer))
        conn.commit()


def get_url_analytics(url_id=None):
    if USE_POSTGRES:
        ph = "%s"
    else:
        ph = "?"

    condition = f"WHERE url_id = {ph}" if url_id is not None else ""
    params = (url_id,) if url_id is not None else ()

    with get_db_conn() as conn:
        cur = conn.cursor()

        cur.execute(f"SELECT COUNT(*) FROM clicks {condition}", params)
        total_clicks = cur.fetchone()[0]

        cur.execute(f"SELECT COUNT(DISTINCT ip_address) FROM clicks {condition}", params)
        unique_ips = cur.fetchone()[0]

        cur.execute(f"""
            SELECT country, COUNT(*) as c FROM clicks {condition}
            GROUP BY country ORDER BY c DESC LIMIT 1
        """, params)
        row = cur.fetchone()
        top_country = row[0] if row else "N/A"

        cur.execute(f"""
            SELECT device, COUNT(*) as c FROM clicks {condition}
            GROUP BY device ORDER BY c DESC LIMIT 1
        """, params)
        row = cur.fetchone()
        top_device = row[0] if row else "N/A"

        cur.execute(f"""
            SELECT timestamp as date, COUNT(*) as count
            FROM clicks {condition}
            GROUP BY timestamp ORDER BY timestamp ASC
        """, params)
        timeline = [{"date": r[0], "clicks": r[1]} for r in cur.fetchall()]

        cur.execute(f"""
            SELECT device, COUNT(*) as count FROM clicks {condition}
            GROUP BY device ORDER BY count DESC
        """, params)
        devices = [{"name": r[0], "value": r[1]} for r in cur.fetchall()]

        cur.execute(f"""
            SELECT country, COUNT(*) as count FROM clicks {condition}
            GROUP BY country ORDER BY count DESC
        """, params)
        countries = [{"name": r[0], "value": r[1]} for r in cur.fetchall()]

        cur.execute(f"""
            SELECT browser, COUNT(*) as count FROM clicks {condition}
            GROUP BY browser ORDER BY count DESC
        """, params)
        browsers = [{"name": r[0], "value": r[1]} for r in cur.fetchall()]

        cur.execute(f"""
            SELECT referrer, COUNT(*) as count FROM clicks {condition}
            GROUP BY referrer ORDER BY count DESC
        """, params)
        referrers = [{"name": r[0], "value": r[1]} for r in cur.fetchall()]

        cur.execute(f"""
            SELECT timestamp, ip_address, country, device, browser, referrer
            FROM clicks {condition}
            ORDER BY id DESC LIMIT 50
        """, params)
        cols = ["timestamp", "ip_address", "country", "device", "browser", "referrer"]
        recent_clicks = [dict(zip(cols, r)) for r in cur.fetchall()]

    return {
        "kpis": {
            "total_clicks": total_clicks,
            "unique_visitors": unique_ips,
            "top_country": top_country,
            "top_device": top_device
        },
        "charts": {
            "timeline": timeline,
            "devices": devices,
            "countries": countries,
            "browsers": browsers,
            "referrers": referrers
        },
        "recent_clicks": recent_clicks
    }


def simulate_test_clicks(url_id, count=50):
    countries_list = ["United States", "United Kingdom", "Germany", "Canada", "Japan", "Australia", "France", "India", "Brazil", "Singapore"]
    devices_list = ["Windows", "macOS", "iPhone", "Android", "iPad", "Linux"]
    browsers_list = ["Chrome", "Safari", "Firefox", "Edge", "Opera"]
    referrers_list = ["Direct", "https://google.com", "https://t.co", "https://linkedin.com", "https://github.com"]

    with get_db_conn() as conn:
        cur = conn.cursor()
        for _ in range(count):
            days_ago = random.randint(0, 9)
            click_time = datetime.now() - timedelta(
                days=days_ago,
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59)
            )
            timestamp_str = click_time.strftime("%Y-%m-%d %H:%M:%S")
            ip = f"{random.randint(24,220)}.{random.randint(10,240)}.{random.randint(0,254)}.{random.randint(1,254)}"
            country = random.choices(countries_list, weights=[30,15,10,8,8,7,6,8,4,2], k=1)[0]
            device = random.choices(devices_list, weights=[40,25,18,12,3,2], k=1)[0]
            browser = random.choices(browsers_list, weights=[55,20,12,8,5], k=1)[0]
            referrer = random.choices(referrers_list, weights=[40,25,12,10,8], k=1)[0]

            if USE_POSTGRES:
                cur.execute("""
                    INSERT INTO clicks (url_id, timestamp, ip_address, country, device, browser, referrer)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (url_id, timestamp_str, ip, country, device, browser, referrer))
            else:
                cur.execute("""
                    INSERT INTO clicks (url_id, timestamp, ip_address, country, device, browser, referrer)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (url_id, timestamp_str, ip, country, device, browser, referrer))
        conn.commit()