"""Strict exact scoring of supplied predictions; no model integration."""

from collections import Counter, defaultdict
import json


def score(dataset_path, prediction_path):
    predictions = {}
    with prediction_path.open() as source:
        for line in source:
            row = json.loads(line)
            if set(row) != {"id", "prediction"} or row["id"] in predictions:
                raise ValueError("predictions require unique IDs and exactly id/prediction fields")
            predictions[row["id"]] = row["prediction"]
    strata = defaultdict(Counter)
    groups = defaultdict(Counter)
    pairs = defaultdict(list)
    required = set()
    with dataset_path.open() as source:
        for line in source:
            row = json.loads(line)
            record_id = row["id"]
            if record_id not in predictions or record_id in required:
                raise ValueError("every dataset ID must have exactly one prediction")
            required.add(record_id)
            p, t, f = predictions[record_id], row["target"], row["factors"]
            # Require genuine JSON types; Python otherwise treats True as integer 1.
            exact = (isinstance(p, dict) and set(p) == set(t) and
                     all(type(p[k]) is type(t[k]) and p[k] == t[k] for k in t))
            value_only = (isinstance(p, dict) and p.get("status") == t["status"] and
                          "value" in p and type(p["value"]) is type(t["value"]) and p["value"] == t["value"])
            keys = ["all", "subset=" + f["subset"], "mode=" + f["mode"],
                    "interference=" + f["interference"], "revision_count=" + str(f["revision_count"]),
                    "answer_delay=" + str(f["answer_delay"]), "recall=" + str(f["recall"])]
            for key in keys:
                strata[key].update(total=1, exact=int(exact), value_status=int(value_only))
            groups[row["group_id"]].update(total=1, exact=int(exact))
            if f["subset"] == "core": pairs[row["pair_id"]].append(exact)
    if set(predictions) != required:
        raise ValueError("prediction file contains unknown IDs")
    if not required:
        raise ValueError("empty dataset")
    return {
        "records": len(required),
        "strata": {k: dict(v, exact_accuracy=v["exact"] / v["total"],
                           value_status_accuracy=v["value_status"] / v["total"]) for k, v in sorted(strata.items())},
        "group_exact_accuracy": {k: v["exact"] / v["total"] for k, v in sorted(groups.items())},
        "core_pair_all_correct": sum(len(v) == 8 and all(v) for v in pairs.values()),
        "core_pair_count": len(pairs),
        "incomplete_core_pairs": sum(len(v) != 8 for v in pairs.values()),
    }
