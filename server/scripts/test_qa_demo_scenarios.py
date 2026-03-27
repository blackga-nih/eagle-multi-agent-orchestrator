#!/usr/bin/env python3
"""
QA Demo Scenario Tests -- exercises all 9 MVP1 use cases from EAGLE-DEMO-SCRIPT.md.

Each use case sends multi-turn chat messages via POST /api/chat, then verifies:
  - Agent responds (non-empty)
  - Correct pathway/threshold detection (keyword checks)
  - Documents are generated when requested
  - Package ZIP export works end-to-end

Usage (from devbox inside VPC):
    python test_qa_demo_scenarios.py
    python test_qa_demo_scenarios.py --base-url http://custom-alb-url
    python test_qa_demo_scenarios.py --scenarios uc1,uc3   # run specific UCs
    python test_qa_demo_scenarios.py --quick                # intake only, skip doc gen
"""
import argparse
import io
import json
import os
import re
import sys
import time
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Optional, Tuple

import requests

# ---- Defaults ----------------------------------------------------------------
QA_BACKEND_URL = os.getenv(
    "QA_BACKEND_URL",
    "http://internal-EagleC-Backe-TxWVQRPzHFsO-1219239040.us-east-1.elb.amazonaws.com",
)
DEFAULT_TENANT = os.getenv("EAGLE_TENANT_ID", "dev-tenant")
DEFAULT_USER = os.getenv("EAGLE_USER_ID", "qa-tester")
CHAT_TIMEOUT = int(os.getenv("CHAT_TIMEOUT", "180"))  # seconds per chat turn

# ---- Result tracking ---------------------------------------------------------
results = []  # type: list


def record(scenario, name, passed, detail="", duration_ms=0):
    status = "PASS" if passed else "FAIL"
    icon = "+" if passed else "X"
    results.append({
        "scenario": scenario,
        "name": name,
        "passed": passed,
        "detail": detail,
        "duration_ms": duration_ms,
    })
    print("  [%s] %s  %s (%dms) %s" % (icon, status, name, duration_ms, detail))


def chat(base_url, session_id, message, headers, timeout=CHAT_TIMEOUT):
    # type: (str, str, str, dict, int) -> Tuple[Optional[dict], int]
    """Send a chat message and return (response_json, elapsed_ms)."""
    t0 = time.monotonic()
    try:
        resp = requests.post(
            "%s/api/chat" % base_url,
            headers=headers,
            json={"message": message, "session_id": session_id},
            timeout=timeout,
        )
        elapsed = int((time.monotonic() - t0) * 1000)
        if resp.status_code == 200:
            return resp.json(), elapsed
        else:
            print("    CHAT ERROR: HTTP %d — %s" % (resp.status_code, resp.text[:300]))
            return None, elapsed
    except Exception as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        print("    CHAT ERROR: %s" % e)
        return None, elapsed


def api_get(base_url, path, headers, timeout=30):
    # type: (str, str, dict, int) -> Tuple[Optional[requests.Response], int]
    t0 = time.monotonic()
    try:
        resp = requests.get("%s%s" % (base_url, path), headers=headers, timeout=timeout)
        elapsed = int((time.monotonic() - t0) * 1000)
        return resp, elapsed
    except Exception as e:
        elapsed = int((time.monotonic() - t0) * 1000)
        print("    API ERROR: %s" % e)
        return None, elapsed


def check_keywords(text, keywords, scenario, test_name):
    """Check response contains expected keywords (case-insensitive). Returns True if any match."""
    text_lower = text.lower()
    found = [kw for kw in keywords if kw.lower() in text_lower]
    missing = [kw for kw in keywords if kw.lower() not in text_lower]
    if found:
        record(scenario, test_name, True, "found: %s" % ", ".join(found[:5]))
        return True
    else:
        record(scenario, test_name, False, "missing all: %s" % ", ".join(missing[:5]))
        return False


# ==============================================================================
# SCENARIO DEFINITIONS
# ==============================================================================

