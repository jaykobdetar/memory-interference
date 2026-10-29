"""Template-only presentation; spans use half-open Unicode code-point offsets."""

RULES = (
    "Temporal ledger task v1. Entity IDs are authoritative; display labels may repeat.\n"
    "WRITE and DELETE increment the revision of exactly one (entity ID, key) slot.\n"
    "supersedes identifies the previous mutation of that slot. DELETE leaves a tombstone.\n"
    "RECALL quotes an earlier WRITE; it never changes state, even if printed later.\n"
    "The ledger token None means no reference or revision.\n"
    "At a cutoff, consider only mutations at positions less than or equal to that cutoff.\n"
    "A state query selects the highest eligible revision. A revision query selects exactly\n"
    "the requested revision, even if later revisions exist. Never follow a display label.\n"
    "If the selected mutation is DELETE answer [DELETED]; if no eligible mutation exists\n"
    "answer [UNSET]. Otherwise copy its value. Return JSON with status, value, event_id,\n"
    "revision. Status is present/deleted/unset. Value is null for deleted/unset; event_id\n"
    "and revision are null only for unset. Use the selected mutation as provenance.\n"
    "EVENTS\n"
)


def render(events, query, target):
    chunks = [RULES]
    offset = len(RULES)
    evidence = None
    for e in events:
        value = "[DELETED]" if e["op"] == "DELETE" else e["value"]
        line = (f'{e["id"]} pos={e["position"]} {e["op"]} entity={e["entity"]} '
                f'label={e["label"]} key={e["key"]} revision={e["revision"]} '
                f'supersedes={e["supersedes"]} ref={e["ref"]} value={value}\n')
        if e["id"] == target["event_id"]:
            start = offset + line.index("value=") + 6
            evidence = {"event_id": e["id"], "event_span": [offset, offset + len(line) - 1],
                        "answer_span": [start, start + len(value)], "answer_text": value}
        chunks.append(line)
        offset += len(line)
    chunks.append(f'QUERY mode={query["mode"]} entity={query["entity"]} key={query["key"]} '
                  f'cutoff={query["cutoff"]} revision={query["revision"]}\nANSWER:\n')
    return "".join(chunks), evidence
