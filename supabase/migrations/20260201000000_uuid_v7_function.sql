-- ==============================================
-- UUID v7 Generation Function
-- Time-ordered UUIDs for better database performance
-- ==============================================

-- Drop old function if exists (for migrations)
DROP FUNCTION IF EXISTS uuid_generate_v7();
DROP FUNCTION IF EXISTS uuidv7();

-- Create UUID v7 generation function
-- Based on RFC 9562: https://datatracker.ietf.org/doc/rfc9562/
-- Implementation: https://gist.github.com/fabiolimace/515a0440e3e40efeb234e12644a6a346
CREATE OR REPLACE FUNCTION uuid_generate_v7(p_timestamp TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp())
RETURNS UUID AS $$
DECLARE
    v_time DOUBLE PRECISION := NULL;
    v_unix_t BIGINT := NULL;
    v_rand_a BIGINT := NULL;
    v_rand_b BIGINT := NULL;
    v_unix_t_hex VARCHAR := NULL;
    v_rand_a_hex VARCHAR := NULL;
    v_rand_b_hex VARCHAR := NULL;
    c_milli DOUBLE PRECISION := 10^3;  -- Millisecond precision
    c_micro DOUBLE PRECISION := 10^6;  -- Microsecond precision
    c_scale DOUBLE PRECISION := 4.096;
    c_version BIGINT := x'0000000000007000'::BIGINT;  -- Version 7
    c_variant BIGINT := x'8000000000000000'::BIGINT;  -- RFC 9562 variant
BEGIN
    -- Extract Unix epoch timestamp
    v_time := EXTRACT(EPOCH FROM p_timestamp);

    -- Unix timestamp in milliseconds
    v_unix_t := TRUNC(v_time * c_milli);

    -- Sub-millisecond precision for additional randomness
    v_rand_a := TRUNC((v_time * c_micro - v_unix_t * c_milli) * c_scale);

    -- Random component (62 bits)
    v_rand_b := TRUNC(random() * 2^30)::BIGINT << 32 | TRUNC(random() * 2^32)::BIGINT;

    -- Convert to hex and pad
    v_unix_t_hex := LPAD(TO_HEX(v_unix_t), 12, '0');
    v_rand_a_hex := LPAD(TO_HEX((v_rand_a | c_version)::BIGINT), 4, '0');
    v_rand_b_hex := LPAD(TO_HEX((v_rand_b | c_variant)::BIGINT), 16, '0');

    -- Combine and return as UUID
    RETURN (v_unix_t_hex || v_rand_a_hex || v_rand_b_hex)::UUID;
END $$ LANGUAGE plpgsql;

-- Grant execute permission to all roles
GRANT EXECUTE ON FUNCTION uuid_generate_v7 TO anon, authenticated, service_role;

-- Create alias for PostgreSQL 18+ compatibility
CREATE OR REPLACE FUNCTION uuidv7(p_timestamp TIMESTAMP WITH TIME ZONE DEFAULT clock_timestamp())
RETURNS UUID AS $$
BEGIN
    RETURN uuid_generate_v7(p_timestamp);
END $$ LANGUAGE plpgsql;

GRANT EXECUTE ON FUNCTION uuidv7 TO anon, authenticated, service_role;

-- ==============================================
-- BENEFITS OF UUID v7:
-- - 2-5x faster inserts than UUID v4
-- - 50% better index performance
-- - Time-ordered (sortable by creation time)
-- - 500x fewer B-tree page splits
-- - Better cache locality
-- - Easier debugging (timestamp visible)
-- ==============================================
