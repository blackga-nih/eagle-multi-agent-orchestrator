"""EAGLE Eval AWS Publisher — S3 archival + CloudWatch custom metrics.

Standalone module. Lazy-loads boto3 clients. All operations non-fatal
(try/except wrappers). Uses EVAL_S3_BUCKET env var
(default: ).

Public API:
    publish_eval_metrics(results, run_timestamp, total_cost_usd)
    archive_results_to_s3(local_path, run_timestamp)
    archive_videos_to_s3(video_base_dir, run_timestamp)
"""

import os
from typing import Optional

# ---------------------------------------------------------------------------
# Lazy boto3 clients
# ---------------------------------------------------------------------------
_cw_client = None
_s3_client = None

_BUCKET = os.environ.get("EVAL_S3_BUCKET", "")
_NAMESPACE = "EAGLE/Eval"
_REGION = os.environ.get("AWS_REGION", "us-east-1")

# All 28 test names (must stay in sync with test_eagle_sdk_eval.py)
_TEST_NAMES = {
    1: "1_session_creation",
    2: "2_session_resume",
    3: "3_trace_observation",
    4: "4_subagent_orchestration",
    5: "5_cost_tracking",
    6: "6_tier_gated_tools",
    7: "7_skill_loading",
    8: "8_subagent_tool_tracking",
    9: "9_oa_intake_workflow",
    10: "10_legal_counsel_skill",
    11: "11_market_intelligence_skill",
    12: "12_tech_review_skill",
    13: "13_public_interest_skill",
    14: "14_document_generator_skill",
    15: "15_supervisor_multi_skill_chain",
    16: "16_s3_document_ops",
    17: "17_dynamodb_intake_ops",
    18: "18_cloudwatch_logs_ops",
    19: "19_document_generation",
    20: "20_cloudwatch_e2e_verification",
    21: "21_uc02_micro_purchase",
    22: "22_uc03_option_exercise",
    23: "23_uc04_contract_modification",
    24: "24_uc05_co_package_review",
    25: "25_uc07_contract_closeout",
    26: "26_uc08_shutdown_notification",
    27: "27_uc09_score_consolidation",
    28: "28_sdk_skill_subagent_orchestration",
    29: "29_compliance_matrix_query_requirements",
    30: "30_compliance_matrix_search_far",
    31: "31_compliance_matrix_vehicle_suggestion",
    32: "32_admin_manager_skill_registered",
    33: "33_workspace_store_default_creation",
    34: "34_store_crud_functions_exist",
    35: "35_uc01_new_acquisition_package",
    36: "36_uc02_gsa_schedule",
    37: "37_uc03_sole_source",
    38: "38_uc04_competitive_range",
    39: "39_uc10_igce_development",
    40: "40_uc13_small_business_setaside",
    41: "41_uc16_tech_to_contract_language",
    42: "42_uc29_e2e_acquisition",
    43: "43_intake_calls_search_far",
    44: "44_legal_cites_far_authority",
    45: "45_market_does_web_research",
    46: "46_doc_gen_creates_document",
    47: "47_supervisor_delegates_not_answers",
    48: "48_compliance_matrix_before_routing",
    # Phase 3: Langfuse trace validation + CloudWatch E2E
    49: "49_trace_has_environment_tag",
    50: "50_trace_token_counts_match",
    51: "51_trace_shows_subagent_hierarchy",
    52: "52_trace_session_id_propagated",
    53: "53_emit_test_result_event",
    54: "54_emit_run_summary_event",
    55: "55_tool_timing_in_cw_event",
    # Phase 4: KB integration
    56: "56_far_search_returns_clauses",
    57: "57_kb_search_finds_policy",
    58: "58_kb_fetch_reads_document",
    59: "59_web_search_for_market_data",
    60: "60_compliance_matrix_threshold",
    # Phase 5: MVP1 UC E2E
    61: "61_uc01_new_acquisition_e2e",
    62: "62_uc02_micro_purchase_e2e",
    63: "63_uc03_sole_source_e2e",
    64: "64_uc04_competitive_range_e2e",
    65: "65_uc05_package_review_e2e",
    66: "66_uc07_contract_closeout_e2e",
    67: "67_uc08_shutdown_notification_e2e",
    68: "68_uc09_score_consolidation_e2e",
    69: "69_uc10_igce_development_e2e",
    70: "70_uc13_small_business_e2e",
    71: "71_uc16_tech_to_contract_e2e",
    72: "72_uc29_full_acquisition_e2e",
    # Phase 6: Document generation
    73: "73_generate_sow_with_sections",
    74: "74_generate_igce_with_pricing",
    75: "75_generate_ap_with_far_refs",
    76: "76_generate_market_research_with_sources",
    # Category 7: Context loss detection
    77: "77_skill_prompt_not_truncated",
    78: "78_subagent_receives_full_query",
    79: "79_subagent_result_not_lost",
    80: "80_input_tokens_within_context_window",
    81: "81_history_messages_count",
    82: "82_no_empty_subagent_responses",
    # Category 8: Handoff validation
    83: "83_intake_findings_reach_supervisor",
    84: "84_legal_risk_rating_propagates",
    85: "85_multi_skill_chain_context",
    86: "86_supervisor_synthesizes",
    87: "87_document_context_from_intake",
    # Category 9: State persistence
    88: "88_session_creates_and_persists",
    89: "89_message_saved_after_turn",
    90: "90_history_loaded_on_resume",
    91: "91_100_message_limit_behavior",
    92: "92_tool_calls_in_saved_messages",
    93: "93_session_metadata_updates",
    94: "94_concurrent_session_isolation",
    # Category 10: Context budget
    95: "95_supervisor_prompt_size",
    96: "96_skill_prompts_all_within_4k",
    97: "97_total_input_tokens_in_langfuse",
    98: "98_cache_utilization",
    # Category 11: Package Creation & Download
    99:  "99_uc01_full_package_creation",
    100: "100_template_no_handlebars",
    101: "101_sow_minimum_required_fields",
    102: "102_igce_dollar_consistency",
    103: "103_package_zip_export_integrity",
    104: "104_docx_export_integrity",
    105: "105_pdf_export_integrity",
    106: "106_document_versioning",
    107: "107_export_api_endpoint",
    # Category 12: Input Guardrails
    108: "108_guardrail_vague_requirement",
    109: "109_guardrail_missing_dollar",
    110: "110_guardrail_out_of_scope",
    111: "111_guardrail_sole_source_no_ja",
    112: "112_guardrail_micropurchase_sow",
    113: "113_guardrail_purchase_card_limit",
    114: "114_guardrail_ja_without_mrr",
    115: "115_guardrail_ja_authority_ambiguous",
    # Category 13: Content Quality
    116: "116_content_no_handlebars_all_types",
    117: "117_content_far_citations_real",
    118: "118_content_ap_milestones_filled",
    119: "119_content_sow_deliverables_filled",
    120: "120_content_igce_data_sources",
    121: "121_content_mrr_small_business",
    122: "122_content_ja_authority_checked",
    # Category 14: Skill-Level Quality
    123: "123_skill_legal_cites_far_clauses",
    124: "124_skill_market_names_vendors",
    125: "125_skill_intake_routes_micropurchase",
    126: "126_skill_tech_quantified_criteria",
    127: "127_skill_docgen_research_first",
    128: "128_skill_supervisor_delegates",
    # Category 15: Demo Script Multi-Turn UC Tests
    129: "129_uc02_gsa_schedule_multi_turn",
    130: "130_uc02_1_micro_purchase_multi_turn",
    131: "131_uc03_sole_source_multi_turn",
    132: "132_uc04_competitive_range_multi_turn",
    133: "133_uc10_igce_multi_turn",
    134: "134_uc13_small_business_multi_turn",
    135: "135_uc16_tech_to_contract_multi_turn",
    136: "136_uc29_e2e_acquisition_multi_turn",
    137: "137_uc29_finalize_package",
}


