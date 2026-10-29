"""Streaming corpus validation and deliberately weak shortcut diagnostics."""

from collections import Counter, defaultdict
import hashlib
import json
import re

from . import SCHEMA_VERSION
from .generator import canonical, MODES, INTERFERENCE
from .machine import replay
from .oracle import answer, certificate
from .render import render


RECORD_FIELDS = {"schema_version", "id", "group_id", "pair_id", "split", "generator_seed", "factors",
                 "events", "query", "prompt", "target", "evidence", "certificate"}
EVENT_FIELDS = {"id", "position", "op", "entity", "label", "key", "value", "revision", "supersedes", "ref"}


def strict_equal(left, right):
    """JSON structural equality with no bool/int/float coercion, including nesting."""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return left.keys() == right.keys() and all(strict_equal(left[k], right[k]) for k in left)
    if type(left) in (list, tuple):
        return len(left) == len(right) and all(strict_equal(a, b) for a, b in zip(left, right))
    return left == right


def check_record(r):
    if type(r) is not dict or set(r) != RECORD_FIELDS or r["schema_version"] != SCHEMA_VERSION:
        raise AssertionError("record schema mismatch")
    if type(r["events"]) is not list or not r["events"] or any(type(e) is not dict or set(e) != EVENT_FIELDS for e in r["events"]):
        raise AssertionError("event schema mismatch")
    for field in ("id", "group_id", "pair_id", "generator_seed"):
        if not isinstance(r[field], str) or not re.fullmatch("[a-f0-9]{64}", r[field]):
            raise AssertionError("invalid hash/seed field")
    if r["generator_seed"] != r["pair_id"] or r["split"] not in (
            "train", "validation", "test", "ood_length", "ood_delay", "ood_revisions"):
        raise AssertionError("invalid seed/split")
    factor_fields = {"mode", "event_count", "answer_delay", "cutoff_gap", "revision_count", "interference", "recall",
                     "recall_conflict", "subset", "expected_status"}
    if type(r["factors"]) is not dict or set(r["factors"]) != factor_fields:
        raise AssertionError("factor schema mismatch")
    if type(r["query"]) is not dict or set(r["query"]) != {"mode", "entity", "key", "cutoff", "revision"}:
        raise AssertionError("query schema mismatch")
    if type(r["target"]) is not dict or set(r["target"]) != {"status", "value", "event_id", "revision"}:
        raise AssertionError("target schema mismatch")
    q = r["query"]
    if (any(type(q[k]) is not str or not q[k] for k in ("mode", "entity", "key")) or
            q["mode"] not in MODES or type(q["cutoff"]) is not int or
            (q["revision"] is not None and (type(q["revision"]) is not int or q["revision"] < 1))):
        raise AssertionError("invalid query types/values")
    if type(r["prompt"]) is not str:
        raise AssertionError("prompt must be a string")
    for e in r["events"]:
        if type(e["id"]) is not str or not re.fullmatch("e[0-9]{5}", e["id"]) or type(e["position"]) is not int:
            raise AssertionError("invalid event identity/position")
        if any(type(e[k]) is not str or not e[k] for k in ("entity", "label", "key")):
            raise AssertionError("invalid entity/label/key")
        if e["revision"] is not None and (type(e["revision"]) is not int or e["revision"] < 1):
            raise AssertionError("revision must be a positive integer or null")
        if type(e["op"]) is not str or e["op"] not in ("WRITE", "DELETE", "RECALL"):
            raise AssertionError("invalid event operation")
        if e["value"] is not None and type(e["value"]) is not str:
            raise AssertionError("event value must be a string or null")
        if any(e[k] is not None and (type(e[k]) is not str or not re.fullmatch("e[0-9]{5}", e[k]))
               for k in ("ref", "supersedes")):
            raise AssertionError("invalid event reference")
    f = r["factors"]
    if (type(f["event_count"]) is not int or not 32 <= f["event_count"] <= 20000 or
            type(f["revision_count"]) is not int or not 0 <= f["revision_count"] <= 16 or
            any(type(f[k]) is not bool for k in ("recall", "recall_conflict")) or
            any(type(f[k]) is not str for k in ("mode", "interference", "subset", "expected_status")) or
            f["interference"] not in INTERFERENCE or
            any(f[k] is not None and (type(f[k]) is not int or f[k] < 1) for k in ("answer_delay", "cutoff_gap"))):
        raise AssertionError("invalid factor values/types")
    expected = answer(r["events"], r["query"])
    if not strict_equal(expected, replay(r["events"], r["query"])) or not strict_equal(expected, r["target"]):
        raise AssertionError("target/oracle/machine mismatch")
    if not strict_equal(certificate(r["events"], r["query"], expected), r["certificate"]):
        raise AssertionError("certificate mismatch")
    prompt, evidence = render(r["events"], r["query"], expected)
    if not strict_equal((prompt, evidence), (r["prompt"], r["evidence"])):
        raise AssertionError("prompt or evidence mismatch")
    if len(r["events"]) != r["factors"]["event_count"]:
        raise AssertionError("event count mismatch")
    f, q = r["factors"], r["query"]
    if f["mode"] != q["mode"] or f["expected_status"] != expected["status"]:
        raise AssertionError("query/status factor mismatch")
    if f["subset"] != ("core" if expected["status"] == "present" else "edge"):
        raise AssertionError("subset factor mismatch")
    target_mutations = [e for e in r["events"] if e["entity"] == q["entity"] and
                        e["key"] == q["key"] and e["op"] != "RECALL"]
    if len(target_mutations) != f["revision_count"]:
        raise AssertionError("revision-count factor mismatch")
    recalls = [e for e in r["events"] if e["op"] == "RECALL"]
    if len(recalls) != int(f["recall"]) or (recalls and recalls[0] != r["events"][-1]):
        raise AssertionError("recall factor mismatch")
    conflict = bool(recalls and recalls[0]["entity"] == q["entity"] and
                    recalls[0]["key"] == q["key"] and recalls[0]["value"] != expected["value"])
    if conflict != f["recall_conflict"]:
        raise AssertionError("recall conflict factor mismatch")
    if f["subset"] == "core":
        target_label = target_mutations[0]["label"]
        for e in r["events"]:
            if e["op"] == "RECALL" or (e["entity"], e["key"]) == (q["entity"], q["key"]):
                continue
            same_entity, same_key = e["entity"] == q["entity"], e["key"] == q["key"]
            constraints = {"unrelated": not same_entity and not same_key,
                           "same_entity": same_entity and not same_key,
                           "same_key": not same_entity and same_key,
                           "near_identity": not same_entity and same_key and e["label"] == target_label
                           and sum(a != b for a, b in zip(e["entity"], q["entity"])) == 1}
            if not constraints.get(f["interference"], False):
                raise AssertionError("interference factor mismatch")
    if evidence:
        lo, hi = evidence["answer_span"]
        if prompt[lo:hi] != evidence["answer_text"]:
            raise AssertionError("invalid answer span")
        source = next(e for e in r["events"] if e["id"] == expected["event_id"])
        if len(r["events"]) - source["position"] != r["factors"]["answer_delay"]:
            raise AssertionError("evidence delay mismatch")
        if q["mode"] == "as_of":
            if f["cutoff_gap"] != q["cutoff"] - source["position"] or f["cutoff_gap"] < 1:
                raise AssertionError("cutoff gap mismatch")
            at_cutoff = r["events"][q["cutoff"] - 1]
            if at_cutoff["op"] == "RECALL" or (at_cutoff["entity"], at_cutoff["key"]) == (q["entity"], q["key"]):
                raise AssertionError("as-of cutoff must land on another slot's mutation")
    elif expected["status"] != "unset" or r["factors"]["answer_delay"] is not None:
        raise AssertionError("only unset targets lack event spans")
    if (q["mode"] != "as_of" or expected["status"] == "unset") and f["cutoff_gap"] is not None:
        raise AssertionError("cutoff gap is defined only for as-of evidence")


