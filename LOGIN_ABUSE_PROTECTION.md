# Login abuse protection (Task 2.4)

## Inspected flow and scope

Previously the landing popup used `EmailOrUsernameAuthenticationForm`, account
login used Django's `LoginView`, and admin used `AdminAuthenticationForm`.
All relied on Django authentication and CSRF middleware but had no shared failed
login limit. This change wraps those three forms with one enforcement mixin:

| Endpoint | Authentication behavior |
| --- | --- |
| `/` POST | Existing username/email popup, Remember Me and dashboard redirect |
| `/accounts/login/` POST | Existing username login and safe `next` redirect handling |
| `/admin/login/` POST | Existing username login and active/staff requirements |

The default Django authentication backend, logout, session expiry, role access,
CSRF middleware and session-key rotation are unchanged. Password reset/change
routes are not login endpoints; reset-email abuse is outside this task.

## Policy and storage

Defaults: five failed attempts per normalized identifier/source pair within a
rolling 900-second window; 50 failed attempts across all identifiers from one
source. Reaching either limit starts a 900-second block. Denied requests do not
extend blocks. When the block expires the affected bucket starts a fresh budget.
Successful authentication clears the pair's failure budget, not the source's
budget, so a known password cannot reset password-spraying protection.

The existing popup resolves a recognized email to its username before the shared
limit, so that alias and username share a bucket. Bucket normalization casefolds
the identifier without changing Django's username authentication semantics.
Unknown identifiers receive the same errors and limits. There is no account-wide
block across sources: an attacker cannot lock a victim out from every IP.

Production uses **Redis**, selected automatically by `SCHED_EASE_ENV=production`.
Explicit production memory mode is rejected. No fallback is attempted when Redis
is absent, unreachable, misconfigured or fails during finalization: authentication
fails closed with a generic retry message and no authenticated session.
Deployment checks flag an absent/invalid Redis URL. No Redis server is installed
or provisioned by this change. The pinned `redis` Python client is the only new
dependency; Django's local-memory cache is not used as a production store.

Redis Lua operations serialize updates. A source-scoped, owner-token lease spans
password verification; only one attempt from that source is admitted at a time.
The lease expires after 60 seconds if a worker disappears. A late/stale worker
cannot finalize authentication after losing ownership. Concurrent callers are
asked to retry; they cannot race past the threshold. Server time determines the
rolling window, and all keys have TTLs. Keys share a source hash tag. The client
configuration targets a standalone Redis endpoint (not Redis Cluster/Sentinel
discovery); no cluster failover behavior is claimed.

Redis records contain HMAC identifiers, timestamps, random lease tokens and
block markers. No username, email, IP, password or session token is stored.
Workers must share the same stable Django secret and Redis instance/database.
Changing the secret changes bucket keys and resets effective limits.

Development defaults to a bounded, thread-safe **single-process memory store**.
It is not multi-worker protection and resets at restart. Use Redis for shared
development/staging deployments. The production mode cannot silently select it.

## Environment configuration

| Variable | Default / purpose |
| --- | --- |
| `SCHED_EASE_LOGIN_STORAGE` | `memory` in development; `redis` in production |
| `SCHED_EASE_LOGIN_REDIS_URL` | Required for Redis; private `redis://` or `rediss://` endpoint |
| `SCHED_EASE_LOGIN_MAX_FAILURES` | `5`, per identifier/source |
| `SCHED_EASE_LOGIN_SOURCE_MAX_FAILURES` | `50`, per source across identifiers |
| `SCHED_EASE_LOGIN_WINDOW_SECONDS` | `900`, rolling failure window |
| `SCHED_EASE_LOGIN_BLOCK_SECONDS` | `900`, temporary restriction |
| `SCHED_EASE_LOGIN_TRUSTED_PROXIES` | Empty; comma-separated IPs/CIDRs of trusted peers |