def _get_cw():
    global _cw_client
    if _cw_client is None:
        import boto3
        _cw_client = boto3.client("cloudwatch", region_name=_REGION)
    return _cw_client


def _get_s3():
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client("s3", region_name=_REGION)
    return _s3_client


# ---------------------------------------------------------------------------
# publish_eval_metrics
# ---------------------------------------------------------------------------

def publish_eval_metrics(
    results: dict,
    run_timestamp: str,
    total_cost_usd: float = 0.0,
    test_summaries: dict = None,
) -> bool:
    """Publish eval metrics to CloudWatch EAGLE/Eval namespace.

    Args:
        results: test_id/result_key -> True/False/None
        run_timestamp: ISO timestamp string for the run
        total_cost_usd: aggregate cost for the run
        test_summaries: optional dict[int, dict] from TraceCollector.summary() per test
            Keys: total_input_tokens, total_output_tokens, total_cost_usd, session_id

    Returns True on success, False on failure (non-fatal).
    """
    try:
        passed = sum(1 for v in results.values() if v is True)
        failed = sum(1 for v in results.values() if v is False)
        skipped = sum(1 for v in results.values() if v is None)
        total = passed + failed + skipped
        pass_rate = (passed / total * 100) if total > 0 else 0.0

        metric_data = [
            # Aggregate pass rate (no dimensions — for dashboard trending)
            {"MetricName": "PassRate", "Value": pass_rate, "Unit": "Percent"},
            # Per-run pass rate
            {
                "MetricName": "PassRate",
                "Value": pass_rate,
                "Unit": "Percent",
                "Dimensions": [{"Name": "RunId", "Value": run_timestamp}],
            },
            {"MetricName": "TestsPassed", "Value": float(passed), "Unit": "Count"},
            {"MetricName": "TestsFailed", "Value": float(failed), "Unit": "Count"},
            {"MetricName": "TestsSkipped", "Value": float(skipped), "Unit": "Count"},
        ]

        if total_cost_usd > 0:
            metric_data.append(
                {"MetricName": "TotalCost", "Value": total_cost_usd, "Unit": "None"}
            )

        # Aggregate token metrics from per-test summaries
        summaries = test_summaries or {}
        total_input = sum(s.get("total_input_tokens", 0) for s in summaries.values())
        total_output = sum(s.get("total_output_tokens", 0) for s in summaries.values())
        if total_input > 0:
            metric_data.append(
                {"MetricName": "TotalInputTokens", "Value": float(total_input), "Unit": "Count"}
            )
        if total_output > 0:
            metric_data.append(
                {"MetricName": "TotalOutputTokens", "Value": float(total_output), "Unit": "Count"}
            )

        # Per-test status (1.0 = pass, 0.0 = fail/skip) + per-test tokens/cost
        for test_id, test_name in _TEST_NAMES.items():
            result_val = results.get(test_id)
            dims = [{"Name": "TestName", "Value": test_name}]
            metric_data.append({
                "MetricName": "TestStatus",
                "Value": 1.0 if result_val is True else 0.0,
                "Unit": "None",
                "Dimensions": dims,
            })

            # Per-test token/cost metrics (only if we have summary data)
            ts = summaries.get(test_id, {})
            in_tok = ts.get("total_input_tokens", 0)
            out_tok = ts.get("total_output_tokens", 0)
            cost = ts.get("total_cost_usd", 0.0)
            if in_tok > 0:
                metric_data.append({
                    "MetricName": "InputTokens", "Value": float(in_tok),
                    "Unit": "Count", "Dimensions": dims,
                })
            if out_tok > 0:
                metric_data.append({
                    "MetricName": "OutputTokens", "Value": float(out_tok),
                    "Unit": "Count", "Dimensions": dims,
                })
            if cost > 0:
                metric_data.append({
                    "MetricName": "CostUSD", "Value": cost,
                    "Unit": "None", "Dimensions": dims,
                })

        # CloudWatch put_metric_data limit: 1000 metric data points per call
        cw = _get_cw()
        for i in range(0, len(metric_data), 1000):
            cw.put_metric_data(Namespace=_NAMESPACE, MetricData=metric_data[i:i+1000])
        count = len(metric_data)
        print(f"CloudWatch Metrics: published {count} metrics to {_NAMESPACE}")
        return True
    except Exception as exc:
        print(f"CloudWatch Metrics: publish failed (non-fatal): {exc}")
        return False


