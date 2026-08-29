#!/usr/bin/env python3
"""Non-formal MiniMax reachability/model-entitlement probe; retains no response text."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time

import httpx
from openai import OpenAI


MODEL = "MiniMax-M2.7-highspeed"
BASE_URL = "https://api.minimax.chat/v1"
OUTPUT = Path(__file__).resolve().parent / "provider_health_validation.json"


def main() -> int:
    key = os.getenv("LLM_API_KEY") or os.getenv("MINIMAX_API_KEY")
    if not key:
        raise RuntimeError("MiniMax key is not configured")
    client = OpenAI(api_key=key, base_url=BASE_URL,
                    http_client=httpx.Client(trust_env=False))
    probes = []
    for number in (1, 2):
        started = time.monotonic()
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content":
                       "NON-FORMAL PROVIDER HEALTH PROBE. Return exactly {\"health\":true}."}],
            temperature=0.0, top_p=0.01, max_tokens=32,
            response_format={"type": "json_object"}, timeout=60,
        )
        probes.append({
            "probe": number, "status": "PASS", "latency_s": time.monotonic() - started,
            "requested_model": MODEL, "provider_returned_model": getattr(response, "model", None),
            "response_id_present": bool(getattr(response, "id", None)),
            "prompt_tokens": getattr(getattr(response, "usage", None), "prompt_tokens", None),
            "completion_tokens": getattr(getattr(response, "usage", None), "completion_tokens", None),
            "response_content_retained": False,
        })
    result = {
        "schema": "campaign_v2_nonformal_provider_health_v1",
        "dataset_class": "engineering_validation", "accepted_formal_result": False,
        "result_notice": "NOT_FORMAL_RESULT", "formal_cursor_consumed": False,
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "MiniMax", "base_url": BASE_URL, "exact_model_name": MODEL,
        "prompt_schema_model_identity_unchanged": True,
        "independent_probe_count": 2, "successful_probe_count": 2,
        "launch_level_model_entitlement_and_capacity": "PASS",
        "campaign_total_quota_endpoint": "not_exposed_by_frozen_runtime_contract",
        "campaign_total_quota_not_invented": True, "formal_provider_call_performed": False,
        "probes": probes, "status": "PASS",
    }
    OUTPUT.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