Numeric settings accept positive integers up to 86400. Production secrets and
Redis credentials belong in the service's private environment, never source
control. Connection/read timeouts are two seconds. Redis must be private, use
appropriate authentication/TLS, and permit EVAL/TIME/SET/GET/DEL/EXISTS/EXPIRE and
sorted-set operations. Dedicate capacity and use a no-eviction policy: eviction
or flushing can reset budgets. Persistence/restart/failover policy must be tested
with the hosting operator. Log/monitor failures without recording credentials.

## Client identification

Use the socket peer's `REMOTE_ADDR` by default. Ignore `X-Forwarded-For` entirely.
Only peers in the explicit login proxy allowlist may supply one valid `X-Real-IP`.
The proxy must strip incoming values and overwrite this header. Do not allow
untrusted clients to connect as a trusted proxy. Missing headers fall back to the
peer; malformed trusted-header values fail closed. IPv4-mapped IPv6 is normalized.
HTTPS proxy trust (`SCHED_EASE_TRUST_PROXY`) alone does not grant IP-header trust.

## User experience and privacy

Existing form error rendering shows a generic invalid-details or temporary
restriction/unavailability message. The landing popup remains open. Invalid,
inactive and unauthorized-admin accounts do not receive existence/status details.
Django's existing dummy password hashing for unknown usernames is retained;
lookup and password-hasher differences mean this is not a constant-time guarantee.
The authentication logger emits static accepted/rejected/restricted/unavailable
events only, without identifiers, submitted values, backend URLs or exceptions.

## Verification and limits

The focused run passed **61 tests** in 62.396 seconds: 27 new login-security
tests plus existing security-configuration and admin/publication tests. The
full suite passed **701 tests** in 561.504 seconds, exit code 0: all 674 existing
tests and 27 new tests, with no failures, errors, skips or expected failures.
System check, migration consistency, `git diff --check` and dependency
consistency checks passed; no migration was generated. A synthetic production
check correctly rejects an absent Redis URL with `schedease.E001`; with a valid
synthetic URL it reports only the existing HSTS warning. This check does not
connect to Redis. All four pre-existing root SQLite files retained identical
SHA-256 hashes across verification. No commits, pushes or deployment were made.
Local implementation/verification is complete; production readiness remains
conditional on the live Redis/proxy checks below. Tests use isolated
synthetic accounts and a fresh memory store, mocked clocks (no sleeps), storage
failure injection and Redis client contract mocks. The source-lease concurrency
test uses actual threads. No working database is migrated or seeded.

**Live Redis integration is a deployment gate:** no existing Redis executable
was found and infrastructure was not provisioned. Multi-process behavior, Lua
execution, Redis ACLs, TLS, outage recovery and production proxy topology still
need a staging check using the configured shared service. Contract mocks are not
a live Redis concurrency test.

Before enabling external access, use synthetic staging accounts to verify:

1. Five failures split across two workers/routes block the sixth attempt, even
   with new browser cookies; an independent source can still authenticate.
2. Controlled short test expiry permits login again; successful login preserves
   Remember Me, role redirects and session rotation.
3. Concurrent same-source requests admit only one password check; a terminated
   worker's lease expires and its stale completion cannot authenticate.
4. Redis outage or denied EVAL permission refuses login without leaking backend
   details. Recovery restores service; restart/failover preserves the agreed
   rate-limit state policy.
5. Trusted proxy headers are overwritten, untrusted headers are ignored, and
   real shared-NAT login volume is acceptable under the selected limits.

Other limitations: distributed attacks across many IPs, shared-NAT contention,
development process restarts, and direct trusted Python calls to `authenticate()`
outside the three HTTP forms. Add any future login endpoint to this shared form
policy. Network/edge request limits remain useful for malformed/empty submissions
and volumetric traffic; this feature counts actual failed authentication attempts.

References: [Django authentication](https://docs.djangoproject.com/en/5.2/topics/auth/default/),
[Redis atomic Lua execution](https://redis.io/docs/latest/develop/programmability/eval-intro/).
