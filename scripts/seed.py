"""Seed script skeleton (T1). Fully built out in T9.

T9's version creates >=2 organisations, each with a Director, >=2 Mission
Leads, a >=6-person crew roster with varied skills/proficiencies/
availability, an org-specific skill taxonomy, and missions spanning at least
three lifecycle states (FR-19). For now this just makes sure the tables
exist so ``python -m scripts.seed`` is a safe, documented no-op.
"""

from __future__ import annotations

from models.database import create_db_and_tables


def seed() -> None:
    create_db_and_tables()
    print(
        "Seed script scaffold only - no demo data yet. "
        "Full multi-tenant seed data (FR-19) lands in T9; see docs/prd/mission-control.md #12."
    )


if __name__ == "__main__":
    seed()
