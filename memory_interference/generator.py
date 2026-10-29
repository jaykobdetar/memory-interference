"""Seeded factorial worlds with matched interference/recall variants."""

import hashlib
import itertools
import json
import random

from . import SCHEMA_VERSION
from .machine import replay
from .oracle import answer, certificate
from .render import render

DEFAULT_CONFIG = {
    "schema_version": SCHEMA_VERSION,
    "seed": 271828,
    "groups": {"train": 4, "validation": 2, "test": 2},
    "event_count": 80,
    "delays": [8, 24],
    "revisions": [1, 3],
    "ood": {
        "length": {"groups": 1, "event_count": 320, "delays": [8, 24], "revisions": [1, 3]},
        "delay": {"groups": 1, "event_count": 80, "delays": [48, 64], "revisions": [1, 3]},
        "revisions": {"groups": 1, "event_count": 80, "delays": [8, 24], "revisions": [8]},
    },
    "max_artifact_bytes": 49_000_000,
}
MODES = ("current", "as_of", "revision")
INTERFERENCE = ("unrelated", "same_entity", "same_key", "near_identity")


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def digest(*parts):
    return hashlib.sha256(canonical(parts).encode()).hexdigest()


def validate_config(config):
    if set(config) != set(DEFAULT_CONFIG):
        raise ValueError("config keys must match the documented v1 config exactly")
    if config["schema_version"] != SCHEMA_VERSION or type(config["seed"]) is not int:
        raise ValueError("invalid schema version or seed")
    if set(config["groups"]) != {"train", "validation", "test"}:
        raise ValueError("groups must specify train, validation, test")
    if any(type(v) is not int or v < 1 for v in config["groups"].values()):
        raise ValueError("each IID split needs at least one world")
    if set(config["ood"]) != {"length", "delay", "revisions"}:
        raise ValueError("v1 requires the three named OOD splits")
    settings = [config] + list(config["ood"].values())
    for setting in settings:
        if setting is not config and (set(setting) != {"groups", "event_count", "delays", "revisions"}
                                     or type(setting["groups"]) is not int or setting["groups"] < 1):
            raise ValueError("invalid OOD group configuration")
        n = setting["event_count"]
        if type(n) is not int or not 32 <= n <= 20000:
            raise ValueError("event_count must be between 32 and 20000")
        for field in ("delays", "revisions"):
            values = setting[field]
            if not isinstance(values, list) or not values or len(set(values)) != len(values):
                raise ValueError(f"{field} must be a nonempty list of distinct integers")
            if any(type(x) is not int or x < 1 for x in values):
                raise ValueError(f"{field} must contain positive integers")
        if max(setting["revisions"]) > 16:
            raise ValueError("v1 supports at most 16 target revisions")
        r = max(setting["revisions"])
        if min(setting["delays"]) < max(r, 4) or max(setting["delays"]) > n - max(r, 4):
            raise ValueError("delays must leave room for target revisions before and after evidence")
    if config["ood"]["length"]["event_count"] <= config["event_count"]:
        raise ValueError("OOD length must exceed IID length")
    if (config["ood"]["length"]["delays"] != config["delays"] or
            config["ood"]["length"]["revisions"] != config["revisions"]):
        raise ValueError("OOD length must preserve IID delay/revision levels")
    if (config["ood"]["delay"]["event_count"] != config["event_count"] or
            config["ood"]["delay"]["revisions"] != config["revisions"] or
            min(config["ood"]["delay"]["delays"]) <= max(config["delays"])):
        raise ValueError("OOD delay must isolate a longer evidence delay")
    if (config["ood"]["revisions"]["event_count"] != config["event_count"] or
            config["ood"]["revisions"]["delays"] != config["delays"] or
            min(config["ood"]["revisions"]["revisions"]) <= max(config["revisions"])):
        raise ValueError("OOD revisions must isolate additional revisions")
    if type(config["max_artifact_bytes"]) is not int or not 1000 <= config["max_artifact_bytes"] <= 49_000_000:
        raise ValueError("artifact byte limit must be between 1000 and 49000000")


def worlds(config):
    """Hash-rank world allocation; no example or contrast pair crosses a split."""
    total = sum(config["groups"].values())
    ranked = sorted(range(total), key=lambda i: digest(config["seed"], "split", i))
    cursor = 0
    for split in ("train", "validation", "test"):
        for index in ranked[cursor:cursor + config["groups"][split]]:
            yield split, digest(config["seed"], "iid-world", index), config
        cursor += config["groups"][split]
    for category in sorted(config["ood"]):
        setting = config["ood"][category]
        for index in range(setting["groups"]):
            yield "ood_" + category, digest(config["seed"], "ood-world", category, index), setting


