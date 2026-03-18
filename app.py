"""
EMA Affiliate Interest Form - Jotform to Notion Webhook
Property names verified directly from live Notion databases via MCP.

Data source IDs (use these, NOT the database page IDs):
  Organizations:      1cbecd67-4a69-81ae-bfcf-000b71cb2246
  Contacts:           1cbecd67-4a69-81a0-a9d0-000b4656c90b
  Affiliate Meetings: aa6fdab3-b950-4d84-8983-e2673943833e
"""

import os
import logging
from datetime import date
from flask import Flask, request, jsonify
from notion_client import Client
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Notion client
notion = Client(auth=os.environ["NOTION_TOKEN"])

# Data Source IDs - verified from live schema
ORG_DS     = os.environ.get("NOTION_ORG_DS",     "1cbecd67-4a69-81ae-bfcf-000b71cb2246")
CONTACT_DS = os.environ.get("NOTION_CONTACT_DS",  "1cbecd67-4a69-81a0-a9d0-000b4656c90b")
MEETING_DS = os.environ.get("NOTION_MEETING_DS",  "aa6fdab3-b950-4d84-8983-e2673943833e")


# ==============================================================================
# PROPERTY HELPERS
# ==============================================================================

def text_prop(value):
    return {"rich_text": [{"text": {"content": str(value or "")[:2000]}}]}

def title_prop(value):
    return {"title": [{"text": {"content": str(value or "")}}]}

def email_prop(value):
    v = str(value or "").strip()
    return {"email": v if v else None}

def phone_prop(value):
    v = str(value or "").strip()
    return {"phone_number": v if v else None}

def number_prop(value):
    try:
        return {"number": float(str(value).strip())}
    except (ValueError, TypeError):
        return {"number": None}

def select_prop(value):
    v = str(value or "").strip()
    return {"select": {"name": v} if v else None}

def relation_prop(page_id):
    return {"relation": [{"id": page_id}]} if page_id else {"relation": []}

def today_iso():
    return date.today().isoformat()


# ==============================================================================
# PARSE JOTFORM SUBMISSION
# ==============================================================================

def parse_form(data):
    """
    Maps Jotform q{id}_{name} tokens to readable field names.
    Use the /debug endpoint with a real submission to verify exact token names.
    """
    def g(*keys):
        for k in keys:
            v = data.get(k, "")
            if v:
                return v
        return ""

    # Address sub-fields
    addr   = g("q9_address[addr_line1]", "q9_address")
    city   = g("q9_address[city]")
    state  = g("q9_address[state]")
    postal = g("q9_address[postal]")
    address = ", ".join(p for p in [addr, city, state, postal] if p)

    return {
        "name":             g("q1_nameOf", "q1_fullName", "q1_name"),
        "job_title":        g("q2_jobTitle", "q2_jobTitle2"),
        "years_in_role":    g("q3_howMany", "q3_yearsIn"),
        "role_description": g("q4_howWould", "q4_roleDescription"),
        "email":            g("q5_emailAddress", "q5_email"),
        "phone":            g("q6_phoneNumber", "q6_phone"),
        "org_name":         g("q7_organizationName", "q7_orgName"),
        "years_in_op":      g("q8_howLong", "q8_yearsOperation"),
        "address":          address,
        "website":          g("q14_organizationWebsite", "q14_website"),
        "mission":          g("q16_organizationMission", "q16_mission"),
        "heard_about":      g("q15_howDid", "q15_howDidYou"),
        "vision":           g("q17_organizationVision", "q17_vision"),
        "core_values":      g("q18_organizationCore", "q18_coreValues"),
        "core_programs":    g("q19_brieflyDescribe", "q19_corePrograms"),
        "clients":          g("q20_brieflyDescribe20", "q20_clients"),
        "referrals":        g("q21_howDo", "q21_referrals"),
        "volunteers":       g("q22_brieflyDescribe22", "q22_volunteers"),
        "interest_ema":     g("q23_whatInterests", "q23_interest"),
        "gap_ema":          g("q24_whatNeed", "q24_gap"),
        "foster_care":      g("q25_howDoes", "q25_fosterCare"),
        "church_role":      g("q26_whatRole", "q26_church"),
        "faith_comfortable":g("q27_isYour", "q27_faith"),
        "investment_ack":   g("q28_iUnderstand", "q28_investment"),
    }


