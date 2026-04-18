from flask import Blueprint, jsonify, render_template


frontend_bp = Blueprint(
    "frontend",
    __name__,
    template_folder="templates",
    static_folder="static",
    static_url_path="/frontend-static",
)


DASHBOARD_DATA = {
    "ctf_name": "GlacierCTF",
    "status_text": "Playing GlacierCTF now",
    "challenges": [f"chall{i}" for i in range(1, 11)],
    "models": [
        {
            "name": "gpt 5.4",
            "states": ["solved", "solved", "trying", "idle", "solved", "trying", "idle", "solved", "idle", "trying"],
        },
        {
            "name": "gpt 5.3",
            "states": ["trying", "idle", "solved", "solved", "idle", "trying", "solved", "idle", "trying", "idle"],
        },
        {
            "name": "gpt 4.1",
            "states": ["idle", "trying", "idle", "solved", "solved", "idle", "trying", "solved", "idle", "solved"],
        },
        {
            "name": "gpt 4o",
            "states": ["solved", "idle", "trying", "idle", "solved", "solved", "idle", "trying", "idle", "idle"],
        },
        {
            "name": "o4-mini",
            "states": ["idle", "solved", "idle", "trying", "idle", "solved", "trying", "idle", "solved", "trying"],
        },
    ],
}


@frontend_bp.get("/")
def index():
    return render_template("index.html")


@frontend_bp.get("/details")
def details():
    return render_template("details.html")


@frontend_bp.get("/api/dashboard")
def api_dashboard():
    return jsonify(DASHBOARD_DATA)


@frontend_bp.get("/api/details")
def api_details():
    return jsonify(
        {
            "ctf_name": DASHBOARD_DATA["ctf_name"],
            "summary": "Dummy details endpoint for the autosolver frontend.",
            "next_step": "Replace this payload with live challenge and solver metadata later.",
        }
    )