# ---------------------------------------------------------------------------
# archive_results_to_s3
# ---------------------------------------------------------------------------

def archive_results_to_s3(
    local_path: str,
    run_timestamp: str,
) -> Optional[str]:
    """Upload results JSON to S3. Returns S3 URI or None on failure."""
    try:
        s3_key = f"eval/results/run-{run_timestamp}.json"
        _get_s3().upload_file(local_path, _BUCKET, s3_key)
        uri = f"s3://{_BUCKET}/{s3_key}"
        print(f"S3 Archive: uploaded results to {uri}")
        return uri
    except Exception as exc:
        print(f"S3 Archive: upload failed (non-fatal): {exc}")
        return None


# ---------------------------------------------------------------------------
# archive_videos_to_s3
# ---------------------------------------------------------------------------

def archive_videos_to_s3(
    video_base_dir: str,
    run_timestamp: str,
) -> int:
    """Walk video_base_dir for .webm/.mp4 files and upload to S3.

    S3 key: eval/videos/<run-ts>/<test_dir>/<file>
    Returns upload count.
    """
    count = 0
    if not os.path.isdir(video_base_dir):
        return count
    try:
        s3 = _get_s3()
        for dirpath, _dirs, files in os.walk(video_base_dir):
            for fname in files:
                if not fname.endswith((".webm", ".mp4")):
                    continue
                local = os.path.join(dirpath, fname)
                rel = os.path.relpath(local, video_base_dir).replace("\\", "/")
                s3_key = f"eval/videos/{run_timestamp}/{rel}"
                try:
                    s3.upload_file(local, _BUCKET, s3_key)
                    count += 1
                except Exception as exc:
                    print(f"S3 Archive: video upload failed for {rel} (non-fatal): {exc}")
        if count:
            print(f"S3 Archive: uploaded {count} video(s) to s3://{_BUCKET}/eval/videos/{run_timestamp}/")
    except Exception as exc:
        print(f"S3 Archive: video walk failed (non-fatal): {exc}")
    return count
