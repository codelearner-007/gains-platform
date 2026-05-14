"""Background jobs for the Gains pipeline.

Phase 1: ingest_schoology — reads scraper CSVs from local FS or Azure Blob,
melts wide CSVs to long format, INSERTs into raw_* tables.

Phase 7+ (future): sync_users, sync_tenant_config.
"""