# ==============================================================================
# STEP 1 - FIND OR CREATE ORGANIZATION
#
# Verified Notion properties (Organizations DB):
#   Name                        -> title
#   Website                     -> text  (NOT url type)
#   Address                     -> text
#   "Years in operation  "      -> number (has two trailing spaces - exact DB name)
#   "How did you hear about EMA?"-> text
#   Organizational Mission      -> text
# ==============================================================================

def find_org(org_name, website):
    if org_name:
        res = notion.databases.query(
            database_id=ORG_DS,
            filter={"property": "Name", "title": {"equals": org_name}}
        ).get("results", [])
        if res:
            return res[0]["id"], "found"

    if website:
        clean = str(website).strip().rstrip("/")
        res = notion.databases.query(
            database_id=ORG_DS,
            filter={"property": "Website", "rich_text": {"equals": clean}}
        ).get("results", [])
        if res:
            return res[0]["id"], "found"

    return None, "not_found"


def upsert_org(form):
    org_id, status = find_org(form["org_name"], form["website"])

    props = {
        "Name":                          title_prop(form["org_name"]),
        "Website":                       text_prop(form["website"]),
        "Address":                       text_prop(form["address"]),
        "Years in operation  ":          number_prop(form["years_in_op"]),
        "How did you hear about \u0112MA?": text_prop(form["heard_about"]),
        "Organizational Mission":        text_prop(form["mission"]),
    }

    if status == "found":
        logger.info(f"Updating org: {org_id}")
        notion.pages.update(page_id=org_id, properties=props)
        return org_id
    else:
        logger.info(f"Creating org: {form['org_name']}")
        page = notion.pages.create(
            parent={"database_id": ORG_DS},
            properties=props
        )
        return page["id"]


# ==============================================================================
# STEP 2 - FIND OR CREATE CONTACT
#
# Verified Notion properties (Contacts DB):
#   Name                -> title
#   Email               -> email   (NOT "Email Address")
#   Phone Number        -> phone_number
#   Internal Org Title  -> text    (closest field for job title)
#   Short Bio           -> text    (used for role description)
#   Organization        -> relation -> Organizations
#
# NOTE: No "Years in Role" or "Role Description" fields exist.
#       Those answers are captured in the Meeting page body only.
# ==============================================================================

def find_contact(email):
    if not email:
        return None, "not_found"
    res = notion.databases.query(
        database_id=CONTACT_DS,
        filter={"property": "Email", "email": {"equals": email.strip()}}
    ).get("results", [])
    if res:
        return res[0]["id"], "found"
    return None, "not_found"


def upsert_contact(form, org_page_id):
    contact_id, status = find_contact(form["email"])

    props = {
        "Name":               title_prop(form["name"]),
        "Email":              email_prop(form["email"]),
        "Phone Number":       phone_prop(form["phone"]),
        "Internal Org Title": text_prop(form["job_title"]),
        "Short Bio":          text_prop(form["role_description"]),
        "Organization":       relation_prop(org_page_id),
    }

    if status == "found":
        logger.info(f"Updating contact: {contact_id}")
        notion.pages.update(page_id=contact_id, properties=props)
        return contact_id
    else:
        logger.info(f"Creating contact: {form['name']}")
        page = notion.pages.create(
            parent={"database_id": CONTACT_DS},
            properties=props
        )
        return page["id"]


