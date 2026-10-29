"""Forward event-sourced implementation used for validation, never to label data."""


class InvalidStream(ValueError):
    pass


class Machine:
    def __init__(self):
        self.events = {}
        self.history = {}
        self.position = 0

    def apply(self, event):
        e = event
        if e["position"] != self.position + 1 or e["id"] in self.events:
            raise InvalidStream("positions must be contiguous and event IDs unique")
        slot = (e["entity"], e["key"])
        if e["op"] == "RECALL":
            ref = self.events.get(e["ref"])
            if (ref is None or ref["op"] != "WRITE" or
                    any(ref[k] != e[k] for k in ("entity", "key", "value")) or
                    e["revision"] is not None or e["supersedes"] is not None):
                raise InvalidStream("recalls must quote an earlier WRITE exactly")
        elif e["op"] in ("WRITE", "DELETE"):
            prior = self.history.get(slot, [])
            if e["revision"] != len(prior) + 1:
                raise InvalidStream("revision must increment by one")
            if e["supersedes"] != (prior[-1]["id"] if prior else None):
                raise InvalidStream("supersedes must identify the previous mutation")
            if e["ref"] is not None:
                raise InvalidStream("mutations cannot quote another event")
            if e["op"] == "WRITE" and not isinstance(e["value"], str):
                raise InvalidStream("WRITE needs a string value")
            if e["op"] == "DELETE" and e["value"] is not None:
                raise InvalidStream("DELETE cannot contain a value")
            self.history.setdefault(slot, []).append(dict(e))
        else:
            raise InvalidStream("unknown operation")
        self.events[e["id"]] = dict(e)
        self.position += 1

    def answer(self, query):
        cutoff = query["cutoff"]
        if not 0 <= cutoff <= self.position:
            raise ValueError("invalid cutoff")
        if query["mode"] not in ("current", "as_of", "revision"):
            raise ValueError("unknown query mode")
        if query["mode"] == "current" and cutoff != self.position:
            raise ValueError("current query must use the end of the stream")
        if query["mode"] == "revision" and (type(query["revision"]) is not int or query["revision"] < 1):
            raise ValueError("revision query needs a positive integer")
        if query["mode"] != "revision" and query["revision"] is not None:
            raise ValueError("state queries cannot select a revision")
        eligible = [e for e in self.history.get((query["entity"], query["key"]), [])
                    if e["position"] <= cutoff]
        if query["mode"] == "revision":
            eligible = [e for e in eligible if e["revision"] == query["revision"]]
        if not eligible:
            return {"status": "unset", "value": None, "event_id": None, "revision": None}
        e = eligible[-1]
        return {"status": "deleted" if e["op"] == "DELETE" else "present",
                "value": e["value"], "event_id": e["id"], "revision": e["revision"]}


def replay(events, query):
    machine = Machine()
    for event in events:
        machine.apply(event)
    return machine.answer(query)
