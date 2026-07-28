/**
 * Cookie marking a Schoology-embedded (iframe / LTI) session.
 *
 * Write-once / read-in-two-places contract, so it lives in one place:
 *   - WRITER:  the LTI bridge sets it   (app/api/lti/bridge/route.ts)
 *   - READER:  the middleware preserves the partitioned SameSite=None; Secure
 *              session-cookie transport off it  (lib/supabase/middleware.ts)
 *   - READER:  getIsFramed() renders the chrome-less shell + suppresses cookie
 *              consent off it  (lib/server/me.ts)
 *
 * httpOnly (server-only) — deliberately NOT readable from client JS. Edge-safe:
 * keep this module import-free so the middleware can pull it in.
 */
export const GAINS_FRAMED_COOKIE = 'gains-framed';