def weak_predictions(record):
    """Outputs are event IDs; accuracy requires correct provenance, not value alone."""
    events, q = record["events"], record["query"]
    slot = [e for e in events if e["entity"] == q["entity"] and e["key"] == q["key"]]
    mutations = [e for e in slot if e["op"] != "RECALL"]
    label = next((e["label"] for e in events if e["entity"] == q["entity"]), None)
    def last(rows):
        return rows[-1]["id"] if rows else None
    return {
        "last_event_anywhere": events[-1]["id"],
        "last_key_match_ignores_entity": last([e for e in events if e["key"] == q["key"]]),
        "last_entity_match_ignores_key": last([e for e in events if e["entity"] == q["entity"]]),
        "last_label_key_ignores_identity": last([e for e in events if e["label"] == label and e["key"] == q["key"]]),
        "last_mention_ignores_operation": last(slot),
        "latest_mutation_ignores_query_time": last(mutations),
        "first_mutation_ignores_revisions": mutations[0]["id"] if mutations else None,
    }


def positional_predictions(record):
    """Adversarial rules from the independent review, scored on all four fields."""
    events, q = record["events"], record["query"]
    at_cutoff = events[q["cutoff"] - 1] if q["cutoff"] else None
    mutations = [e for e in events if e["entity"] == q["entity"] and e["key"] == q["key"] and e["op"] != "RECALL"]
    latest = mutations[-1] if mutations else None
    def as_target(event):
        if event is None:
            return dict(status="unset", value=None, event_id=None, revision=None)
        return dict(status="deleted" if event["op"] == "DELETE" else "present", value=event["value"],
                    event_id=event["id"], revision=event["revision"])
    return {"cutoff_event_ignores_identity": as_target(at_cutoff),
            "cutoff_asof_else_latest_slot": as_target(at_cutoff if q["mode"] == "as_of" else latest)}