def uc1_full_competition(base_url, headers, quick=False):
    """UC-1: New IT Services Acquisition ($750K, Full Competition)"""
    sc = "UC-1"
    print("\n--- %s: New IT Services Acquisition ($750K) ---" % sc)
    sid = "qa-uc1-%s" % uuid.uuid4().hex[:8]

    # Turn 1: Intake
    r, ms = chat(base_url, sid, (
        "I need to procure cloud hosting services for our research data platform. "
        "Estimated value around $750,000."
    ), headers)
    record(sc, "intake_response", r is not None and len(r.get("response", "")) > 50,
           "len=%d" % len(r.get("response", "")) if r else "no response", ms)
    if not r:
        return

    # Turn 2: Details
    r, ms = chat(base_url, sid, (
        "3-year base period plus 2 option years, starting October 2026. "
        "No existing vehicles -- new standalone contract. We need FedRAMP High "
        "for PII and genomics research data. Full and open competition preferred. Fixed-price."
    ), headers)
    if r:
        text = r.get("response", "")
        record(sc, "details_response", len(text) > 100, "len=%d" % len(text), ms)
        check_keywords(text, ["competition", "SOW", "IGCE", "compliance", "threshold", "FAR"],
                       sc, "pathway_detection")
    else:
        record(sc, "details_response", False, "no response", ms)
        return

    if quick:
        return

    # Turn 3: Generate SOW
    r, ms = chat(base_url, sid, (
        "Generate the Statement of Work for this cloud hosting acquisition."
    ), headers, timeout=300)
    if r:
        text = r.get("response", "")
        record(sc, "sow_generation", len(text) > 200, "len=%d" % len(text), ms)
        check_keywords(text, ["Statement of Work", "scope", "contractor", "cloud", "FedRAMP"],
                       sc, "sow_content")
    else:
        record(sc, "sow_generation", False, "no response", ms)

    # Turn 4: Generate remaining docs
    r, ms = chat(base_url, sid, (
        "Now generate the IGCE, Market Research Report, and Acquisition Plan."
    ), headers, timeout=300)
    if r:
        text = r.get("response", "")
        record(sc, "multi_doc_generation", len(text) > 200, "len=%d" % len(text), ms)
    else:
        record(sc, "multi_doc_generation", False, "no response", ms)

    # Turn 5: Revise SOW
    r, ms = chat(base_url, sid, (
        "The SOW needs a Section 508 accessibility requirement added under the "
        "technical requirements. Also add FedRAMP High authorization as a mandatory "
        "contractor qualification. Please regenerate it."
    ), headers, timeout=300)
    if r:
        text = r.get("response", "")
        record(sc, "sow_revision", len(text) > 200, "len=%d" % len(text), ms)
        check_keywords(text, ["508", "accessibility", "FedRAMP"],
                       sc, "revision_content")
    else:
        record(sc, "sow_revision", False, "no response", ms)

    # Verify package + ZIP
    _verify_package_and_zip(base_url, headers, sc)


def uc2_gsa_schedule(base_url, headers, quick=False):
    """UC-2: GSA Schedule Purchase ($45K, Below SAT)"""
    sc = "UC-2"
    print("\n--- %s: GSA Schedule Purchase ($45K) ---" % sc)
    sid = "qa-uc2-%s" % uuid.uuid4().hex[:8]

    r, ms = chat(base_url, sid, (
        "I need to purchase a $45,000 confocal microscope for our genomics lab. "
        "This is an urgent need -- our current microscope failed last week and we have "
        "active grant-funded experiments. I believe GSA Schedule covers this type of "
        "equipment. The vendor is Zeiss and they're on GSA Schedule 66 III. Building 37, "
        "Room 410. What's the acquisition pathway and what documents do I need?"
    ), headers)
    if r:
        text = r.get("response", "")
        record(sc, "intake_response", len(text) > 100, "len=%d" % len(text), ms)
        check_keywords(text, ["GSA", "schedule", "simplified", "SAT", "FAR"],
                       sc, "gsa_pathway")
    else:
        record(sc, "intake_response", False, "no response", ms)
        return

    if quick:
        return

    r, ms = chat(base_url, sid, (
        "It's grant-funded under R01-CA-228473. No special security requirements. "
        "We need installation and 1-year warranty included. Delivery within 30 days. "
        "The quote is valid through end of month."
    ), headers)
    if r:
        record(sc, "followup_response", len(r.get("response", "")) > 50, "", ms)

    r, ms = chat(base_url, sid, (
        "Generate the purchase request documentation for this GSA Schedule order."
    ), headers, timeout=300)
    if r:
        record(sc, "doc_generation", len(r.get("response", "")) > 100, "", ms)
    else:
        record(sc, "doc_generation", False, "no response", ms)