def make_record(world, split, n_events, delay, n_revisions, mode, interference,
                recall, status="present"):
    pair = digest(SCHEMA_VERSION, world, n_events, delay, n_revisions, mode, status)
    rng = random.Random(int(pair, 16))
    prefix = world[:12]
    # Four one-character neighbors per entity. Labels collide within each group.
    bases = rng.sample(range(16 ** 3), 4)
    entities = [f"E{prefix}_{base:03x}{suffix}" for base in bases for suffix in "abcde"]
    labels = [f"L{prefix}_{i // 5}" for i in range(20)]
    keys = [f"K{prefix}_{x:04x}" for x in rng.sample(range(65536), 7)]
    values = [f"V{prefix}_{x:05x}" for x in rng.sample(range(16 ** 5), 32)]
    entity_index = rng.randrange(20)
    key_index = rng.randrange(6)
    target_entity, target_key = entities[entity_index], keys[key_index]
    chain_key = keys[6] if status == "unset" else target_key
    far_entities = rng.sample([i for i in range(20) if i // 5 != entity_index // 5], 4)
    near_entities = [i for i in range(20) if i // 5 == entity_index // 5 and i != entity_index]
    other_keys = [k for k in keys[:6] if k != target_key]
    if mode == "current":
        chosen = n_revisions - 1
    elif mode == "as_of":
        # Leave at least one intervening distractor, plus the final recall slot.
        # At the tightest delay/revision combination, this excludes revision 1.
        first_allowed = max(0, n_revisions - delay + 1)
        chosen = rng.randrange(first_allowed, max(n_revisions - 1, 1))
    else:
        chosen = rng.randrange(n_revisions)
    source_position = n_events - delay
    cutoff_position = source_position
    if mode == "as_of":
        future_mutations = n_revisions - chosen - 1
        max_gap = delay - future_mutations - 1
        gap_rng = random.Random(int(digest(pair, "cutoff-gap"), 16))
        cutoff_position += gap_rng.randint(1, max_gap)
    positions = (sorted(rng.sample(range(1, source_position), chosen)) + [source_position] +
                 sorted(rng.sample(range(cutoff_position + 1, n_events), n_revisions - chosen - 1)))
    target_values = rng.sample(values, n_revisions)
    target_at = {pos: i for i, pos in enumerate(positions)}
    # Every variant has exactly the same four distractor-slot trajectories.
    # Only entity/key overlap changes, not slot cardinality or revision timing.
    filler = [(rng.randrange(4), rng.choice(values)) for _ in range(n_events)]
    events = []
    heads = {}
    for pos in range(1, n_events + 1):
        e_id = f"e{pos:05d}"
        if pos == n_events and recall:
            candidates = [e for e in events if e["entity"] == target_entity and e["key"] == chain_key
                          and e["op"] == "WRITE" and e["position"] != source_position]
            if not candidates:
                candidates = [e for e in events if e["op"] == "WRITE"]
            ref = candidates[0]
            event = dict(id=e_id, position=pos, op="RECALL", entity=ref["entity"], label=ref["label"],
                         key=ref["key"], value=ref["value"], revision=None, supersedes=None, ref=ref["id"])
        else:
            if pos in target_at:
                i = target_at[pos]
                entity, label, key, value = target_entity, labels[entity_index], chain_key, target_values[i]
                op = "DELETE" if status == "deleted" and i == chosen else "WRITE"
            else:
                slot_pick, value = filler[pos - 1]
                entity_ix = (entity_index if interference == "same_entity" else
                             near_entities[slot_pick] if interference == "near_identity" else far_entities[slot_pick])
                entity, label = entities[entity_ix], labels[entity_ix]
                key = target_key if interference in ("same_key", "near_identity") else other_keys[slot_pick]
                op = "WRITE"
            slot = entity, key
            previous = heads.get(slot)
            event = dict(id=e_id, position=pos, op=op, entity=entity, label=label, key=key,
                         value=None if op == "DELETE" else value,
                         revision=1 if previous is None else previous["revision"] + 1,
                         supersedes=None if previous is None else previous["id"], ref=None)
            heads[slot] = event
        events.append(event)
    query = dict(mode=mode, entity=target_entity, key=target_key,
                 cutoff=cutoff_position if mode == "as_of" else n_events,
                 revision=chosen + 1 if mode == "revision" else None)
    # Validate the full stream with the forward implementation, then label from
    # the independent row-selection oracle. Neither path calls a model.
    forward_result = replay(events, query)
    target = answer(events, query)
    if target != forward_result or target["status"] != status:
        raise AssertionError("oracle/forward state/experimental status disagreement")
    prompt, evidence = render(events, query, target)
    last = events[-1]
    recall_conflict = (last["op"] == "RECALL" and last["entity"] == query["entity"]
                       and last["key"] == query["key"] and last["value"] != target["value"])
    return {
        "schema_version": SCHEMA_VERSION,
        "id": digest(pair, interference, recall),
        "group_id": world,
        "pair_id": pair,
        "split": split,
        "generator_seed": pair,
        "factors": dict(mode=mode, event_count=n_events, answer_delay=delay if evidence else None,
                        cutoff_gap=cutoff_position - source_position if mode == "as_of" and evidence else None,
                        revision_count=n_revisions if status != "unset" else 0,
                        interference=interference, recall=bool(recall), recall_conflict=recall_conflict,
                        subset="core" if status == "present" else "edge", expected_status=status),
        "events": events, "query": query, "prompt": prompt,
        "target": target, "evidence": evidence,
        "certificate": certificate(events, query, target),
    }


def records(config):
    validate_config(config)
    for split, world, setting in worlds(config):
        for mode, revisions, delay in itertools.product(MODES, setting["revisions"], setting["delays"]):
            for interference, recall in itertools.product(INTERFERENCE, (False, True)):
                yield make_record(world, split, setting["event_count"], delay, revisions, mode,
                                  interference, recall)
        # Edge cases are balanced across modes and missing/deleted outcomes.
        # They are diagnostic supplements, not part of the core factorial.
        for mode, status in itertools.product(MODES, ("deleted", "unset")):
            yield make_record(world, split, setting["event_count"], max(setting["delays"]),
                              max(setting["revisions"]), mode, "near_identity", True, status)