def summarize(paths, manifest=None):
    counts, groups, pairs, seen_ids = Counter(), {}, {}, set()
    per_split = defaultdict(Counter)
    cells, outcomes, modes = defaultdict(Counter), defaultdict(Counter), defaultdict(Counter)
    shortcuts = defaultdict(lambda: Counter(total=0, correct=0))
    positional = defaultdict(lambda: Counter(total=0, correct=0))
    cutoff_gaps = defaultdict(Counter)
    spans = Counter()
    value_ranks = defaultdict(Counter)
    selected_revisions = defaultdict(Counter)
    prompt_lengths = defaultdict(list)
    recall_conflicts = defaultdict(Counter)
    namespace_owners = {}
    file_results = []
    total_bytes = 0
    for path in paths:
        content_hash = hashlib.sha256()
        file_count, file_bytes = 0, 0
        with path.open("rb") as stream:
            for line in stream:
                content_hash.update(line); file_bytes += len(line)
                r = json.loads(line)
                check_record(r)
                split = r["split"]
                if r["id"] in seen_ids:
                    raise AssertionError("duplicate example ID")
                seen_ids.add(r["id"])
                if groups.setdefault(r["group_id"], split) != split:
                    raise AssertionError("world crosses split boundaries")
                # Every group has a namespace; catch collisions or transplanted entities.
                for token in {e["entity"] for e in r["events"]} | {e["key"] for e in r["events"]} | {
                        e["value"] for e in r["events"] if e["value"] is not None}:
                    if namespace_owners.setdefault(token, r["group_id"]) != r["group_id"]:
                        raise AssertionError("entity/key/value overlaps across worlds")
                f = r["factors"]
                prompt_lengths[split].append(len(r["prompt"]))
                recall_conflicts[split][str(f["recall_conflict"]).lower()] += 1
                pair_state = pairs.setdefault(r["pair_id"], [r["group_id"], r["target"], set()])
                if pair_state[:2] != [r["group_id"], r["target"]]:
                    raise AssertionError("matched interference/recall variants change answer")
                pair_state[2].add((f["interference"], f["recall"]))
                counts[split] += 1; file_count += 1
                per_split[split][f["subset"]] += 1
                outcomes[split][r["target"]["status"]] += 1
                modes[split][f["mode"]] += 1
                spans["present" if r["evidence"] else "unset"] += 1
                if f["subset"] == "core":
                    if f["mode"] == "as_of":
                        cutoff_gaps[split][f["cutoff_gap"]] += 1
                    selected_revisions[(split, f["mode"], f["revision_count"])][r["target"]["revision"]] += 1
                    cell = (f["mode"], f["revision_count"], f["answer_delay"], f["interference"], f["recall"])
                    cells[split][cell] += 1
                    # rank among visible distinct values: a diagnostic for extreme-token shortcuts
                    unique = sorted({e["value"] for e in r["events"] if e["value"] is not None})
                    rank = unique.index(r["target"]["value"])
                    value_ranks[split]["lexicographic_min"] += rank == 0
                    value_ranks[split]["lexicographic_max"] += rank == len(unique) - 1
                    value_ranks[split]["total"] += 1
                    for baseline, prediction in weak_predictions(r).items():
                        for stratum in ("all_core", f'mode={f["mode"]};revisions={f["revision_count"]}'):
                            score = shortcuts[(split, baseline, stratum)]
                            score["total"] += 1
                            score["correct"] += prediction == r["target"]["event_id"]
                    for baseline, prediction in positional_predictions(r).items():
                        for stratum in ("all_core", "mode=" + f["mode"], f'mode={f["mode"]};revisions={f["revision_count"]}'):
                            score = positional[(split, baseline, stratum)]
                            score["total"] += 1
                            score["correct"] += strict_equal(prediction, r["target"])
        result = {"file": path.name, "records": file_count, "bytes": file_bytes,
                  "sha256": content_hash.hexdigest()}
        if manifest:
            entry = next((f for f in manifest["files"] if f["file"] == path.name), None)
            if result != entry:
                raise AssertionError("manifest file hash/count/size mismatch")
        file_results.append(result); total_bytes += file_bytes
    for split, counter in cells.items():
        if len(set(counter.values())) != 1:
            raise AssertionError("unbalanced core factorial")
        observed_modes = {cell[0] for cell in counter}
        r_levels = {cell[1] for cell in counter}; d_levels = {cell[2] for cell in counter}
        if observed_modes != set(MODES) or len(counter) != len(MODES) * len(r_levels) * len(d_levels) * 8:
            raise AssertionError("missing factorial cells")
    required = {(i, recall) for i in INTERFERENCE for recall in (False, True)}
    core_pairs = sum(v[2] == required for v in pairs.values())
    # Supplemental edge records deliberately have one variant per pair.
    if core_pairs * 8 != sum(v["core"] for v in per_split.values()):
        raise AssertionError("incomplete matched variant pairs")
    return {
        "result": "passed", "schema_version": SCHEMA_VERSION,
        "records": sum(counts.values()), "bytes": total_bytes, "files": file_results,
        "split_counts": dict(counts), "groups_per_split": dict(Counter(groups.values())),
        "core_cells_per_split": {s: len(v) for s, v in cells.items()},
        "replicates_per_cell": {s: next(iter(v.values())) for s, v in cells.items()},
        "status_counts": {s: dict(v) for s, v in outcomes.items()},
        "mode_counts": {s: dict(v) for s, v in modes.items()},
        "prompt_characters": {s: {"min": min(v), "max": max(v), "mean": round(sum(v)/len(v), 2)}
                              for s, v in prompt_lengths.items()},
        "recall_conflict_counts": {s: dict(v) for s, v in recall_conflicts.items()},
        "asof_cutoff_gap_counts": {s: dict(v) for s, v in cutoff_gaps.items()},
        "selected_revision_counts": [dict(split=s, mode=m, revisions=n, counts=dict(v))
                                      for (s, m, n), v in sorted(selected_revisions.items())],
        "paired_core_families": core_pairs, "span_counts": dict(spans),
        "lexicographic_value_shortcuts": {s: dict(v) for s, v in value_ranks.items()},
        "shortcut_baselines": [dict(split=s, baseline=b, stratum=t, **v,
                                    accuracy=round(v["correct"] / v["total"], 6))
                               for (s, b, t), v in sorted(shortcuts.items())],
        "positional_shortcut_baselines": [dict(split=s, baseline=b, stratum=t, metric="four_field_exact", **v,
                                              accuracy=round(v["correct"] / v["total"], 6))
                                         for (s, b, t), v in sorted(positional.items())],
        "checks_passed": ["stream invariants", "independent oracle equality", "target equality",
                          "certificate reconstruction", "prompt reconstruction", "exact spans",
                          "exact evidence delays", "positive as-of cutoff gap", "strict nested JSON types",
                          "factor realization", "unique record IDs", "group isolation",
                          "entity/key/value namespace isolation", "complete balanced core factorial",
                          "eight matched variants per core pair", "manifest hashes" if manifest else "file hashes computed"],
        "unrun": ["model training", "model evaluation", "tokenizer-specific length calibration",
                  "external JSON Schema validator (not installed; standard-library record checks used)",
                  "parent-arranged independent cross-review"],
    }
