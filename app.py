import os
import json
import logging
from datetime import datetime
from flask import Flask, request, jsonify
from notion_client import Client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

notion = Client(auth=os.environ.get("NOTION_TOKEN"))

LEADS_DB_ID = os.environ.get("NOTION_AFFILIATE_DB_ID")  # Leads database


@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "EMA Affiliate Webhook running", "timestamp": datetime.utcnow().isoformat()})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.form.to_dict() if request.form else request.get_json(silent=True) or {}
        logger.info(f"Received webhook data: {json.dumps(data, indent=2)}")

        fields = parse_jotform(data)
        logger.info(f"Parsed fields: {json.dumps(fields, indent=2)}")

        lead_page = create_lead(fields)
        logger.info(f"Created lead record: {lead_page['id']}")

        return jsonify({"success": True, "notion_page_id": lead_page["id"]})

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


def parse_jotform(data):
    """Extract fields using exact field names confirmed from Railway logs."""
    raw = data
    if "rawRequest" in data:
        try:
            raw = json.loads(data["rawRequest"])
        except Exception:
            raw = data

    def get(*keys):
        for k in keys:
            v = raw.get(k, "")
            if isinstance(v, list):
                v = ", ".join(str(i) for i in v if i)
            if isinstance(v, dict):
                v = v.get("full", "") or (v.get("first", "") + " " + v.get("last", "")).strip()
            if v:
                return str(v).strip()
        return ""

    return {
        "full_name": get("q1_nameOf") or "Unknown",
        "job_title": get("q3_jobTitle"),
        "email": get("q9_emailAddress"),
        "phone": get("q44_phoneNumber44"),
        "org_name": get("q11_organizationName"),
        "website": get("q17_organizationWebsite"),
        "how_connected": get("q19_howDid"),
        "role": get("q5_howWould"),
        "city": get("q14_city"),
        "state": get("q15_state"),
        "mission": get("q26_organizationMission"),
        "submission_date": datetime.utcnow().strftime("%Y-%m-%d"),
    }


def create_lead(fields):
    """Create a record in the Leads database with correct Notion property names."""
    org_name = fields.get("org_name") or fields.get("full_name") or "Unknown"
    full_name = fields.get("full_name") or ""

    contact_parts = [p for p in [full_name, fields.get("job_title"), ", ".join(filter(None, [fields.get("city"), fields.get("state")]))] if p]
    contact_display = " - ".join(contact_parts) if contact_parts else full_name

    properties = {
        "Oraganization": {  # Notion typo — must match exactly
            "title": [{"text": {"content": org_name}}]
        }
    }

    if contact_display:
        properties["Lead Contact "] = {  # Trailing space is in Notion
            "rich_text": [{"text": {"content": contact_display}}]
        }

    if fields.get("email"):
        properties["Lead Contact Email"] = {"email": fields["email"]}

    if fields.get("how_connected"):
        properties["How Connected"] = {
            "rich_text": [{"text": {"content": fields["how_connected"]}}]
        }

    properties["Initial Conversation"] = {
        "date": {"start": datetime.utcnow().strftime("%Y-%m-%d")}
    }

    body_lines = []
    if fields.get("role"):
        body_lines.append(f"Role: {fields['role']}")
    if fields.get("phone"):
        body_lines.append(f"Phone: {fields['phone']}")
    if fields.get("website"):
        body_lines.append(f"Website: {fields['website']}")
    if fields.get("mission"):
        body_lines.append(f"Mission: {fields['mission']}")

    kwargs = {"parent": {"database_id": LEADS_DB_ID}, "properties": properties}
    if body_lines:
        kwargs["children"] = [{
            "object": "block",
            "type": "paragraph",
            "paragraph": {"rich_text": [{"type": "text", "text": {"content": "\n".join(body_lines)}}]}
        }]

    return notion.pages.create(**kwargs)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
