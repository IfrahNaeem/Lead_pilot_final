"""
LeadPilot AI - Streamlit Frontend
==================================
Talks to the FastAPI backend to let a (non-technical) user:
  1. Upload portfolio files (pdf/docx/txt) -> ingested into RAG
  2. Upload a leads CSV -> creates lead records
  3. View a dashboard of leads with fit scores
  4. Drill into a lead, trigger analysis, review AI drafts, and approve/edit/reject

Run locally:   streamlit run app.py
Run in Docker: see Dockerfile (port 8501)

Config:
  BACKEND_URL - base URL of the FastAPI backend (default http://localhost:8000)
"""

import os
import io
import requests
import streamlit as st
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()  # allows a local .env file with BACKEND_URL=... during dev

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
REQUEST_TIMEOUT = 30  # seconds, generous because AI agent calls can be slow

st.set_page_config(page_title="LeadPilot AI", page_icon="🧭", layout="wide")

# ---------------------------------------------------------------------------
# Session state defaults
# ---------------------------------------------------------------------------
if "selected_lead_id" not in st.session_state:
    st.session_state.selected_lead_id = None
if "page" not in st.session_state:
    st.session_state.page = "Upload Portfolio"


# ---------------------------------------------------------------------------
# Small API helper layer
# All backend calls live here so the page functions stay simple, and so we
# have ONE place that handles connection errors / bad status codes.
# ---------------------------------------------------------------------------
class ApiError(Exception):
    """Raised when the backend call fails or returns a non-2xx response."""
    pass


def _handle_response(resp: requests.Response):
    if not resp.ok:
        try:
            detail = resp.json().get("detail", resp.text)
        except Exception:
            detail = resp.text
        raise ApiError(f"Backend returned {resp.status_code}: {detail}")
    if resp.content:
        return resp.json()
    return None


