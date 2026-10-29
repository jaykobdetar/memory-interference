import copy
import itertools
import json
from pathlib import Path
import tempfile
import unittest

from memory_interference.generator import (
    DEFAULT_CONFIG, MODES, INTERFERENCE, canonical, digest, make_record, records, validate_config, worlds,
)
from memory_interference.machine import InvalidStream, Machine, replay
from memory_interference.oracle import answer
from memory_interference.validation import check_record, summarize
from memory_interference.__main__ import generate
from memory_interference.scoring import score


def tiny_config():
    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(groups={"train": 1, "validation": 1, "test": 1}, event_count=32,
                  delays=[4, 8], revisions=[1, 2])
    config["ood"] = {
        "length": dict(groups=1, event_count=64, delays=[4, 8], revisions=[1, 2]),
        "delay": dict(groups=1, event_count=32, delays=[12, 20], revisions=[1, 2]),
        "revisions": dict(groups=1, event_count=32, delays=[4, 8], revisions=[3]),
    }
    return config


def sample(**kwargs):
    args = dict(world=digest("test-world"), split="test", n_events=48, delay=12, n_revisions=3,
                mode="current", interference="near_identity", recall=True)
    args.update(kwargs)
    return make_record(**args)


def event(pos, entity, value, history):
    prior = history.get(entity)
    result = dict(id=f"e{pos}", position=pos, op="WRITE" if value is not None else "DELETE",
                  entity=entity, label=entity, key="k", value=value,
                  revision=1 if prior is None else prior["revision"] + 1,
                  supersedes=None if prior is None else prior["id"], ref=None)
    history[entity] = result
    return result


class OracleTests(unittest.TestCase):
    def test_exhaustive_small_streams(self):
        # All 9,331 action sequences of length 0..5: two slots x {a,b,DELETE}.
        # The third expected-state expression uses list order, not revision maxima.
        streams = queries = 0
        actions = tuple(itertools.product(("x", "y"), ("a", "b", None)))
        for length in range(6):
            for sequence in itertools.product(actions, repeat=length):
                history = {}
                events = [event(i, entity, value, history)
                          for i, (entity, value) in enumerate(sequence, 1)]
                machine = Machine()
                for e in events:
                    machine.apply(e)
                streams += 1
                for cutoff in range(length + 1):
                    for entity in ("x", "y", "never_written"):
                        rows = [e for e in events[:cutoff] if e["entity"] == entity]
                        for revision in (None, 1, 2, 6):
                            query = dict(entity=entity, key="k", mode="as_of" if revision is None else "revision",
                                         cutoff=cutoff, revision=revision)
                            row = (rows[-1] if rows else None) if revision is None else (
                                rows[revision - 1] if len(rows) >= revision else None)
                            expected = dict(status="unset", value=None, event_id=None, revision=None) if row is None else dict(
                                status="deleted" if row["value"] is None else "present", value=row["value"],
                                event_id=row["id"], revision=row["revision"])
                            self.assertEqual(answer(events, query), expected)
                            self.assertEqual(machine.answer(query), expected)
                            queries += 1
        self.assertEqual(streams, 9331)
        self.assertEqual(queries, 649452)

    def test_stale_recall_does_not_overwrite(self):
        r = sample()
        self.assertTrue(r["factors"]["recall_conflict"])
        self.assertNotEqual(r["events"][-1]["value"], r["target"]["value"])
        self.assertEqual(answer(r["events"][:-1], r["query"]), r["target"])

    def test_deletion_then_recreation_and_missing_revision(self):
        history = {}
        events = [event(i, "x", value, history) for i, value in enumerate(("a", None, "b"), 1)]
        for cutoff, status, value in ((0, "unset", None), (1, "present", "a"), (2, "deleted", None), (3, "present", "b")):
            q = dict(entity="x", key="k", mode="as_of", cutoff=cutoff, revision=None)
            self.assertEqual(answer(events, q)["status"], status)
            self.assertEqual(answer(events, q)["value"], value)
        q.update(mode="revision", revision=9)
        self.assertEqual(replay(events, q)["status"], "unset")

    def test_cutoff_is_inclusive_and_late_mutations_excluded(self):
        r = sample(mode="as_of")
        self.assertTrue(r["certificate"]["excluded_after_cutoff"])
        source = next(e for e in r["events"] if e["id"] == r["target"]["event_id"])
        self.assertLess(source["position"], r["query"]["cutoff"])
        inclusive = dict(r["query"], cutoff=source["position"])
        self.assertEqual(answer(r["events"], inclusive), r["target"])
        previous = dict(r["query"], cutoff=source["position"] - 1)
        self.assertNotEqual(answer(r["events"], previous), r["target"])
        self.assertEqual(replay(r["events"][:r["query"]["cutoff"]], r["query"]), r["target"])


