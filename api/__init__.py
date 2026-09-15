"""Thin route handlers (the top of the api -> services -> models layering).

Routes stay thin: parse/validate input, call into ``services``, translate the
result to an HTTP response. No domain logic lives here.
"""