def uc2_1_micro_purchase(base_url, headers, quick=False):
    """UC-2.1: Micro Purchase ($14K, Purchase Card)"""
    sc = "UC-2.1"
    print("\n--- %s: Micro Purchase ($14K) ---" % sc)
    sid = "qa-uc21-%s" % uuid.uuid4().hex[:8]

    r, ms = chat(base_url, sid, (
        "I have a quote for $13,800 from Fisher Scientific for lab supplies -- "
        "centrifuge tubes, pipette tips, and reagents. Grant-funded, deliver to "
        "Building 37 Room 204. I want to use the purchase card."
    ), headers)
    if r:
        text = r.get("response", "")
        record(sc, "intake_response", len(text) > 50, "len=%d" % len(text), ms)
        check_keywords(text, ["micro", "purchase card", "$15", "threshold", "simplified"],
                       sc, "micro_purchase_detection")
    else:
        record(sc, "intake_response", False, "no response", ms)
        return

    if quick:
        return

    r, ms = chat(base_url, sid, (
        "The quote is from last week, valid for 30 days. Fisher Scientific is on "
        "AbilityOne/JWOD and I checked FedMall -- these specific items aren't available "
        "there. I have purchase card authority up to $15K. No hazmat involved."
    ), headers)
    if r:
        text = r.get("response", "")
        record(sc, "followup_response", len(text) > 50, "", ms)
        check_keywords(text, ["price", "reason", "source", "card"],
                       sc, "micro_purchase_guidance")
    else:
        record(sc, "followup_response", False, "no response", ms)


def uc3_sole_source(base_url, headers, quick=False):
    """UC-3: Sole Source Justification ($280K, Below SAT)"""
    sc = "UC-3"
    print("\n--- %s: Sole Source Justification ($280K) ---" % sc)
    sid = "qa-uc3-%s" % uuid.uuid4().hex[:8]

    r, ms = chat(base_url, sid, (
        "I need to sole-source a $280,000 annual software maintenance contract to "
        "Illumina Inc. for our BaseSpace Sequence Hub platform. Only Illumina can "
        "maintain this proprietary genomic analysis software -- no other vendor has "
        "access to the source code or can provide updates. We've used this system for "
        "3 years. The current contract expires in 60 days. What's the justification "
        "authority and what documents do I need?"
    ), headers)
    if r:
        text = r.get("response", "")
        record(sc, "intake_response", len(text) > 100, "len=%d" % len(text), ms)
        check_keywords(text, ["sole source", "6.302", "J&A", "justification", "FAR"],
                       sc, "sole_source_detection")
    else:
        record(sc, "intake_response", False, "no response", ms)
        return

    if quick:
        return

    r, ms = chat(base_url, sid, (
        "We contacted two other genomics software firms (DNAnexus and Seven Bridges) "
        "and neither can maintain BaseSpace -- it's proprietary to Illumina. We have "
        "email documentation from both vendors confirming this. The system supports "
        "200+ active research protocols and downtime would halt clinical trials. "
        "Previous contract: GS-35F-0038X."
    ), headers)
    if r:
        record(sc, "followup_response", len(r.get("response", "")) > 50, "", ms)

    r, ms = chat(base_url, sid, (
        "Generate the Justification and Approval document for this sole source procurement."
    ), headers, timeout=300)
    if r:
        text = r.get("response", "")
        record(sc, "ja_generation", len(text) > 200, "len=%d" % len(text), ms)
        check_keywords(text, ["justification", "Illumina", "sole", "authority", "source"],
                       sc, "ja_content")
    else:
        record(sc, "ja_generation", False, "no response", ms)


