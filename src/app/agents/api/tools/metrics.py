"""Coverage metrics — deterministic computations only.

Implements formulas from MASTEST paper Section IV-C:
  (1) Syntax correctness  — bracket balance & structure checks
  (2) Data type correctness  — delegated to the LLM orchestrator
  (3) Usability (Levenshtein) — editing distance
  (4-5) Scenario coverage  — set intersection ratio
  (7) Operation coverage  — proportion of ops tested
  (8) Status code coverage  — delegated to the LLM orchestrator

All LLM-based analysis (data type checking, status code coverage) is
handled by the orchestrator agent following instructions in the system
prompt. This module provides only the deterministic math.
"""

from __future__ import annotations

import json
from typing import Any

import Levenshtein

# -- Syntax checker (deterministic) -------------------------------------------

def check_script_syntax(script: str) -> str:
    """Validate a TypeScript test script structure.

    Checks bracket balance and required Playwright test constructs.
    This is a fast heuristic -- for full validation, the orchestrator
    can run ``npx tsc --noEmit`` via the shell.

    Args:
        script: TypeScript test script content.

    Returns:
        JSON string with ``valid``, ``errors``, and ``error_count``.
    """
    errors: list[str] = []

    if "test(" not in script and "describe(" not in script:
        errors.append("Missing test() or describe() block")

    if script.count("{") != script.count("}"):
        errors.append("Mismatched curly braces")
    if script.count("(") != script.count(")"):
        errors.append("Mismatched parentheses")
    if script.count("[") != script.count("]"):
        errors.append("Mismatched square brackets")

    return json.dumps({
        "valid": len(errors) == 0,
        "errors": errors,
        "error_count": len(errors),
    }, indent=2)


# -- Coverage calculations (deterministic) ------------------------------------

def _parse_json_list(raw: str) -> list[str]:
    """Safely parse a JSON string array, returning [] on failure."""
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []


def compute_coverage(
    parsed_api_json: str,
    *,
    generated_scenarios_json: str = "[]",
    accepted_scenarios_json: str = "[]",
    tested_operation_ids_json: str = "[]",
    original_script: str = "",
    final_script: str = "",
) -> str:
    """Compute all deterministic coverage metrics in one call.

    Args:
        parsed_api_json: Output from ``parse_openapi_spec`` (JSON string).
        generated_scenarios_json: JSON array of scenario names the LLM produced.
        accepted_scenarios_json: JSON array of scenario names after review.
        tested_operation_ids_json: JSON array of operationIds covered by scripts.
        original_script: Raw LLM-generated script for usability calc (optional).
        final_script: Edited script for usability calc (optional).

    Returns:
        JSON string with ``scenario_coverage``, ``operation_coverage``,
        and ``usability`` (when both scripts are provided).
    """
    parsed = json.loads(parsed_api_json)
    result: dict[str, Any] = {}

    # -- Scenario coverage (formulas 4-5) --
    generated = _parse_json_list(generated_scenarios_json)
    accepted = _parse_json_list(accepted_scenarios_json)
    gen_set, acc_set = set(generated), set(accepted)
    result["scenario_coverage"] = {
        "generated": len(gen_set),
        "accepted": len(acc_set),
        "coverage_pct": round(
            len(gen_set & acc_set) / len(acc_set) * 100, 2
        ) if acc_set else 100.0,
        "added_manually": len(acc_set - gen_set),
        "rejected": len(gen_set - acc_set),
    }

    # -- Operation coverage (formula 7) --
    all_ops = {op["operationId"] for op in parsed.get("operations", [])}
    tested = set(_parse_json_list(tested_operation_ids_json))
    result["operation_coverage"] = {
        "total_operations": len(all_ops),
        "tested": len(tested),
        "coverage_pct": round(
            len(tested) / len(all_ops) * 100, 2
        ) if all_ops else 0.0,
        "untested": sorted(all_ops - tested),
    }

    # -- Usability (formula 3) --
    if original_script and final_script:
        dist = Levenshtein.distance(original_script, final_script)
        max_len = max(len(original_script), len(final_script), 1)
        result["usability"] = {
            "levenshtein_distance": dist,
            "normalized_distance": round(dist / max_len, 4),
            "similarity": round(1.0 - dist / max_len, 4),
        }

    return json.dumps(result, indent=2)
