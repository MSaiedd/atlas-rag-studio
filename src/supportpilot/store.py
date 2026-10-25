"""Sandbox commerce ledger. Authorization and refund invariants live outside the LLM."""

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path


class NotFound(Exception):
    pass


class Conflict(Exception):
    pass


def eligible(order):
    age = datetime.now(UTC) - datetime.fromisoformat(order["delivered_at"])
    return order["status"] == "delivered" and timedelta(0) <= age <= timedelta(days=30)


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS orders (
                    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, user TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL CHECK(amount_cents > 0),
                    status TEXT NOT NULL, delivered_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS tickets (
                    id TEXT PRIMARY KEY, tenant TEXT NOT NULL, user TEXT NOT NULL,
                    message TEXT NOT NULL, order_id TEXT, status TEXT NOT NULL,
                    response TEXT NOT NULL DEFAULT '', trace TEXT NOT NULL DEFAULT '[]'
                );
                CREATE TABLE IF NOT EXISTS refunds (
                    id TEXT PRIMARY KEY, ticket_id TEXT NOT NULL REFERENCES tickets(id),
                    order_id TEXT NOT NULL UNIQUE REFERENCES orders(id),
                    tenant TEXT NOT NULL, user TEXT NOT NULL, status TEXT NOT NULL,
                    amount_cents INTEGER NOT NULL, decided_by TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, tenant TEXT NOT NULL,
                    actor TEXT NOT NULL, kind TEXT NOT NULL, entity TEXT NOT NULL,
                    timestamp TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def seed(self, tenant, user, order_id="DEMO-1001"):
        """Explicit synthetic data, invoked by CLI only; never seeded at server startup."""
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO orders VALUES (?,?,?,?,?,?)",
                (
                    order_id,
                    tenant,
                    user,
                    4999,
                    "delivered",
                    datetime.now(UTC).isoformat(),
                ),
            )

    def order(self, principal, order_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM orders WHERE id=? AND tenant=? AND user=?",
                (
                    order_id,
                    principal.tenant,
                    principal.user,
                ),
            ).fetchone()
            if not row:
                raise NotFound("Order not found")
            return dict(row)

    def new_ticket(self, principal, message, order_id):
        ticket_id = uuid.uuid4().hex
        with self.connect() as db:
            db.execute(
                "INSERT INTO tickets (id,tenant,user,message,order_id,status) VALUES (?,?,?,?,?,?)",
                (
                    ticket_id,
                    principal.tenant,
                    principal.user,
                    message,
                    order_id,
                    "processing",
                ),
            )
            self.event(db, principal, "ticket.created", ticket_id)
        return ticket_id

    def finish(self, principal, ticket_id, response, trace, status="answered"):
        with self.connect() as db:
            db.execute(
                "UPDATE tickets SET response=?,trace=?,status=? WHERE id=? AND tenant=? AND user=?",
                (
                    response,
                    json.dumps(trace, ensure_ascii=False),
                    status,
                    ticket_id,
                    principal.tenant,
                    principal.user,
                ),
            )
            self.event(db, principal, "ticket." + status, ticket_id)

    def ticket(self, principal, ticket_id):
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM tickets WHERE id=? AND tenant=? AND user=?",
                (
                    ticket_id,
                    principal.tenant,
                    principal.user,
                ),
            ).fetchone()
            if not row:
                raise NotFound("Ticket not found")
            result = dict(row)
            result["trace"] = json.loads(result["trace"])
            result["refunds"] = [
                dict(r)
                for r in db.execute(
                    "SELECT id,status,amount_cents FROM refunds WHERE ticket_id=? AND tenant=?",
                    (ticket_id, principal.tenant),
                )
            ]
            return result

    @staticmethod
    def event(db, principal, kind, entity):
        db.execute(
            "INSERT INTO events(tenant,actor,kind,entity) VALUES (?,?,?,?)",
            (principal.tenant, principal.user, kind, entity),
        )

    def request_refund(self, principal, ticket_id, order_id):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            ticket = db.execute(
                "SELECT * FROM tickets WHERE id=? AND tenant=? AND user=? AND order_id=?",
                (ticket_id, principal.tenant, principal.user, order_id),
            ).fetchone()
            order = db.execute(
                "SELECT * FROM orders WHERE id=? AND tenant=? AND user=?",
                (order_id, principal.tenant, principal.user),
            ).fetchone()
            if not ticket or not order:
                raise NotFound("Order or ticket not found")
            previous = db.execute(
                "SELECT id,status FROM refunds WHERE order_id=?", (order_id,)
            ).fetchone()
            if previous:
                return dict(previous)
            if not eligible(order):
                raise Conflict("Order is outside the refund policy")
            refund_id = uuid.uuid4().hex
            db.execute(
                "INSERT INTO refunds VALUES (?,?,?,?,?,?,?,?)",
                (
                    refund_id,
                    ticket_id,
                    order_id,
                    principal.tenant,
                    principal.user,
                    "pending",
                    order["amount_cents"],
                    None,
                ),
            )
            self.event(db, principal, "refund.requested", refund_id)
            return {"id": refund_id, "status": "pending"}

    def decide(self, principal, refund_id, approve):
        if principal.role != "operator":
            raise PermissionError("Operator role required")
        with self.connect() as db:
            # Lock before reading: concurrent approvals cannot apply the same refund twice.
            db.execute("BEGIN IMMEDIATE")
            refund = db.execute(
                "SELECT * FROM refunds WHERE id=? AND tenant=?", (refund_id, principal.tenant)
            ).fetchone()
            if not refund:
                raise NotFound("Refund not found")
            desired = "approved" if approve else "rejected"
            if refund["status"] == desired:
                return {"id": refund_id, "status": desired, "idempotent_replay": True}
            if refund["status"] != "pending":
                raise Conflict("Refund was already decided")
            if approve:
                order = db.execute(
                    "SELECT * FROM orders WHERE id=? AND tenant=? AND user=?",
                    (refund["order_id"], principal.tenant, refund["user"]),
                ).fetchone()
                if not order or not eligible(order):
                    raise Conflict("Order is no longer eligible")
                db.execute(
                    "UPDATE orders SET status='refunded' WHERE id=? AND tenant=?",
                    (order["id"], principal.tenant),
                )
            db.execute(
                "UPDATE refunds SET status=?,decided_by=? WHERE id=?",
                (desired, principal.user, refund_id),
            )
            self.event(db, principal, "refund." + desired, refund_id)
            return {"id": refund_id, "status": desired, "idempotent_replay": False}

    def pending(self, principal):
        if principal.role != "operator":
            raise PermissionError("Operator role required")
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM refunds WHERE tenant=? AND status='pending'", (principal.tenant,)
                )
            ]

    def events(self, principal):
        if principal.role != "operator":
            raise PermissionError("Operator role required")
        with self.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT * FROM events WHERE tenant=? ORDER BY seq", (principal.tenant,)
                )
            ]
