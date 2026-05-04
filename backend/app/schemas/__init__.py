"""Pydantic schemas for request/response validation.

Organized into:
- schemas/request/  -- Input validation (POST/PUT/PATCH bodies)
- schemas/response/  -- Output serialization (response_model)
- schemas/common.py  -- Shared base schemas (timestamps, pagination, errors)
- schemas/auth.py    -- JWT claims and current user (used in dependencies)
"""