class AdversarialTests(unittest.TestCase):
    def test_invalid_streams_rejected(self):
        original = sample()["events"]
        cases = []
        for field, value in (("revision", 99), ("supersedes", "absent"), ("position", 2),
                             ("op", "REWRITE"), ("value", None), ("ref", "e00009")):
            altered = copy.deepcopy(original); altered[0][field] = value; cases.append(altered)
        altered = copy.deepcopy(original); altered[1]["id"] = altered[0]["id"]; cases.append(altered)
        for field, value in (("value", "wrong"), ("ref", "future"), ("revision", 1)):
            altered = copy.deepcopy(original); altered[-1][field] = value; cases.append(altered)
        for events in cases:
            with self.subTest(event=events[-1]):
                with self.assertRaises(InvalidStream):
                    replay(events, sample()["query"])

    def test_invalid_queries_rejected(self):
        r = sample()
        for update in (dict(cutoff=-1), dict(cutoff=49), dict(mode="unknown"), dict(cutoff=47),
                       dict(mode="revision", revision=None), dict(revision=1)):
            with self.assertRaises(ValueError):
                replay(r["events"], dict(r["query"], **update))

    def test_tampered_targets_prompts_spans_and_certificates_rejected(self):
        for field in ("target", "prompt", "evidence", "certificate", "events", "factors"):
            r = sample()
            if field == "target": r[field]["value"] = "forged"
            elif field == "prompt": r[field] += "forged"
            elif field == "evidence": r[field]["answer_span"][0] += 1
            elif field == "certificate": r[field]["selected_event"] = "forged"
            elif field == "events": r[field][0]["extra_field"] = "forged"
            else: r[field]["answer_delay"] += 1
            with self.assertRaises(AssertionError): check_record(r)


class MetamorphicTests(unittest.TestCase):
    def test_eight_interference_variants_invariant(self):
        for mode in MODES:
            variants = [sample(mode=mode, interference=i, recall=r)
                        for i, r in itertools.product(INTERFERENCE, (False, True))]
            outputs = [v["target"] for v in variants]
            self.assertTrue(all(result == outputs[0] for result in outputs))
            shapes = [tuple((e["position"], e["op"], e["revision"], e["supersedes"], e["value"])
                            for e in v["events"][:-1]) for v in variants]
            self.assertTrue(all(shape == shapes[0] for shape in shapes))

    def test_named_revision_queries_do_not_always_select_first(self):
        observed = {sample(world=digest("revision-selection", i), mode="revision")["query"]["revision"]
                    for i in range(30)}
        self.assertEqual(observed, {1, 2, 3})

    def test_irrelevant_prefix_and_suffix_do_not_change_answer(self):
        for mode in MODES:
            r = sample(mode=mode)
            prefix = event(1, "irrelevant-prefix", "noise", {})
            prefix["id"] = "prefix"
            events = [prefix] + [dict(e, position=e["position"] + 1) for e in r["events"]]
            q = dict(r["query"], cutoff=r["query"]["cutoff"] + 1)
            self.assertEqual(replay(events, q), r["target"])
            suffix = event(len(events) + 1, "irrelevant-suffix", "noise", {})
            suffix["id"] = "suffix"
            events.append(suffix)
            if mode != "as_of": q["cutoff"] += 1
            self.assertEqual(replay(events, q), r["target"])

    def test_symbol_bijection_equivariance(self):
        r = sample()
        events = copy.deepcopy(r["events"])
        for e in events:
            for field in ("entity", "key", "value", "id", "ref", "supersedes"):
                if e[field] is not None: e[field] = "π" + e[field]
        query = dict(r["query"], entity="π" + r["query"]["entity"], key="π" + r["query"]["key"])
        expected = dict(r["target"], value="π" + r["target"]["value"], event_id="π" + r["target"]["event_id"])
        self.assertEqual(replay(events, query), expected)
        self.assertEqual(answer(events, query), expected)

    def test_changing_selected_write_changes_target(self):
        r = sample()
        for e in r["events"]:
            if e["id"] == r["target"]["event_id"] or e["ref"] == r["target"]["event_id"]:
                e["value"] = "COUNTERFACTUAL_VALUE"
        self.assertEqual(replay(r["events"], r["query"])["value"], "COUNTERFACTUAL_VALUE")
        self.assertEqual(answer(r["events"], r["query"])["value"], "COUNTERFACTUAL_VALUE")

    def test_stream_length_ood_keeps_controlled_answer_delay(self):
        for n in (48, 512, 4096):
            r = sample(n_events=n)
            check_record(r)
            self.assertEqual(r["factors"]["answer_delay"], 12)


