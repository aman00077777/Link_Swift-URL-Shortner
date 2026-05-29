import sqlite3
import random
import string
import base64
import contextlib
import requests
from io import BytesIO
from datetime import datetime, timedelta
import qrcode
from config import Config


@contextlib.contextmanager
def get_db_conn():
    """Establish a connection to the SQLite database with row factory enabled, closing it afterwards."""
    conn = sqlite3.connect(Config.DATABASE_FILE, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
    finally:
        conn.close()


def db_init():
    """Initialize database tables for URL mappings and analytical tracking."""
    with get_db_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS urls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                original_url TEXT NOT NULL,
                short_code TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                qr_code_base64 TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS clicks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_id INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                ip_address TEXT,
                country TEXT,
                device TEXT,
                browser TEXT,
                referrer TEXT,
                FOREIGN KEY (url_id) REFERENCES urls (id) ON DELETE CASCADE
            )
        """)
        conn.commit()


def generate_short_code(length=6):
    """Generate a unique random alphanumeric short code."""
    characters = string.ascii_letters + string.digits
    while True:
        code = "".join(random.choices(characters, k=length))
        # Verify uniqueness
        with get_db_conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM urls WHERE short_code = ?", (code,)).fetchone()
            if not row:
                return code


def generate_qr_base64(target_url):
    """Generate a QR code image as a Base64 encoded string."""
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=4,
        )
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
    """
    Persists original URL and short code.
    Returns the created record as a dictionary or None if custom code is taken.
    """
    if custom_code:
        # Validate custom code uniqueness
        with get_db_conn() as conn:
            exists = conn.execute(
                "SELECT 1 FROM urls WHERE short_code = ?", (custom_code,)).fetchone()
            if exists:
                return None
        short_code = custom_code
    else:
        short_code = generate_short_code()

    # Pre-generate QR code base64
    shortened_link = f"{Config.BASE_URL}/{short_code}"
    qr_base64 = generate_qr_base64(shortened_link)
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_db_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO urls (original_url, short_code, created_at, qr_code_base64) VALUES (?, ?, ?, ?)",
            (original_url, short_code, created_at, qr_base64)
        )
        conn.commit()
        url_id = cursor.lastrowid

        # Retrieve and return the created record
        row = conn.execute(
            "SELECT * FROM urls WHERE id = ?", (url_id,)).fetchone()
        return dict(row) if row else None


def get_url_by_code(short_code):
    """Retrieve URL mapping details using the short code."""
    with get_db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM urls WHERE short_code = ?", (short_code,)).fetchone()
        return dict(row) if row else None


def get_url_by_id(url_id):
    """Retrieve URL mapping details using the primary ID."""
    with get_db_conn() as conn:
        row = conn.execute(
            "SELECT * FROM urls WHERE id = ?", (url_id,)).fetchone()
        return dict(row) if row else None


def get_recent_urls(limit=10):
    """Get the list of recently created shortened URLs."""
    with get_db_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM urls ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def parse_user_agent(ua_string):
    """Parse User Agent string to extract Device OS and Web Browser classifications."""
    if not ua_string:
        return "Unknown", "Unknown"

    ua = ua_string.lower()

    # Device / OS classification
    if "windows" in ua:
        device = "Windows"
    elif "macintosh" in ua or "mac os" in ua:
        if "iphone" in ua:
            device = "iPhone"
        elif "ipad" in ua:
            device = "iPad"
        else:
            device = "macOS"
    elif "android" in ua:
        device = "Android"
    elif "iphone" in ua:
        device = "iPhone"
    elif "ipad" in ua:
        device = "iPad"
    elif "linux" in ua:
        device = "Linux"
    else:
        device = "Other"

    # Browser classification
    if "edg/" in ua or "edge" in ua:
        browser = "Edge"
    elif "chrome" in ua or "crios" in ua:
        if "opr/" in ua or "opera" in ua:
            browser = "Opera"
        else:
            browser = "Chrome"
    elif "firefox" in ua or "fxios" in ua:
        browser = "Firefox"
    elif "safari" in ua and "chrome" not in ua:
        browser = "Safari"
    elif "msie" in ua or "trident" in ua:
        browser = "Internet Explorer"
    else:
        browser = "Other"

    return device, browser


def get_country_from_ip(ip):
    """Resolve country from IP Address using the ip-api service with cache-friendly fallbacks."""
    if not ip or ip in ("127.0.0.1", "::1", "localhost"):
        return "Localhost"

    # Check for private IP ranges
    ip_parts = ip.split(".")
    if len(ip_parts) == 4:
        try:
            p1 = int(ip_parts[0])
            p2 = int(ip_parts[1])
            if p1 == 10 or (p1 == 172 and 16 <= p2 <= 31) or (
                    p1 == 192 and p2 == 168):
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
    """Record an analytical access click event."""
    device, browser = parse_user_agent(user_agent_string)
    country = get_country_from_ip(ip_address)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Normalize referrer
    if not referrer:
        referrer = "Direct"
    else:
        referrer = referrer.strip().rstrip("/")

    with get_db_conn() as conn:
        conn.execute("""
            INSERT INTO clicks (url_id, timestamp, ip_address, country, device, browser, referrer)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (url_id, timestamp, ip_address, country, device, browser, referrer))
        conn.commit()


