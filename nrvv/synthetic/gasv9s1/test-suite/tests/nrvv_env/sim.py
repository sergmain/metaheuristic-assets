import inspect
import random
import re

_RECORD_NAMES = ("record_visit", "record_a_visit", "handle_visit", "visit")
_PAGE_NAMES = ("serve_visit_count_page", "serve_page", "serve_visit_page",
               "request_page", "serve_visit_count", "handle_page_request",
               "get_page", "page")


class Event:
    def __init__(self, event_index, kind, message):
        self.event_index = event_index
        self.kind = kind  # "sent" | "delivered" | "acknowledged"
        self.message = message

    def __repr__(self):
        return "Event(%d, %s, %r)" % (self.event_index, self.kind, self.message.msg_id)


class Message:
    def __init__(self, msg_id, kind, client, payload):
        self.msg_id = msg_id
        self.kind = kind  # "visit" | "page_request"
        self.client = client
        self.payload = payload
        self.sent_index = None
        self.delivered_index = None
        self.reply = None
        self.reply_index = None
        self.number = None

    def __repr__(self):
        return "Message(%d, %s, %s)" % (self.msg_id, self.kind, self.client)


class Client:
    def __init__(self, name):
        self.name = name
        self.sent = []
        self.acknowledgements = []  # visit acks received
        self.pages = []  # page replies received

    @property
    def displayed_numbers(self):
        return [m.number for m in self.pages]


def _extract_number(reply):
    if isinstance(reply, bool):
        return None
    if isinstance(reply, int):
        return reply
    for attr in ("displayed_number", "number", "count", "visit_count"):
        v = getattr(reply, attr, None)
        if isinstance(v, int) and not isinstance(v, bool):
            return v
        if isinstance(reply, dict) and isinstance(reply.get(attr), int):
            return reply[attr]
    if isinstance(reply, dict):
        for v in reply.values():
            if isinstance(v, int) and not isinstance(v, bool):
                return v
    if isinstance(reply, (str, bytes)):
        if isinstance(reply, bytes):
            reply = reply.decode("utf-8", "replace")
        m = re.search(r"\d+", reply)
        if m:
            return int(m.group(0))
    return None


def _call(fn, arg):
    try:
        params = [p for p in inspect.signature(fn).parameters.values()
                  if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_POSITIONAL)
                  and p.default is p.empty]
    except (TypeError, ValueError):
        params = [None]
    if not params:
        return fn()
    return fn(arg)


def _find(app, names, explicit):
    if explicit is not None:
        return explicit
    for n in names:
        f = getattr(app, n, None)
        if callable(f):
            return f
    raise AttributeError("app provides none of %s" % (names,))


class Simulation:
    def __init__(self, seed=0, shuffle=False):
        self.seed = seed
        self.rng = random.Random(seed)
        self.shuffle = shuffle
        self.clients = {}
        self.events = []
        self.messages = []
        self._counter = 0
        self._queue = []
        self._step = None

    # --- clients
    def add_client(self, name):
        if name not in self.clients:
            self.clients[name] = Client(name)
        return self.clients[name]

    def client(self, name):
        return self.add_client(name)

    def _event(self, kind, msg):
        ev = Event(self._counter, kind, msg)
        self._counter += 1
        self.events.append(ev)
        return ev

    def _send(self, client, kind, payload):
        c = self.add_client(client)
        msg = Message(len(self.messages), kind, client, payload)
        self.messages.append(msg)
        msg.sent_index = self._event("sent", msg).event_index
        c.sent.append(msg)
        self._queue.append(msg)
        return msg

    def visit(self, client):
        mid = len(self.messages)
        return self._send(client, "visit",
                          {"client": client, "visit_id": mid})

    def request_page(self, client):
        mid = len(self.messages)
        return self._send(client, "page_request",
                          {"client": client, "request_id": mid})

    # --- transport
    def in_flight(self):
        return list(self._queue)

    def idle(self):
        return not self._queue

    def step(self):
        """Deliver one in-flight message to app; return it or None if idle."""
        if self._step is None:
            raise RuntimeError("not connected")
        return self._step()

    def run_until_idle(self, max_steps=1000000):
        n = 0
        while self._queue:
            if n >= max_steps:
                raise RuntimeError("did not become idle")
            self.step()
            n += 1
        return n

    # --- observation
    def sent_events(self):
        return [e for e in self.events if e.kind == "sent"]

    def delivered_events(self):
        return [e for e in self.events if e.kind == "delivered"]

    def acknowledged_events(self):
        return [e for e in self.events if e.kind == "acknowledged"]

    def visits_sent(self):
        return [m for m in self.messages if m.kind == "visit"]

    def visits_acknowledged(self):
        return [m for m in self.messages if m.kind == "visit" and m.reply_index is not None]

    def page_replies(self):
        return [m for m in self.messages if m.kind == "page_request" and m.reply_index is not None]

    def connect(self, app, record_visit=None, serve_page=None):
        record = _find(app, _RECORD_NAMES, record_visit)
        serve = _find(app, _PAGE_NAMES, serve_page)
        sim = self

        def deliver_visit(msg):
            return _call(record, msg.payload)

        def deliver_page_request(msg):
            return _call(serve, msg.payload)

        def step():
            if not sim._queue:
                return None
            i = sim.rng.randrange(len(sim._queue)) if sim.shuffle else 0
            msg = sim._queue.pop(i)
            msg.delivered_index = sim._event("delivered", msg).event_index
            if msg.kind == "visit":
                reply = deliver_visit(msg)
            else:
                reply = deliver_page_request(msg)
            msg.reply = reply
            msg.reply_index = sim._event("acknowledged", msg).event_index
            c = sim.clients[msg.client]
            if msg.kind == "visit":
                c.acknowledgements.append(msg)
            else:
                msg.number = _extract_number(reply)
                c.pages.append(msg)
            return msg

        self._step = step
        return self


def build(seed=0, clients=(), shuffle=False):
    s = Simulation(seed, shuffle)
    for c in clients:
        s.add_client(c)
    return s
