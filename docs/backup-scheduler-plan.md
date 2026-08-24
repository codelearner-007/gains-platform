# Daily Database Backup — Simple Plan

## What we're building

A small robot that runs once a day, automatically, with no one touching it:

1. It connects to our database and makes a full backup copy.
2. It uploads that backup to Cloudflare (a cloud storage locker, called R2).
3. It sends us an email saying "backup done" — or, if anything went wrong, an email explaining exactly what broke.

## Where it lives

A new folder in the project, called `backup`, sitting right next to the existing `scraper` folder. It's written in Python — the same language the `backend` service already uses — following the same conventions (structured logging, config via environment variables, `requirements.txt`) rather than `scraper`'s Node.js style.

## What happens every day, step by step

1. **Wake up.** A scheduler (built into our hosting platform, Railway) starts the job automatically at a set time every day. We don't run our own clock/timer — we use the one Railway already provides.
2. **Make the backup.** The job connects to the database and asks it to export everything into one backup file.
3. **Hold it briefly.** That file is written to a temporary spot on the same machine running the job — it's never saved anywhere permanent, and it's automatically wiped when the job finishes, whether it succeeded or failed. Caveat: the machine needs enough temporary disk space to hold the whole backup file at once — worth confirming the backup's typical size before we go live, so we know that's not a problem.
4. **Upload it.** That temporary file gets uploaded to our Cloudflare storage bucket, into a dated folder (e.g. `backups/2026-08-23/`).
5. **Clean up old backups.** After every backup that succeeds, the job automatically deletes the oldest backup(s) in Cloudflare so only the last 3 stay in the bucket — storage never piles up or costs more over time. If a backup fails, nothing gets deleted (there's nothing to safely clean up until we know a new one actually landed).
6. **Send the email.** Whether the backup succeeded or failed, an email goes out immediately:
   - **Success email:** confirms it worked, how big the backup was, how long it took.
   - **Failure email:** says exactly what failed and why (e.g. "couldn't connect to the database" or "upload to Cloudflare failed"), so it can be fixed quickly instead of silently going unnoticed.
   - Every email — success, failure, or dry-run — always states how many backups are being kept (the limit) alongside whether one was actually deleted this run.
7. **Done.** The job shuts itself off until tomorrow.

## What we need to set up (one-time)

- A Cloudflare account + storage bucket + an access key for it.
- A Resend account (for sending the emails) + an API key + a verified "from" email address.
- The database's connection details (already have this).
- A list of who should receive the backup emails.

All of these are stored as secret settings on Railway — never written into the code itself.

## What could go wrong (and how we're handling it)

- **If the backup step fails** → email sent immediately explaining why. No silent failures.
- **If the upload step fails** → same — an email goes out either way, success or failure.
- **If backups pile up** → the job itself deletes the oldest ones after every successful run, keeping only the last 3, so storage cost stays basically free — this isn't left to an R2 dashboard setting.
- **If yesterday's job is still stuck running when today's is due** → today's run gets skipped rather than running two at once and colliding. (Something to keep an eye on — a stuck job could mean a missed day.)

## What's NOT being built (on purpose)

- No custom scheduler code — we lean on Railway's built-in daily-trigger feature instead of writing our own timer.
- No attaching the actual backup file to the email — email systems have small size limits and backups can be large. The email just reports what happened; the real file lives safely in Cloudflare.

## Next step

If this looks right, the next step is a short technical implementation plan (which files get created, in what order) — no code gets written until that's approved too.