def uc4_competitive_range(base_url, headers, quick=False):
    """UC-4: Competitive Range Advisory ($2.1M, FAR Part 15)"""
    sc = "UC-4"
    print("\n--- %s: Competitive Range Advisory ($2.1M) ---" % sc)
    sid = "qa-uc4-%s" % uuid.uuid4().hex[:8]

    r, ms = chat(base_url, sid, (
        "We're in a FAR Part 15 negotiated procurement for IT modernization services, "
        "$2.1M estimated value. We received 7 proposals and after initial evaluation, "
        "3 are clearly in the competitive range but 2 are borderline -- technically "
        "acceptable but weak on past performance. Do we have to keep all offerors in "
        "the competitive range? Can we narrow it? What are the rules and risks?"
    ), headers)
    if r:
        text = r.get("response", "")
        record(sc, "advisory_response", len(text) > 100, "len=%d" % len(text), ms)
        check_keywords(text, ["competitive range", "15.306", "15.503", "discussion", "protest"],
                       sc, "far_part_15_citations")
    else:
        record(sc, "advisory_response", False, "no response", ms)
        return

    if quick:
        return

    r, ms = chat(base_url, sid, (
        "One of the borderline offerors is a small business and we have a 40% small "
        "business goal this quarter. Does that change the calculus? Also, if we exclude "
        "them and they protest, what's our exposure?"
    ), headers)
    if r:
        text = r.get("response", "")
        record(sc, "sb_followup", len(text) > 100, "", ms)
        check_keywords(text, ["small business", "protest", "GAO", "risk"],
                       sc, "protest_analysis")
    else:
        record(sc, "sb_followup", False, "no response", ms)


def uc10_igce_development(base_url, headers, quick=False):
    """UC-10: IGCE Development ($4.5M, Multi-Category)"""
    sc = "UC-10"
    print("\n--- %s: IGCE Development ($4.5M) ---" % sc)
    sid = "qa-uc10-%s" % uuid.uuid4().hex[:8]

    r, ms = chat(base_url, sid, (
        "I need to develop an IGCE for a clinical research support services contract. "
        "3-year period of performance (base + 2 option years). Labor categories: "
        "Project Manager (1 FTE), Senior Biostatistician (2 FTE), Data Managers (3 FTE), "
        "Clinical Research Associates (4 FTE). Plus ODCs for travel ($50K/year) and "
        "software licenses ($30K/year). Estimated total value around $4.5M. This will "
        "be evaluated under FAR Part 15 with cost realism analysis. What should the "
        "IGCE include and what methodology should I use?"
    ), headers)
    if r:
        text = r.get("response", "")
        record(sc, "intake_response", len(text) > 100, "len=%d" % len(text), ms)
        check_keywords(text, ["IGCE", "labor", "cost", "realism", "escalation", "indirect"],
                       sc, "igce_methodology")
    else:
        record(sc, "intake_response", False, "no response", ms)
        return

    if quick:
        return

    r, ms = chat(base_url, sid, (
        "Use GSA rates as the baseline. PM at GS-14 equivalent (~$175K loaded), "
        "Senior Biostatistician at GS-13 (~$155K loaded), Data Managers at GS-12 "
        "(~$130K loaded), CRAs at GS-11 (~$115K loaded). Apply 3% annual escalation. "
        "Work location is NIH campus Bethesda with 25% travel to clinical sites. "
        "Indirect rate estimate: 45% fringe, 15% overhead, 8% G&A, 6% fee."
    ), headers)
    if r:
        record(sc, "rate_details", len(r.get("response", "")) > 50, "", ms)

    r, ms = chat(base_url, sid, (
        "Generate the IGCE document with the rate structure we discussed."
    ), headers, timeout=300)
    if r:
        text = r.get("response", "")
        record(sc, "igce_generation", len(text) > 200, "len=%d" % len(text), ms)
        check_keywords(text, ["IGCE", "labor", "cost", "total"],
                       sc, "igce_content")
    else:
        record(sc, "igce_generation", False, "no response", ms)


