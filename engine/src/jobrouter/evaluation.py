"""Transparent quality metrics. No fabricated ground truth or precision on zero results."""


def evaluate(cases, relevant_by_case, required_count=10, precision_floor=.9):
    if required_count < 1 or not 0 <= precision_floor <= 1:
        raise ValueError("Invalid evaluation thresholds")
    rows = []
    # Include the complete supplied reference roster: a failed/omitted run is
    # an empty result, not permission to remove a difficult brief from metrics.
    # Keep unjudged submitted cases too; absent truth cannot make them pass.
    for case_id in dict.fromkeys([*cases, *relevant_by_case]):
        results = cases.get(case_id, [])
        truth = set(relevant_by_case.get(case_id, []))
        # Duplicates remain wasted ranking slots; never remove them and promote rank 11.
        returned = list(results)[:required_count]
        correct = len(set(returned) & truth)
        precision = correct / len(returned) if returned else None
        recall = correct / len(truth) if truth else None
        enough = len(returned) >= min(required_count, len(truth)) if truth else False
        rows.append({"case": case_id, "returned": len(returned), "relevant": correct,
                     "reference_available": len(truth), "precision": precision, "recall": recall,
                     "strict_precision_at_k": correct / required_count,
                     "duplicate_slots": len(returned) - len(set(returned)),
                     "shortfall": max(0, required_count - correct),
                     "enough_results": enough,
                     "pass": bool(truth) and enough and precision is not None and precision >= precision_floor})
    total = sum(x["returned"] for x in rows)
    return {"cases": rows, "micro_precision": sum(x["relevant"] for x in rows) / total if total else None,
            "macro_strict_precision_at_k": sum(x["strict_precision_at_k"] for x in rows) / len(rows) if rows else None,
            "all_case_targets_met": bool(rows) and all(x["pass"] for x in rows),
            "release_pass": False,
            "release_status": "Not assessed: independent held-out judgments, opportunity coverage, sample size and uncertainty review are required"}