class CorpusTests(unittest.TestCase):
    def test_schema_references_resolve(self):
        schema = json.loads((Path(__file__).resolve().parent.parent / "schemas/record-v1.1.schema.json").read_text())
        def walk(node):
            if isinstance(node, dict):
                if "$ref" in node:
                    self.assertTrue(node["$ref"].startswith("#/"))
                    target = schema
                    for part in node["$ref"][2:].split("/"): target = target[part]
                    self.assertIsInstance(target, dict)
                for value in node.values(): walk(value)
            elif isinstance(node, list):
                for value in node: walk(value)
        walk(schema)

    def test_every_tiny_record_valid(self):
        count = 0
        for r in records(tiny_config()):
            check_record(r); count += 1
        self.assertEqual(count, 564)

    def test_seed_determinism_and_sensitivity(self):
        self.assertEqual(canonical(sample()), canonical(sample()))
        self.assertNotEqual(sample()["target"], sample(world=digest("other-world"))["target"])
        config = tiny_config()
        assigned = list(worlds(config))
        self.assertEqual(len({world for _, world, _ in assigned}), len(assigned))

    def test_byte_reproducibility_manifest_and_balanced_corpus(self):
        with tempfile.TemporaryDirectory() as temporary:
            a, b = Path(temporary) / "a", Path(temporary) / "b"
            ma, mb = generate(tiny_config(), a), generate(tiny_config(), b)
            self.assertEqual(ma, mb)
            self.assertEqual((a / "manifest.json").read_bytes(), (b / "manifest.json").read_bytes())
            for entry in ma["files"]:
                self.assertEqual((a / entry["file"]).read_bytes(), (b / entry["file"]).read_bytes())
            report = summarize(sorted(a.glob("*.jsonl")), ma)
            self.assertEqual(report["records"], 564)
            self.assertEqual(report["paired_core_families"], 66)
            with self.assertRaises(ValueError): generate(tiny_config(), a)
            # Detect a group copied across splits, even with a fresh example ID.
            path = a / "test.jsonl"
            original = json.loads((a / "train.jsonl").read_text().splitlines()[0])
            original["split"] = "test"; original["id"] = digest("transplanted")
            with path.open("a") as out: out.write(canonical(original) + "\n")
            with self.assertRaises(AssertionError): summarize(sorted(a.glob("*.jsonl")))

    def test_budget_failure_keeps_partial_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = tiny_config(); config["max_artifact_bytes"] = 1000
            destination = Path(temporary) / "bounded"
            with self.assertRaisesRegex(ValueError, "budget exceeded"):
                generate(config, destination)
            self.assertTrue(list(destination.glob("*.partial")))
            self.assertFalse((destination / "manifest.json").exists())

    def test_invalid_and_confounded_configs_rejected(self):
        bad = []
        for field, value in (("event_count", 20), ("delays", [1]), ("delays", [31]),
                             ("revisions", [17]), ("revisions", [1, 1]), ("seed", True)):
            c = tiny_config(); c[field] = value; bad.append(c)
        c = tiny_config(); c["ood"]["length"]["delays"] = [8]; bad.append(c)
        c = tiny_config(); c["ood"]["delay"]["event_count"] = 40; bad.append(c)
        for config in bad:
            with self.assertRaises(ValueError): validate_config(config)

    def test_scorer_rejects_wrong_provenance_and_missing_ids(self):
        with tempfile.TemporaryDirectory() as temporary:
            data, pred = Path(temporary) / "data.jsonl", Path(temporary) / "pred.jsonl"
            r = sample(n_revisions=1)
            data.write_text(canonical(r) + "\n")
            prediction = dict(r["target"], event_id="e00001")
            pred.write_text(canonical(dict(id=r["id"], prediction=prediction)) + "\n")
            result = score(data, pred)
            self.assertEqual(result["strata"]["all"]["exact"], 0)
            self.assertEqual(result["strata"]["all"]["value_status"], 1)
            pred.write_text(canonical(dict(id=r["id"], prediction=r["target"])) + "\n")
            self.assertEqual(score(data, pred)["strata"]["all"]["exact"], 1)
            prediction = dict(r["target"], revision=True)
            pred.write_text(canonical(dict(id=r["id"], prediction=prediction)) + "\n")
            self.assertEqual(score(data, pred)["strata"]["all"]["exact"], 0)
            pred.write_text("")
            with self.assertRaises(ValueError): score(data, pred)


if __name__ == "__main__":
    unittest.main()
