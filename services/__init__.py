"""Domain logic (the middle of the api -> services -> models layering).

Empty in T1 by design — this is pure scaffold. Lifecycle transitions, RBAC/
tenant-scoping rules, the matching algorithm, and assignment rules land here
in T2-T6, one module per domain area (e.g. ``services/auth.py``,
``services/missions.py``, ``services/matching.py``). Routes call into this
layer; this layer calls into ``models``. Never the other way around.
"""
