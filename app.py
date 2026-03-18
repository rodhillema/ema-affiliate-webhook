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

LEADS_DB_ID      = os.environ.get("NOTION_AFFILIATE_DB_ID")   # Leads
CONTACTS_DB_ID   = os.environ.get("NOTION_CONTACTS_DB_ID")    # Contacts
ORGS_DB_ID       = os.environ.get("NOTION_ORGS_DB_ID")        # Organizations


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

        today = datetime.utcnow().strftime("%Y-%m-%d")

        # 1. Create Organization record
        org_page = create_organization(fields, today)
        org_page_url = org_page["url"]
        logger.info(f"Created org record: {org_page['id']}")

        # 2. Create Contact record, linked to Organization
        contact_page = create_contact(fields, org_page_url)
        contact_page_url = contact_page["url"]
        logger.info(f"Created contact record: {contact_page['id']}")

        # 3. Create Lead record
        lead_page = create_lead(fields, today)
        logger.info(f"Created lead record: {lead_page['id']}")

        return jsonify({
            "success": True,
            "org_id": org_page["id"],
            "contact_id": contact_page["id"],
            "lead_id": lead_page["id"],
        })

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

    # Build full address
    addr_parts = [get("q12_address"), get("q13_streetAddress"), get("q14_city"), get("q15_state"), get("q16_postal")]
    full_address = ", ".join(p for p in addr_parts if p)

    return {
        "full_name":    get("q1_nameOf") or "Unknown",
        "job_title":    get("q3_jobTitle"),
        "email":        get("q9_emailAddress"),
        "phone":        get("q44_phoneNumber44"),
        "org_name":     get("q11_organizationName") or "Unknown Organization",
        "website":      get("q17_organizationWebsite"),
        "how_connected": get("q19_howDid"),
        "role":         get("q5_howWould"),
        "address":      full_address,
        "city":         get("q14_city"),
        "state":        get("q15_state"),
        "mission":      get("q26_organizationMission"),
        "years_op":     get("q45_howLong45"),
        "submission_date": datetime.utcnow().strftime("%Y-%m-%d"),
    }


def create_organization(fields, today):
    """Create a record in Organizations database."""
    properties = {
        "Name": {
            "title": [{"text": {"content": fields["org_name"]}}]
        },
        "Phase": {
            "status": {"name": "Research"}
        }
    }

    if fields.get("website"):
        properties["Website"] = {"url": fields["website"]}

    if fields.get("address"):
        properties["Address"] = {
            "rich_text": [{"text": {"content": fields["address"]}}]
        }

    if fields.get("mission"):
        properties["Organizational Mission"] = {
            "rich_text": [{"text": {"content": fields["mission"]}}]
        }

    if fields.get("how_connected"):
        properties["How did you hear about ĒMA?"] = {
            "rich_text": [{"text": {"content": fields["how_connected"]}}]
        }

    if fields.get("years_op"):
        try:
            properties["Years in operation  "] = {  # Note double trailing spaces
                "number": float(fields["years_op"])
            }
        except ValueError:
            pass

    # Set Interest Call Date to today as a placeholder
    properties["Interest Call Date"] = {
        "date": {"start": today}
    }

    return notion.pages.create(
        parent={"database_id": ORGS_DB_ID},
        properties=properties
    )


def create_contact(fields, org_page_url):
    """Create a record in Contacts database, linked to the Organization."""
    properties = {
        "Name": {
            "title": [{"text": {"content": fields["full_name"]}}]
        }
    }

    if fields.get("email"):
        properties["Email"] = {"email": fields["email"]}

    if fields.get("phone"):
        properties["Phone Number"] = {"phone_number": fields["phone"]}

    if fields.get("job_title"):
        properties["Internal Org Title"] = {
            "rich_text": [{"text": {"content": fields["job_title"]}}]
        }

    # Link to the Organization we just created
    if org_page_url:
        properties["Organization"] = {
            "relation": [{"url": org_page_url}]
        }

    return notion.pages.create(
        parent={"database_id": CONTACTS_DB_ID},
        properties=properties
    )


def create_lead(fields, today):
    """Create a record in Leads database."""
    contact_parts = [p for p in [fields.get("full_name"), fields.get("job_title"),
                     ", ".join(filter(None, [fields.get("city"), fields.get("state")]))] if p]
    contact_display = " - ".join(contact_parts) if contact_parts else fields.get("full_name", "")

    properties = {
        "Oraganization": {  # Notion typo — must match exactly
            "title": [{"text": {"content": fields["org_name"]}}]
        },
        "Initial Conversation": {
            "date": {"start": today}
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

    return notion.pages.create(
        parent={"database_id": LEADS_DB_ID},
        properties=properties
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