# ==============================================================================
# STEP 3 - CREATE MEETING PAGE
#
# Verified Notion properties (Affiliate Meetings DB):
#   Meeting Name        -> title   (NOT "Name")
#   Organization        -> relation -> Organizations
#   External Attendees  -> relation -> Contacts  (NOT "Contact")
#   Phase               -> select  (options: "Phase 0 // Discovery", etc.)
#   Creation Date       -> date
# ==============================================================================

def build_meeting_body(form):
    """Returns all Q&A as Notion paragraph blocks."""
    def block(label, value):
        text = f"{label}: {value or 'Not provided'}"
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "rich_text": [
                    {"type": "text", "text": {"content": label + ": "}, "annotations": {"bold": True}},
                    {"type": "text", "text": {"content": value or "Not provided"}}
                ]
            }
        }

    def heading(text):
        return {
            "object": "block",
            "type": "heading_2",
            "heading_2": {"rich_text": [{"type": "text", "text": {"content": text}}]}
        }

    def divider():
        return {"object": "block", "type": "divider", "divider": {}}

    return [
        heading("Contact Information"),
        block("Years in current role",   form["years_in_role"]),
        block("Role within organization",form["role_description"]),
        divider(),

        heading("Organization Profile"),
        block("Mission statement",       form["mission"]),
        block("Vision statement",        form["vision"]),
        block("Core values",             form["core_values"]),
        block("Core programs of service",form["core_programs"]),
        block("Clients served",          form["clients"]),
        block("Referral partners",       form["referrals"]),
        block("Volunteer opportunities", form["volunteers"]),
        block("Years in operation",      form["years_in_op"]),
        divider(),

        heading("EMA Alignment Questions"),
        block("Interest in EMA program",          form["interest_ema"]),
        block("Gap EMA could solve",              form["gap_ema"]),
        block("Understanding of foster care crisis", form["foster_care"]),
        block("Role of the church",               form["church_role"]),
        block("Comfortable with faith communities",form["faith_comfortable"]),
        block("Investment acknowledgment",         form["investment_ack"]),
    ]


def create_meeting(form, org_page_id, contact_page_id):
    meeting_name = f"{form['org_name']} - Interest Form"

    props = {
        "Meeting Name":       title_prop(meeting_name),
        "Organization":       relation_prop(org_page_id),
        "External Attendees": relation_prop(contact_page_id),
        "Phase":              select_prop("Phase 0 // Discovery"),
        "date:Creation Date:start":       today_iso(),
        "date:Creation Date:is_datetime": 0,
    }

    logger.info(f"Creating meeting: {meeting_name}")
    page = notion.pages.create(
        parent={"database_id": MEETING_DS},
        properties=props,
        children=build_meeting_body(form)
    )
    return page["id"]


# ==============================================================================
# ROUTES
# ==============================================================================

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "service": "EMA Affiliate Webhook"}), 200


@app.route("/debug", methods=["POST"])
def debug():
    """Point Jotform here temporarily to see exact raw field names."""
    data = request.form.to_dict()
    logger.info("DEBUG fields:\n" + "\n".join(f"  {k} = {v}" for k, v in sorted(data.items())))
    return jsonify({"fields": data}), 200


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        data = request.form.to_dict()
        if not data:
            data = request.get_json(silent=True) or {}

        logger.info(f"Submission for: {data.get('q7_organizationName', '(unknown)')}")

        form = parse_form(data)

        if not form["org_name"]:
            return jsonify({"error": "Missing organization name"}), 400
        if not form["email"]:
            return jsonify({"error": "Missing email address"}), 400

        org_page_id     = upsert_org(form)
        contact_page_id = upsert_contact(form, org_page_id)
        meeting_page_id = create_meeting(form, org_page_id, contact_page_id)

        result = {
            "status":           "success",
            "org_page_id":      org_page_id,
            "contact_page_id":  contact_page_id,
            "meeting_page_id":  meeting_page_id,
        }
        logger.info(f"Success: {result}")
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Webhook error: {e}", exc_info=True)
        return jsonify({"error": str(e)}), 500


# ==============================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
