import json
import re
from flask import Flask, render_template, request, jsonify, redirect, flash, url_for
import plotly.express as px
import plotly.utils
from config import Config
import database

from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database schemas
database.db_init()


@app.context_processor
def inject_now():
    """Inject current year dynamically into templates."""
    return {"now": datetime.now().year}


def validate_and_format_url(url):
    """
    Checks if a URL has a protocol prefix, prepending http:// if missing.
    Validates syntax, returning formatted string or None if invalid.
    """
    if not url:
        return None
    url = url.strip()
    # Add http:// if no protocol prefix is present
    if not re.match(r"^https?://", url, re.IGNORECASE):
        url = "http://" + url

    # Standard URL syntax regex validation
    url_pattern = re.compile(
        r"^https?://"  # http:// or https://
        # Domain name
        r"(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+[A-Z]{2,6}\.?|"
        r"localhost|"  # localhost
        r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"  # IPv4 address
        r"(?::\d+)?"  # Optional port number
        r"(?:/?|[/?]\S+)$", re.IGNORECASE
    )

    if re.match(url_pattern, url):
        return url
    return None


def get_client_ip():
    """Extract client's real public IP, managing proxy forward headers."""
    x_forwarded_for = request.headers.get("X-Forwarded-For")
    if x_forwarded_for:
        # Get the first IP in the list (client's real IP)
        return x_forwarded_for.split(",")[0].strip()
    return request.remote_addr


def generate_plotly_charts(analytics_data):
    """
    Generates premium interactive Plotly charts as JSON data to render inside the front-end.
    Returns:
        A dictionary containing JSON strings for four distinct charts.
    """
    charts = analytics_data["charts"]

    # Common layout styles for a consistent dark theme
    layout_theme = dict(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#e2e8f0", family="Outfit, sans-serif", size=12),
        margin=dict(l=40, r=20, t=40, b=40),
        xaxis=dict(
            gridcolor="rgba(255, 255, 255, 0.08)",
            zerolinecolor="rgba(255, 255, 255, 0.15)",
            tickfont=dict(color="#94a3b8")
        ),
        yaxis=dict(
            gridcolor="rgba(255, 255, 255, 0.08)",
            zerolinecolor="rgba(255, 255, 255, 0.15)",
            tickfont=dict(color="#94a3b8")
        )
    )

    # 1. Timeline Chart (Clicks over Time)
    timeline_data = charts["timeline"]
    if timeline_data:
        dates = [d["date"] for d in timeline_data]
        clicks = [d["clicks"] for d in timeline_data]
        fig_timeline = px.line(
            x=dates,
            y=clicks,
            title="Access Frequency (Last 14 Days)",
            labels={"x": "Date", "y": "Clicks"},
            markers=True
        )
        fig_timeline.update_traces(
            line=dict(color="#a855f7", width=3),
            marker=dict(color="#d8b4fe", size=8),
            hovertemplate="<b>Date:</b> %{x}<br><b>Clicks:</b> %{y}<extra></extra>"
        )
    else:
        fig_timeline = px.line(title="Access Frequency (No Data Yet)")

    fig_timeline.update_layout(**layout_theme)

    # 2. Devices Chart (Pie / Donut)
    device_data = charts["devices"]
    if device_data:
        names = [d["name"] for d in device_data]
        values = [d["value"] for d in device_data]
        fig_devices = px.pie(
            names=names,
            values=values,
            hole=0.4,
            title="Operating Systems / Platforms",
            color_discrete_sequence=[
                "#a855f7",
                "#ec4899",
                "#3b82f6",
                "#10b981",
                "#f59e0b",
                "#64748b"]
        )
        fig_devices.update_traces(
            textposition="inside",
            textinfo="percent+label",
            hovertemplate="<b>%{label}</b><br>Clicks: %{value}<br>Percentage: %{percent}<extra></extra>"
        )
    else:
        fig_devices = px.pie(title="Operating Systems (No Data)")

    fig_devices.update_layout(**layout_theme)
    fig_devices.update_layout(
        showlegend=False, margin=dict(
            l=20, r=20, t=40, b=20))

    # 3. Country Chart (Horizontal Bar)
    country_data = charts["countries"]
    if country_data:
        names = [d["name"] for d in country_data][:10]  # Limit to top 10
        values = [d["value"] for d in country_data][:10]
        # Reverse list to make highest count appear on top in horizontal plot
        names.reverse()
        values.reverse()
        fig_countries = px.bar(
            x=values,
            y=names,
            orientation="h",
            title="Top Geolocation Sources",
            labels={"x": "Clicks", "y": "Country"}
        )
        fig_countries.update_traces(
            marker_color="#3b82f6",
            hovertemplate="<b>%{y}</b><br>Clicks: %{x}<extra></extra>"
        )
    else:
        fig_countries = px.bar(title="Top Geolocation Sources (No Data)")

    fig_countries.update_layout(**layout_theme)

    # 4. Web Browser Distribution (Vertical Bar)
    browser_data = charts["browsers"]
    if browser_data:
        names = [d["name"] for d in browser_data][:8]
        values = [d["value"] for d in browser_data][:8]
        fig_browsers = px.bar(
            x=names,
            y=values,
            title="Top Browsers",
            labels={"x": "Browser", "y": "Clicks"}
        )
        fig_browsers.update_traces(
            marker_color="#10b981",
            hovertemplate="<b>%{x}</b><br>Clicks: %{y}<extra></extra>"
        )
    else:
        fig_browsers = px.bar(title="Top Browsers (No Data)")

    fig_browsers.update_layout(**layout_theme)

    # Convert figures to JSON using Plotly's JSON encoder
    return {
        "timeline": json.dumps(fig_timeline, cls=plotly.utils.PlotlyJSONEncoder),
        "devices": json.dumps(fig_devices, cls=plotly.utils.PlotlyJSONEncoder),
        "countries": json.dumps(fig_countries, cls=plotly.utils.PlotlyJSONEncoder),
        "browsers": json.dumps(fig_browsers, cls=plotly.utils.PlotlyJSONEncoder)
    }


