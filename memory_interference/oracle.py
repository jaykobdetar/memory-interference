"""Independent relational oracle. No imports from machine/generator/renderer.

Targets are calculated only here. Unlike the forward machine, this implementation
does not apply mutations or maintain heads/histories: it selects eligible rows,
then computes their maximum revision. It assumes a previously validated stream.
"""


def answer(events, query):
    rows = tuple(e for e in events
                 if e["op"] != "RECALL"
                 and e["entity"] == query["entity"]
                 and e["key"] == query["key"]
                 and e["position"] <= query["cutoff"])
    if query["mode"] == "revision":
        rows = tuple(e for e in rows if e["revision"] == query["revision"])
    if len(rows) == 0:
        return dict(status="unset", value=None, event_id=None, revision=None)
    newest = max(rows, key=lambda row: row["revision"])
    return dict(status="present" if newest["op"] == "WRITE" else "deleted",
                value=newest["value"], event_id=newest["id"], revision=newest["revision"])


def certificate(events, query, result):
    """A computed evidence certificate, not a model-authored reasoning trace."""
    relevant = [e for e in events if e["entity"] == query["entity"] and e["key"] == query["key"]]
    return {
        "eligible_mutations": [e["id"] for e in relevant
                               if e["op"] != "RECALL" and e["position"] <= query["cutoff"]],
        "ignored_recalls": [e["id"] for e in relevant if e["op"] == "RECALL"],
        "excluded_after_cutoff": [e["id"] for e in relevant
                                  if e["op"] != "RECALL" and e["position"] > query["cutoff"]],
        "selected_event": result["event_id"],
        "selection_rule": "exact_revision" if query["mode"] == "revision" else "maximum_eligible_revision",
    }
