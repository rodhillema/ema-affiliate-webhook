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
    """Extract fields from Jotform POST data."""
    # Jotform sometimes nests data in rawRequest
    raw = data
    if "rawRequest" in data:
        try:
            raw = json.loads(data["rawRequest"])
        except Exception:
            raw = data

    def get(*keys):
        for k in keys:
            v = raw.get(k, "")
            if isinstance(v, dict):
                # Handle name fields like {"first": "Jane", "last": "Doe"}
                parts = [v.get("first", ""), v.get("last", "")]
                v = " ".join(p for p in parts if p)
            if v:
                return str(v).strip()
        return ""

    first = get("q3_name[first]", "q3_name", "firstName", "first_name")
    last = get("q3_name[last]", "lastName", "last_name")
    full_name = f"{first} {last}".strip() or get("name", "q3_name", "fullName") or "Unknown"

    return {
        "full_name": full_name,
        "email": get("q4_email", "email", "q5_email", "q4_email[0]"),
        "phone": get("q5_phone", "phone", "q6_phone"),
        "org_name": get("q6_organization", "q7_organization", "organization", "orgName", "q8_organization"),
        "how_connected": get("q7_howConnected", "howConnected", "how_connected", "q9_howConnected"),
        "message": get("q10_message", "message", "q11_message", "comments", "q8_message"),
        "submission_date": data.get("submissionDate") or data.get("submission_date") or datetime.utcnow().strftime("%Y-%m-%d"),
    }


def create_lead(fields):
    """Create a record in the Leads database with the correct Notion property names."""
    org_name = fields["org_name"] or fields["full_name"] or "Unknown"

    properties = {
        # Title field (Notion has a typo: "Oraganization")
        "Oraganization": {
            "title": [{"text": {"content": org_name}}]
        }
    }

    if fields["full_name"]:
        properties["Lead Contact "] = {  # Note the trailing space — it's in Notion
            "rich_text": [{"text": {"content": fields["full_name"]}}]
        }

    if fields["email"]:
        properties["Lead Contact Email"] = {
            "email": fields["email"]
        }

    if fields["how_connected"]:
        properties["How Connected"] = {
            "rich_text": [{"text": {"content": fields["how_connected"]}}]
        }

    # Set Initial Conversation to today's date
    today = datetime.utcnow().strftime("%Y-%m-%d")
    properties["Initial Conversation"] = {
        "date": {"start": today}
    }

    # Add message to page body if present
    children = []
    if fields["message"]:
        children = [
            {
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Message from form:\n" + fields["message"]}}
                    ]
                }
            }
        ]

    kwargs = {
        "parent": {"database_id": LEADS_DB_ID},
        "properties": properties,
    }
    if children:
        kwargs["children"] = children

    return notion.pages.create(**kwargs)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