@app.route("/", methods=["GET"])
def index():
    """Render landing UI with shortening form and recent history table."""
    recent_urls = database.get_recent_urls(limit=8)
    return render_template(
        "index.html", recent_urls=recent_urls, base_url=Config.BASE_URL)


@app.route("/shorten", methods=["POST"])
def shorten():
    """API endpoint to shorten a new URL."""
    try:
        data = request.get_json() or {}
        original_url = data.get("original_url")
        custom_code = data.get("custom_code", "").strip() or None

        # Validate input
        formatted_url = validate_and_format_url(original_url)
        if not formatted_url:
            return jsonify(
                {"status": "error", "message": "Please enter a valid URL."}), 400

        if custom_code:
            # Enforce clean alphanumeric formatting for custom aliases
            if not re.match(r"^[a-zA-Z0-9\-_]+$", custom_code):
                return jsonify({
                    "status": "error",
                    "message": "Custom code can only contain letters, numbers, hyphens, and underscores."
                }), 400
            if len(custom_code) < 3 or len(custom_code) > 20:
                return jsonify({
                    "status": "error",
                    "message": "Custom code must be between 3 and 20 characters."
                }), 400

        # Call database insert
        url_record = database.create_short_url(formatted_url, custom_code)
        if not url_record:
            return jsonify(
                {"status": "error", "message": "That custom code is already in use."}), 409

        return jsonify({
            "status": "success",
            "short_url": f"{Config.BASE_URL}/{url_record['short_code']}",
            "short_code": url_record["short_code"],
            "original_url": url_record["original_url"],
            "qr_code_base64": url_record["qr_code_base64"]
        })

    except Exception as e:
        return jsonify(
            {"status": "error", "message": f"Server error: {str(e)}"}), 500


@app.route("/<short_code>", methods=["GET"])
def redirect_to_url(short_code):
    """Log tracking analytics and redirect short codes to target destinations."""
    url_record = database.get_url_by_code(short_code)
    if not url_record:
        return render_template("404.html"), 404

    # Log the click metrics
    ip_address = get_client_ip()
    user_agent = request.headers.get("User-Agent", "")
    referrer = request.headers.get("Referer", "")

    # Asynchronously process tracking to avoid network bottlenecks
    database.record_click(url_record["id"], ip_address, user_agent, referrer)

    return redirect(url_record["original_url"])


@app.route("/analytics", methods=["GET"])
def global_analytics():
    """Display system-wide consolidated metrics and statistics."""
    analytics_data = database.get_url_analytics(url_id=None)
    charts_json = generate_plotly_charts(analytics_data)

    return render_template(
        "analytics.html",
        is_global=True,
        kpis=analytics_data["kpis"],
        recent_clicks=analytics_data["recent_clicks"],
        charts_json=charts_json
    )


@app.route("/analytics/<short_code>", methods=["GET"])
def url_analytics(short_code):
    """Display precise tracking dashboard metrics for a specific shortened link."""
    url_record = database.get_url_by_code(short_code)
    if not url_record:
        flash("The requested short link analytics does not exist.", "warning")
        return redirect(url_for("index"))

    analytics_data = database.get_url_analytics(url_record["id"])
    charts_json = generate_plotly_charts(analytics_data)

    return render_template(
        "analytics.html",
        is_global=False,
        url=url_record,
        base_url=Config.BASE_URL,
        kpis=analytics_data["kpis"],
        recent_clicks=analytics_data["recent_clicks"],
        charts_json=charts_json
    )


@app.route("/api/simulate", methods=["POST"])
def simulate_clicks_api():
    """Debug utility to inject realistic access history parameters for demonstration."""
    try:
        data = request.get_json() or {}
        url_id = data.get("url_id")

        # If url_id is None, simulate for the most recent link
        if url_id is None:
            recent = database.get_recent_urls(limit=1)
            if not recent:
                return jsonify(
                    {"status": "error", "message": "Create a short link first!"}), 400
            url_id = recent[0]["id"]

        database.simulate_test_clicks(url_id, count=60)
        return jsonify(
            {"status": "success", "message": "Injected 60 simulated tracking events successfully."})

    except Exception as e:
        return jsonify(
            {"status": "error", "message": f"Simulation failed: {str(e)}"}), 500


@app.errorhandler(404)
def page_not_found(e):
    """Graceful handler for unregistered resource lookups."""
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