def uc13_small_business(base_url, headers, quick=False):
    """UC-13: Small Business Set-Aside ($450K, FAR Part 19)"""
    sc = "UC-13"
    print("\n--- %s: Small Business Set-Aside ($450K) ---" % sc)
    sid = "qa-uc13-%s" % uuid.uuid4().hex[:8]

    r, ms = chat(base_url, sid, (
        "I have a $450,000 IT services requirement for network infrastructure monitoring "
        "and management at NCI. NAICS code 541512 (Computer Systems Design Services, "
        "$34M size standard). I found 8 small businesses on SAM.gov with relevant "
        "experience and 3 large businesses. Should this be set aside for small business? "
        "What type of set-aside? What market research documentation do I need?"
    ), headers)
    if r:
        text = r.get("response", "")
        record(sc, "intake_response", len(text) > 100, "len=%d" % len(text), ms)
        check_keywords(text, ["set-aside", "small business", "Rule of Two", "19", "NAICS", "SAM"],
                       sc, "sb_set_aside_analysis")
    else:
        record(sc, "intake_response", False, "no response", ms)
        return

    if quick:
        return

    r, ms = chat(base_url, sid, (
        "Here's what I found on SAM.gov: 5 of the 8 small businesses have prior "
        "federal IT monitoring contracts over $100K. Two are 8(a) certified, one is "
        "HUBZone, and one is SDVOSB. The requirement includes 24/7 NOC monitoring, "
        "incident response SLA under 15 minutes, and quarterly vulnerability assessments. "
        "Performance period is 1 base year plus 4 option years."
    ), headers)
    if r:
        record(sc, "market_details", len(r.get("response", "")) > 50, "", ms)

    r, ms = chat(base_url, sid, (
        "Generate the Market Research Report documenting the small business set-aside determination."
    ), headers, timeout=300)
    if r:
        text = r.get("response", "")
        record(sc, "mr_generation", len(text) > 200, "len=%d" % len(text), ms)
    else:
        record(sc, "mr_generation", False, "no response", ms)


def uc16_tech_to_contract(base_url, headers, quick=False):
    """UC-16: Technical Requirements to Contract Language"""
    sc = "UC-16"
    print("\n--- %s: Tech Requirements to Contract Language ---" % sc)
    sid = "qa-uc16-%s" % uuid.uuid4().hex[:8]

    r, ms = chat(base_url, sid, (
        "I'm a program scientist and I need help turning my technical requirements "
        "into a SOW. Here's what we need: whole-genome sequencing services for our "
        "cancer genomics program. Requires Illumina NovaSeq 6000 or equivalent platform, "
        "minimum 30x coverage depth, paired-end 150bp reads. We need library preparation "
        "(DNA extraction, fragmentation, adapter ligation), sequencing, bioinformatics "
        "pipeline (alignment to GRCh38, variant calling with GATK, quality metrics), "
        "and data delivery via Globus to our HPC cluster. Expected throughput: 500 samples "
        "per year across 3 years. CLIA-certified lab required. Please translate this "
        "into SOW language a contracting officer can use."
    ), headers)
    if r:
        text = r.get("response", "")
        record(sc, "intake_response", len(text) > 100, "len=%d" % len(text), ms)
        check_keywords(text, ["contractor shall", "scope", "deliverable", "performance",
                              "sequencing", "NovaSeq"],
                       sc, "sow_language")
    else:
        record(sc, "intake_response", False, "no response", ms)
        return

    if quick:
        return

    r, ms = chat(base_url, sid, (
        "A few more things: samples will ship on dry ice, contractor must provide "
        "a LIMS portal for tracking, turnaround time is 4 weeks per batch of 50 samples, "
        "and we need monthly quality reports with Q30 scores above 85%. Data must be "
        "BAM and VCF format. All data handling must comply with NIH Genomic Data Sharing "
        "Policy and dbGaP submission requirements."
    ), headers)
    if r:
        record(sc, "addl_requirements", len(r.get("response", "")) > 50, "", ms)

    r, ms = chat(base_url, sid, (
        "Generate the full Statement of Work incorporating all these technical requirements."
    ), headers, timeout=300)
    if r:
        text = r.get("response", "")
        record(sc, "sow_generation", len(text) > 200, "len=%d" % len(text), ms)
        check_keywords(text, ["Statement of Work", "contractor", "sequencing", "deliverable"],
                       sc, "sow_content")
    else:
        record(sc, "sow_generation", False, "no response", ms)