def get_url_analytics(url_id=None):
    """
    Retrieve comprehensive analytics datasets for a single URL or globally if url_id is None.
    Returns:
        A dictionary containing total clicks, unique visitors, top country, top device,
        and raw structured data for timeline, device, country, browser, and referrer aggregates.
    """
    query_condition = "WHERE url_id = ?" if url_id is not None else ""
    params = (url_id,) if url_id is not None else ()

    with get_db_conn() as conn:
        # KPI calculations
        total_clicks = conn.execute(
            f"SELECT COUNT(*) FROM clicks {query_condition}",
            params).fetchone()[0]
        unique_ips = conn.execute(
            f"SELECT COUNT(DISTINCT ip_address) FROM clicks {query_condition}",
            params).fetchone()[0]

        top_country_row = conn.execute(f"""
            SELECT country, COUNT(*) as c FROM clicks {query_condition}
            GROUP BY country ORDER BY c DESC LIMIT 1
        """, params).fetchone()
        top_country = top_country_row["country"] if top_country_row else "N/A"

        top_device_row = conn.execute(f"""
            SELECT device, COUNT(*) as c FROM clicks {query_condition}
            GROUP BY device ORDER BY c DESC LIMIT 1
        """, params).fetchone()
        top_device = top_device_row["device"] if top_device_row else "N/A"

        # Chart datasets: Clicks by Day (last 14 days timeline)
        # Construct timeline structure in sqlite using strftime
        timeline_rows = conn.execute(f"""
            SELECT strftime('%Y-%m-%d', timestamp) as date, COUNT(*) as count
            FROM clicks {query_condition}
            GROUP BY date ORDER BY date ASC
        """, params).fetchall()
        timeline = [{"date": r["date"], "clicks": r["count"]}
                    for r in timeline_rows]

        # Device distribution
        device_rows = conn.execute(f"""
            SELECT device, COUNT(*) as count FROM clicks {query_condition}
            GROUP BY device ORDER BY count DESC
        """, params).fetchall()
        devices = [{"name": r["device"], "value": r["count"]}
                   for r in device_rows]

        # Country distribution
        country_rows = conn.execute(f"""
            SELECT country, COUNT(*) as count FROM clicks {query_condition}
            GROUP BY country ORDER BY count DESC
        """, params).fetchall()
        countries = [{"name": r["country"], "value": r["count"]}
                     for r in country_rows]

        # Browser distribution
        browser_rows = conn.execute(f"""
            SELECT browser, COUNT(*) as count FROM clicks {query_condition}
            GROUP BY browser ORDER BY count DESC
        """, params).fetchall()
        browsers = [{"name": r["browser"], "value": r["count"]}
                    for r in browser_rows]

        # Referrer distribution
        referrer_rows = conn.execute(f"""
            SELECT referrer, COUNT(*) as count FROM clicks {query_condition}
            GROUP BY referrer ORDER BY count DESC
        """, params).fetchall()
        referrers = [{"name": r["referrer"], "value": r["count"]}
                     for r in referrer_rows]

        # Recent individual clicks
        recent_clicks_rows = conn.execute(f"""
            SELECT timestamp, ip_address, country, device, browser, referrer
            FROM clicks {query_condition}
            ORDER BY id DESC LIMIT 50
        """, params).fetchall()
        recent_clicks = [dict(r) for r in recent_clicks_rows]

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
    """
    Generates high-fidelity simulated tracking data over the last 10 days for dynamic Plotly chart testing.
    """
    countries_list = [
        "United States",
        "United Kingdom",
        "Germany",
        "Canada",
        "Japan",
        "Australia",
        "France",
        "India",
        "Brazil",
        "Singapore",
        "Netherlands"]
    devices_list = ["Windows", "macOS", "iPhone", "Android", "iPad", "Linux"]
    browsers_list = ["Chrome", "Safari", "Firefox", "Edge", "Opera"]
    referrers_list = [
        "Direct",
        "https://google.com",
        "https://t.co",
        "https://linkedin.com",
        "https://github.com",
        "https://reddit.com"]

    with get_db_conn() as conn:
        for _ in range(count):
            # Generate random date offset (0 to 9 days ago) with randomized
            # times
            days_ago = random.randint(0, 9)
            hours = random.randint(0, 23)
            minutes = random.randint(0, 59)
            seconds = random.randint(0, 59)

            click_time = datetime.now() - timedelta(days=days_ago, hours=hours,
                                                    minutes=minutes, seconds=seconds)
            timestamp_str = click_time.strftime("%Y-%m-%d %H:%M:%S")

            ip = f"{
                random.randint(
                    24,
                    220)}.{
                random.randint(
                    10,
                    240)}.{
                random.randint(
                    0,
                    254)}.{
                random.randint(
                    1,
                    254)}"
            country = random.choices(
                countries_list,
                weights=[30, 15, 10, 8, 8, 7, 6, 8, 4, 2, 2],
                k=1
            )[0]
            device = random.choices(
                devices_list,
                weights=[40, 25, 18, 12, 3, 2],
                k=1
            )[0]
            browser = random.choices(
                browsers_list,
                weights=[55, 20, 12, 8, 5],
                k=1
            )[0]
            referrer = random.choices(
                referrers_list,
                weights=[40, 25, 12, 10, 8, 5],
                k=1
            )[0]

            conn.execute("""
                INSERT INTO clicks (url_id, timestamp, ip_address, country, device, browser, referrer)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (url_id, timestamp_str, ip, country, device, browser, referrer))
        conn.commit()