def api_get(path: str, params: dict | None = None):
    try:
        resp = requests.get(f"{BACKEND_URL}{path}", params=params, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise ApiError(f"Could not reach backend at {BACKEND_URL}. Is it running? ({e})")
    return _handle_response(resp)


def api_post_json(path: str, payload: dict):
    try:
        resp = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise ApiError(f"Could not reach backend at {BACKEND_URL}. Is it running? ({e})")
    return _handle_response(resp)


def api_post_files(path: str, files: list[tuple[str, tuple[str, bytes, str]]]):
    try:
        resp = requests.post(f"{BACKEND_URL}{path}", files=files, timeout=REQUEST_TIMEOUT)
    except requests.exceptions.RequestException as e:
        raise ApiError(f"Could not reach backend at {BACKEND_URL}. Is it running? ({e})")
    return _handle_response(resp)


# ---------------------------------------------------------------------------
# Page: Upload Portfolio
# ---------------------------------------------------------------------------
def page_upload_portfolio():
    st.title("📁 Upload Portfolio")
    st.caption(
        "Upload your CV, case studies, or project write-ups. These get chunked and "
        "embedded so the AI agents can quote real evidence when scoring leads and "
        "drafting outreach."
    )

    uploaded_files = st.file_uploader(
        "Choose portfolio files (PDF, DOCX, or TXT)",
        type=["pdf", "docx", "txt"],
        accept_multiple_files=True,
        help="You can select multiple files at once (hold Ctrl/Cmd while clicking).",
    )

    if st.button("Upload & Ingest", type="primary", disabled=not uploaded_files):
        with st.spinner("Uploading and processing your portfolio..."):
            try:
                files_payload = [
                    ("files", (f.name, f.getvalue(), f.type or "application/octet-stream"))
                    for f in uploaded_files
                ]
                result = api_post_files("/portfolio/upload", files_payload)
                count = (result or {}).get("ingested_count", len(uploaded_files))
                st.success(f"✅ Success! {count} portfolio item(s) were ingested.")
            except ApiError as e:
                st.error(f"⚠️ Upload failed: {e}")


# ---------------------------------------------------------------------------
# Page: Upload Leads
# ---------------------------------------------------------------------------
def page_upload_leads():
    st.title("📇 Upload Leads")
    st.caption("Upload a CSV of companies you'd like LeadPilot to research and score.")

    with st.expander("ℹ️ Expected CSV format (click to see example)"):
        st.write("Your CSV must contain these columns:")
        st.code("company_name,website,industry", language="text")
        st.dataframe(
            {
                "company_name": ["Acme Corp", "Globex Inc"],
                "website": ["https://acme.com", "https://globex.com"],
                "industry": ["E-commerce", "Manufacturing"],
            },
            use_container_width=True,
        )

    uploaded_csv = st.file_uploader("Choose a leads CSV file", type=["csv"])

    if st.button("Upload Leads", type="primary", disabled=uploaded_csv is None):
        with st.spinner("Uploading leads..."):
            try:
                files_payload = [("file", (uploaded_csv.name, uploaded_csv.getvalue(), "text/csv"))]
                result = api_post_files("/leads/upload", files_payload)
                lead_ids = (result or {}).get("lead_ids", [])
                st.success(f"✅ Uploaded {len(lead_ids)} lead(s).")
                if lead_ids:
                    st.write("New lead IDs:", lead_ids)
            except ApiError as e:
                st.error(
                    "⚠️ Upload failed: "
                    f"{e}\n\nDouble-check your CSV has the columns "
                    "`company_name, website, industry`."
                )


# ---------------------------------------------------------------------------
# Page: Lead Dashboard
# ---------------------------------------------------------------------------
FIT_SCORE_COLORS = {
    "High": "🟢 High",
    "Medium": "🟡 Medium",
    "Low": "🔴 Low",
}


def page_lead_dashboard():
    st.title("📊 Lead Dashboard")
    st.caption("All leads uploaded so far. Click 'View Details' to review and approve outreach.")

    if st.button("🔄 Refresh"):
        st.rerun()

    with st.spinner("Loading leads..."):
        try:
            leads = api_get("/leads") or []
        except ApiError as e:
            st.error(f"⚠️ Could not load leads: {e}")
            return

    if not leads:
        st.info("No leads yet. Go to **Upload Leads** to add some.")
        return

    # Header row
    header_cols = st.columns([3, 2, 2, 2, 2])
    for col, label in zip(header_cols, ["Company", "Industry", "Fit Score", "Status", ""]):
        col.markdown(f"**{label}**")

    for lead in leads:
        cols = st.columns([3, 2, 2, 2, 2])
        cols[0].write(lead.get("company_name", "—"))
        cols[1].write(lead.get("industry", "—"))
        fit_score = lead.get("fit_score")
        cols[2].write(FIT_SCORE_COLORS.get(fit_score, "⚪ Not scored"))
        cols[3].write(lead.get("status", "pending"))
        if cols[4].button("View Details", key=f"view_{lead['id']}"):
            st.session_state.selected_lead_id = lead["id"]
            st.session_state.page = "Lead Detail & Approval"
            st.rerun()


# ---------------------------------------------------------------------------
# Page: Lead Detail & Approval
# ---------------------------------------------------------------------------
def page_lead_detail():
    st.title("🔍 Lead Detail & Approval")

    lead_id = st.session_state.selected_lead_id
    if lead_id is None:
        st.info("No lead selected. Go to **Lead Dashboard** and click 'View Details' on a lead.")
        return

    with st.spinner("Loading lead details..."):
        try:
            lead = api_get(f"/leads/{lead_id}")
        except ApiError as e:
            st.error(f"⚠️ Could not load lead: {e}")
            return

    if lead is None:
        st.warning("Lead not found.")
        return

    st.subheader(lead.get("company_name", "Unknown company"))
    st.caption(f"Industry: {lead.get('industry', '—')}  |  Status: {lead.get('status', 'pending')}")

    analyzed = bool(lead.get("research") or lead.get("fit_score"))

    if not analyzed:
        st.warning("This lead hasn't been analyzed yet.")
        if st.button("🤖 Analyze this lead", type="primary"):
            with st.spinner("Running research, fit scoring, and outreach drafting... this can take a moment."):
                try:
                    api_post_json(f"/leads/{lead_id}/analyze", {})
                    st.success("Analysis complete!")
                    st.rerun()
                except ApiError as e:
                    st.error(f"⚠️ Analysis failed: {e}")
        return

    # --- Company summary ---
    st.markdown("### 🏢 Company Summary")
    st.write(lead.get("company_summary", "No summary available."))

    # --- Fit score & explanation ---
    st.markdown("### 🎯 Fit Score")
    fit_score = lead.get("fit_score", "Unknown")
    st.markdown(f"**{FIT_SCORE_COLORS.get(fit_score, fit_score)}**")
    st.write(lead.get("fit_explanation", "No explanation available."))

    matching_skills = lead.get("matching_skills") or []
    if matching_skills:
        st.write("**Matching skills:** " + ", ".join(matching_skills))

    # --- Portfolio evidence ---
    st.markdown("### 📎 Portfolio Evidence")
    evidence = lead.get("portfolio_evidence") or []
    if evidence:
        for item in evidence:
            st.markdown(f"- {item}")
    else:
        st.caption("No portfolio evidence returned.")

    # --- Drafts ---
    st.markdown("### ✉️ Outreach Drafts")
    email_draft = st.text_area(
        "Email draft", value=lead.get("email_draft", ""), height=200,
        help="Feel free to edit before approving.",
    )
    linkedin_draft = st.text_area(
        "LinkedIn message draft", value=lead.get("linkedin_draft", ""), height=120,
        help="Feel free to edit before approving.",
    )

    # --- Approval controls ---
    st.markdown("### ✅ Approval")
    decision = st.radio(
        "Decision", options=["Approve", "Edit", "Reject"], horizontal=True,
        help="Approve = send as-is. Edit = send your edited version above. Reject = discard.",
    )
    notes = st.text_area("Notes (optional)", placeholder="Any context for the team...")

    if st.button("Submit Decision", type="primary"):
        with st.spinner("Saving your decision..."):
            try:
                api_post_json(
                    "/approvals",
                    {
                        "lead_id": lead_id,
                        "decision": decision.lower(),
                        "email_draft": email_draft,
                        "linkedin_draft": linkedin_draft,
                        "notes": notes,
                    },
                )
                st.success(f"✅ Decision '{decision}' saved for {lead.get('company_name')}.")
            except ApiError as e:
                st.error(f"⚠️ Could not save decision: {e}")


# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
def main():
    st.sidebar.title("🧭 LeadPilot AI")
    st.sidebar.caption(f"Backend: {BACKEND_URL}")

    pages = {
        "Upload Portfolio": page_upload_portfolio,
        "Upload Leads": page_upload_leads,
        "Lead Dashboard": page_lead_dashboard,
        "Lead Detail & Approval": page_lead_detail,
    }

    choice = st.sidebar.radio(
        "Navigate",
        list(pages.keys()),
        index=list(pages.keys()).index(st.session_state.page),
    )
    st.session_state.page = choice

    pages[choice]()


if __name__ == "__main__":
    main()