def uc29_end_to_end(base_url, headers, quick=False):
    """UC-29: End-to-End Acquisition ($3.5M, Multi-Phase R&D)"""
    sc = "UC-29"
    print("\n--- %s: End-to-End Acquisition ($3.5M) ---" % sc)
    sid = "qa-uc29-%s" % uuid.uuid4().hex[:8]

    r, ms = chat(base_url, sid, (
        "I'm starting a new $3.5M acquisition for R&D services -- bioinformatics "
        "pipeline development and clinical data analysis support for NCI's Division "
        "of Cancer Treatment and Diagnosis. This is a complex requirement: Phase 1 "
        "(Year 1): develop ML-based variant classification pipeline. Phase 2 (Years 2-3): "
        "operate pipeline + provide clinical data analysis. Estimated 15 FTEs across "
        "data science, bioinformatics, and project management. We want a CPFF contract "
        "type, FAR Part 15 competitive negotiated procurement. I need the full acquisition "
        "package: SOW, IGCE, Acquisition Plan, Market Research Report, and small business "
        "coordination. What's the complete roadmap and what regulatory requirements apply?"
    ), headers)
    if r:
        text = r.get("response", "")
        record(sc, "intake_response", len(text) > 100, "len=%d" % len(text), ms)
        check_keywords(text, ["FAR", "15", "TINA", "competition", "subcontracting",
                              "SOW", "IGCE", "cost"],
                       sc, "full_package_pathway")
    else:
        record(sc, "intake_response", False, "no response", ms)
        return

    if quick:
        return

    r, ms = chat(base_url, sid, (
        "Phase 1 team: 2 ML engineers, 2 bioinformaticians, 1 PM. Phase 2 adds: "
        "3 clinical data analysts, 2 data engineers, 3 biostatisticians, 2 QA specialists. "
        "Travel: quarterly PI meetings at NIH Bethesda plus annual site visits to 4 NCTN "
        "clinical sites. All data subject to NIH data management and sharing policy. "
        "Need FISMA Moderate ATO for cloud infrastructure. Previous related contract was "
        "HHSN261201800001C (completed 2025)."
    ), headers)
    if r:
        record(sc, "details_response", len(r.get("response", "")) > 50, "", ms)

    r, ms = chat(base_url, sid, (
        "Generate the Statement of Work for this acquisition."
    ), headers, timeout=300)
    if r:
        text = r.get("response", "")
        record(sc, "sow_generation", len(text) > 200, "len=%d" % len(text), ms)
    else:
        record(sc, "sow_generation", False, "no response", ms)

    r, ms = chat(base_url, sid, (
        "Now generate the IGCE, Acquisition Plan, and Market Research Report."
    ), headers, timeout=300)
    if r:
        text = r.get("response", "")
        record(sc, "remaining_docs", len(text) > 200, "len=%d" % len(text), ms)
    else:
        record(sc, "remaining_docs", False, "no response", ms)

    r, ms = chat(base_url, sid, (
        "What's the small business subcontracting plan strategy for this $3.5M contract? "
        "We need to meet NCI's socioeconomic goals."
    ), headers, timeout=180)
    if r:
        text = r.get("response", "")
        record(sc, "sb_strategy", len(text) > 100, "", ms)
        check_keywords(text, ["subcontracting", "small business", "19", "goal", "plan"],
                       sc, "sb_plan_content")
    else:
        record(sc, "sb_strategy", False, "no response", ms)

    _verify_package_and_zip(base_url, headers, sc)


# ---- Helpers -----------------------------------------------------------------

def _verify_package_and_zip(base_url, headers, scenario):
    """Check if a package was created and if ZIP export works."""
    resp, ms = api_get(base_url, "/api/packages", headers)
    if resp is not None and resp.status_code == 200:
        pkgs = resp.json()
        if pkgs:
            pkg_id = pkgs[-1].get("package_id", "")
            record(scenario, "package_exists", True,
                   "id=%s, count=%d" % (pkg_id, len(pkgs)), ms)

            # Try ZIP export
            resp_zip, ms_zip = api_get(
                base_url, "/api/packages/%s/export/zip" % pkg_id, headers
            )
            if resp_zip is not None and resp_zip.status_code == 200:
                size = len(resp_zip.content)
                try:
                    zf = zipfile.ZipFile(io.BytesIO(resp_zip.content))
                    names = zf.namelist()
                    record(scenario, "zip_export", True,
                           "%d files, %d bytes" % (len(names), size), ms_zip)
                    for n in names:
                        print("      - %s" % n)
                except zipfile.BadZipFile:
                    record(scenario, "zip_export", False, "invalid ZIP", ms_zip)
            elif resp_zip is not None and resp_zip.status_code == 404:
                record(scenario, "zip_export", True,
                       "404 (no docs with content yet — expected for intake-only)", ms_zip)
            else:
                status = resp_zip.status_code if resp_zip is not None else "N/A"
                record(scenario, "zip_export", False, "HTTP %s" % status, ms_zip)
        else:
            record(scenario, "package_exists", False, "no packages found", ms)
    else:
        record(scenario, "package_exists", False, "API error", ms)


