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

LEADS_DB_ID    = os.environ.get("NOTION_AFFILIATE_DB_ID")
CONTACTS_DB_ID = os.environ.get("NOTION_CONTACTS_DB_ID")
ORGS_DB_ID     = os.environ.get("NOTION_ORGS_DB_ID")


@app.route("/", methods=["GET"])
def index():
    return jsonify({"status": "EMA Affiliate Webhook running", "timestamp": datetime.utcnow().isoformat()})


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/debug/orgs-schema", methods=["GET"])
def debug_orgs_schema():
    try:
        db = notion.databases.retrieve(database_id=ORGS_DB_ID)
        props = {k: v["type"] for k, v in db["properties"].items()}
        return jsonify(props)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/debug/orgs-raw", methods=["GET"])
def debug_orgs_raw():
    try:
        db = notion.databases.retrieve(database_id=ORGS_DB_ID)
        result = {}
        for k in db["properties"].keys():
            result[repr(k)] = list(k.encode("utf-8"))
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.form.to_dict() if request.form else request.get_json(silent=True) or {}
        logger.info(f"Received webhook data: {json.dumps(data, indent=2)}")

        fields = parse_jotform(data)
        logger.info(f"Parsed fields: {json.dumps(fields, indent=2)}")

        today = datetime.utcnow().strftime("%Y-%m-%d")
        results = {}
        org_id = None

        # 1. Create Organization
        try:
            org_page = create_organization(fields, today)
            org_id = org_page["id"]
            results["org_id"] = org_id
            logger.info(f"Created org: {org_id}")
        except Exception as e:
            logger.error(f"Org creation failed: {e}")

        # 2. Create Contact (linked to org if available)
        try:
            contact_page = create_contact(fields, org_id)
            results["contact_id"] = contact_page["id"]
            logger.info(f"Created contact: {contact_page['id']}")
        except Exception as e:
            logger.error(f"Contact creation failed: {e}")

        # 3. Create Lead
        try:
            lead_page = create_lead(fields, today)
            results["lead_id"] = lead_page["id"]
            logger.info(f"Created lead: {lead_page['id']}")
        except Exception as e:
            logger.error(f"Lead creation failed: {e}")

        return jsonify({"success": True, **results})

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500


def parse_jotform(data):
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

    addr_parts = [get("q12_address"), get("q13_streetAddress"), get("q14_city"), get("q15_state"), get("q16_postal")]
    full_address = ", ".join(p for p in addr_parts if p)

    return {
        "full_name":     get("q1_nameOf") or "Unknown",
        "job_title":     get("q3_jobTitle"),
        "email":         get("q9_emailAddress"),
        "phone":         get("q44_phoneNumber44"),
        "org_name":      get("q11_organizationName") or "Unknown Organization",
        "website":       get("q17_organizationWebsite"),
        "how_connected": get("q19_howDid"),
        "role":          get("q5_howWould"),
        "address":       full_address,
        "city":          get("q14_city"),
        "state":         get("q15_state"),
        "mission":       get("q26_organizationMission"),
        "years_in_op":   get("q45_howLong45"),
        "vision":        get("q27_organizationVision"),
        "core_values":   get("q28_organizationCore"),
        "core_programs": get("q29_brieflyDescribe"),
        "clients":       get("q30_brieflyDescribe30"),
        "referrals":     get("q31_howDo"),
        "volunteers":    get("q32_brieflyDescribe32"),
        "ema_interest":  get("q33_whatInterests"),
        "ema_gap":       get("q43_whatNeed43"),
        "foster_crisis": get("q34_howDoes"),
        "church_role":   get("q35_whatRole"),
        "faith_comfort": get("q36_isYour"),
    }


def _make_block(heading, value):
    return [
        {
            "object": "block",
            "type": "heading_3",
            "heading_3": {
                "rich_text": [{"type": "text", "text": {"content": heading}}]
            }
        },
        {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [{"type": "text", "text": {"content": value}}]
            }
        }
    ]


def create_organization(fields, today):
    properties = {
        "Name": {"title": [{"text": {"content": fields["org_name"]}}]},
    }
    if fields.get("website"):
        properties["Website"] = {
            "rich_text": [{"text": {"content": fields["website"]}}]
        }
    if fields.get("address"):
        properties["Address"] = {
            "rich_text": [{"text": {"content": fields["address"]}}]
        }
    if fields.get("mission"):
        properties["Organizational Mission"] = {
            "rich_text": [{"text": {"content": fields["mission"]}}]
        }
    if fields.get("years_in_op"):
        try:
            properties["Years in operation\xa0 "] = {"number": float(fields["years_in_op"])}
        except ValueError:
            pass
    if fields.get("how_connected"):
        properties["How did you hear about ĒMA?"] = {
            "rich_text": [{"text": {"content": fields["how_connected"]}}]
        }

    page = notion.pages.create(parent={"database_id": ORGS_DB_ID}, properties=properties)

    qa_fields = [
        ("Organization vision statement",                                    fields.get("vision")),
        ("Organization Core Values",                                         fields.get("core_values")),
        ("Briefly describe your core programs of service",                   fields.get("core_programs")),
        ("Briefly describe the majority of clients you serve",               fields.get("clients")),
        ("How do clients hear about your program / main referral partners",  fields.get("referrals")),
        ("Briefly describe your current volunteer opportunities",             fields.get("volunteers")),
        ("What interests you about the ĒMA program and model",          fields.get("ema_interest")),
        ("What need or gap could the ĒMA program solve",                fields.get("ema_gap")),
        ("How does your organization understand the foster care crisis",      fields.get("foster_crisis")),
        ("What role do you see the church playing in supporting families",    fields.get("church_role")),
        ("Is your organization comfortable working with communities of faith",fields.get("faith_comfort")),
    ]

    blocks = []
    for heading, value in qa_fields:
        if value:
            blocks.extend(_make_block(heading, value))

    if blocks:
        notion.blocks.children.append(block_id=page["id"], children=blocks)

    return page


def create_contact(fields, org_id=None):
    properties = {
        "Name": {"title": [{"text": {"content": fields["full_name"]}}]},
    }
    if fields.get("email"):
        properties["Email"] = {"email": fields["email"]}
    if fields.get("phone"):
        properties["Phone Number"] = {"phone_number": fields["phone"]}
    if fields.get("job_title"):
        properties["Internal Org Title"] = {
            "rich_text": [{"text": {"content": fields["job_title"]}}]
        }
    if org_id:
        properties["Organization"] = {"relation": [{"id": org_id}]}
    if fields.get("address"):
        properties["Shipping Address"] = {
            "rich_text": [{"text": {"content": fields["address"]}}]
        }

    return notion.pages.create(parent={"database_id": CONTACTS_DB_ID}, properties=properties)


def create_lead(fields, today):
    contact_parts = [p for p in [
        fields.get("full_name"),
        fields.get("job_title"),
        ", ".join(filter(None, [fields.get("city"), fields.get("state")]))
    ] if p]
    contact_display = " - ".join(contact_parts)

    properties = {
        "Oraganization": {"title": [{"text": {"content": fields["org_name"]}}]},
        "Initial Conversation": {"date": {"start": today}},
    }
    if contact_display:
        properties["Lead Contact "] = {
            "rich_text": [{"text": {"content": contact_display}}]
        }
    if fields.get("email"):
        properties["Lead Contact Email"] = {"email": fields["email"]}
    if fields.get("how_connected"):
        properties["How Connected"] = {
            "rich_text": [{"text": {"content": fields["how_connected"]}}]
        }

    return notion.pages.create(parent={"database_id": LEADS_DB_ID}, properties=properties)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