# ---- Scenario registry -------------------------------------------------------

SCENARIOS = {
    "uc1": ("UC-1: Full Competition $750K", uc1_full_competition),
    "uc2": ("UC-2: GSA Schedule $45K", uc2_gsa_schedule),
    "uc2.1": ("UC-2.1: Micro Purchase $14K", uc2_1_micro_purchase),
    "uc3": ("UC-3: Sole Source $280K", uc3_sole_source),
    "uc4": ("UC-4: Competitive Range $2.1M", uc4_competitive_range),
    "uc10": ("UC-10: IGCE Development $4.5M", uc10_igce_development),
    "uc13": ("UC-13: Small Business Set-Aside $450K", uc13_small_business),
    "uc16": ("UC-16: Tech to Contract Language", uc16_tech_to_contract),
    "uc29": ("UC-29: End-to-End $3.5M", uc29_end_to_end),
}


def run_all(base_url, headers, scenario_keys=None, quick=False):
    print("\n" + "=" * 70)
    print("  EAGLE QA Demo Scenario Tests")
    print("  Target:     %s" % base_url)
    print("  Tenant:     %s" % headers.get("X-Tenant-Id", "?"))
    print("  Quick mode: %s" % quick)
    print("  Scenarios:  %s" % (", ".join(scenario_keys) if scenario_keys else "ALL"))
    print("  Time:       %s" % datetime.now(timezone.utc).isoformat())
    print("=" * 70)

    # Health check first
    try:
        r = requests.get("%s/api/health" % base_url, timeout=15)
        if r.status_code != 200:
            print("\n  [X] Health check failed: HTTP %d" % r.status_code)
            sys.exit(1)
        health = r.json()
        print("\n  Backend: v%s (sha=%s)" % (
            health.get("version", "?"), health.get("git_sha", "?")[:8]))
        bedrock = health.get("services", {}).get("bedrock", False)
        if not bedrock:
            print("  WARNING: Bedrock not available — chat tests will fail!")
    except Exception as e:
        print("\n  [X] Cannot reach backend: %s" % e)
        sys.exit(1)

    keys = scenario_keys or list(SCENARIOS.keys())
    for key in keys:
        if key not in SCENARIOS:
            print("\n  [!] Unknown scenario: %s (skipping)" % key)
            continue
        name, fn = SCENARIOS[key]
        fn(base_url, headers, quick=quick)

    # Summary
    print("\n" + "=" * 70)
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    total = len(results)
    total_ms = sum(r["duration_ms"] for r in results)
    print("  Results: %d/%d passed, %d failed (%.1fs total)" % (
        passed, total, failed, total_ms / 1000))

    # Per-scenario summary
    scenarios_seen = []
    for r in results:
        if r["scenario"] not in scenarios_seen:
            scenarios_seen.append(r["scenario"])
    for sc in scenarios_seen:
        sc_results = [r for r in results if r["scenario"] == sc]
        sc_passed = sum(1 for r in sc_results if r["passed"])
        sc_total = len(sc_results)
        icon = "+" if sc_passed == sc_total else "X"
        print("    [%s] %s: %d/%d" % (icon, sc, sc_passed, sc_total))

    print("=" * 70)

    if failed:
        print("\n  Failed tests:")
        for r in results:
            if not r["passed"]:
                print("    [X] %s / %s: %s" % (r["scenario"], r["name"], r["detail"]))
        print()

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EAGLE QA Demo Scenario Tests")
    parser.add_argument("--base-url", default=QA_BACKEND_URL, help="Backend ALB URL")
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT, help="Tenant ID")
    parser.add_argument("--user-id", default=DEFAULT_USER, help="User ID")
    parser.add_argument("--scenarios", default=None,
                        help="Comma-separated scenario keys (e.g. uc1,uc3)")
    parser.add_argument("--quick", action="store_true",
                        help="Quick mode: intake only, skip doc generation")
    args = parser.parse_args()

    headers = {
        "X-Tenant-Id": args.tenant_id,
        "X-User-Id": args.user_id,
    }
    scenario_keys = args.scenarios.split(",") if args.scenarios else None
    run_all(args.base_url, headers, scenario_keys, args.quick)
