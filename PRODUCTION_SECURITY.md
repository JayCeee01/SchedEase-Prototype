# Production security preparation (Task 8.1)

## Dependency baseline update

The current dependency pin is Django 5.2.18 LTS on Python 3.12. See
[the isolated upgrade report](DJANGO_52_UPGRADE.md) for verification and limitations.
The Django 5.0.6 references below describe the original Task 8.1 audit.
This dependency upgrade does not certify hosting, HTTPS, backups, or production readiness.

## Initial audit

The starting working tree was clean. The existing Python 3.12.10 / Django 5.0.6 baseline and Phases 1–7 are preserved.

- `sched_ease/settings.py` loaded dotenv for every startup, defaulted DEBUG to true, accepted an insecure development secret fallback, and parsed hosts without production validation. No production mode existed.
- SecurityMiddleware was first; session, CSRF, authentication and clickjacking middleware and all four Django password validators were present. Preserve their order and behavior.
- HTTPS redirects, secure cookies, proxy trust and HSTS were not configured. Django's defaults supplied HttpOnly session cookies, SameSite=Lax, nosniff, same-origin referrer policy and DENY framing.
- Static source and collection directories were already separate. No public media route was found. Imports and exports use application views rather than public static storage.
- `.env` exists locally and is ignored; it was not printed or modified. Tracked-file pattern inspection found test/demo credentials, documented sample accounts and development placeholders, not an identified live production secret. This is not a complete Git-history or external-secret audit. Never deploy sample accounts; treat any development key reused elsewhere as exposed and arrange rotation separately.
- WSGI and manage.py use `sched_ease.settings`; no ASGI module exists. SQLite is the only configured database backend. No hosting provider, domain, TLS termination or production server is selected.
- Django 5.0 is unsupported. A supported-version upgrade and dependency security review remain prerequisites to a live deployment, as already noted in README. This task does not upgrade dependencies or claim the application is ready to expose publicly.

## Development and production selection

Continue local development with the existing `.venv` and `python manage.py runserver`. The default mode is `development`; the project-root `.env` loads without overriding process variables. Local HTTP, localhost hosts, SQLite and development debugging remain available. Boolean settings now accept only `true` or `false` (case-insensitive); typos fail with a configuration error.

For production, explicitly set **`SCHED_EASE_ENV=production` in the worker/service environment before Python starts**. `manage.py` and WSGI still use `sched_ease.settings`; no alternate settings module is needed. This mode skips local dotenv loading and requires a production secret and explicit hosts. Missing DEBUG defaults to false; setting it true fails startup. An unknown environment mode also fails. Configuration cannot determine whether a machine is publicly hosted: selecting production for every worker and management command is an operator responsibility.

Do not point a production process at a developer's `.env`. `.env.example` is a development example with commented production placeholders. `.env` and `.env.*` are ignored except `.env.example`. Never put actual production configuration in source control or command history.

## Environment variables

| Variable | Production behavior |
|---|---|
| `SCHED_EASE_ENV` | Required operational selection: `production`. Default is `development` for existing local commands. |
| `SCHED_EASE_DEBUG` | Omit or set `false`. `true` and invalid Boolean values fail startup. |
| `SCHED_EASE_SECRET_KEY` | Required private, random, stable key: at least 50 characters, at least five distinct characters, no whitespace or recognized development placeholders. No legacy `SECRET_KEY` fallback in production. These checks cannot prove entropy; use a secure generator in your private secret-management process. |
| `SCHED_EASE_ALLOWED_HOSTS` | Required comma-separated exact hostnames or IPs. No schemes, ports, paths, empty items, leading-dot subdomain patterns or wildcards. Bracket IPv6 literals. |
| `SCHED_EASE_CSRF_TRUSTED_ORIGINS` | Optional; empty by default. Exact HTTPS origins with optional port, no path/trailing slash, credentials or wildcards. Only add origins authorized to submit forms. |
| `SCHED_EASE_TRUST_PROXY` | `false` by default. Set `true` only after the proxy prerequisites below are met; enables `HTTP_X_FORWARDED_PROTO=https`. |
| `SCHED_EASE_HSTS_SECONDS` | Integer 0–31536000; default 0 until HTTPS is verified. Start with 300 after verification. Local development always disables HSTS. |
| `SCHED_EASE_DATABASE_URL` | Existing SQLite URL configuration remains, default `sqlite:///db.sqlite3`. Legacy `DATABASE_URL` behavior is unchanged. No backend migration is performed. |

HTTPS redirects and secure cookies are mandatory in production mode; there is deliberately no environment switch to disable them. Subdomain HSTS and preload remain false. Hosts/origins and errors are validated without echoing their supplied values; secrets are never printed by configuration validation.

## Secrets, hosts and origins

Supply a stable secret from your deployment platform's protected environment mechanism. Do not generate it each startup: changing it invalidates signed data and sessions. Do not reuse example, test, sample or development keys. Plan any future rotation separately with backup and session/signature implications understood. No real secret was generated, rotated or changed in this task.

Use the actual public hostname in ALLOWED_HOSTS when it is assigned. Configure the front server to reject unexpected Host headers as well. Do not trust forwarded host headers: `USE_X_FORWARDED_HOST` remains false.

Same-origin HTTPS forms do not require CSRF_TRUSTED_ORIGINS entries. A reverse proxy alone is not a reason to broaden trust: preserve the intended Host and correct secure-request indication. Add a separate origin only when a genuine authorized cross-origin form workflow requires it. This setting does not enable CORS or grant authentication/role permissions.

## HTTPS and reverse proxy prerequisites

Two supported arrangements are:

1. A production application server receives TLS directly and provides the correct WSGI HTTPS scheme. Leave proxy trust false.
2. A trusted edge proxy terminates TLS and forwards to a private application server. Before enabling proxy trust, restrict backend access to that proxy, remove client-supplied forwarded-protocol headers, and set a single `X-Forwarded-Proto` value from the actual connection scheme. Preserve/validate Host. Never append an untrusted client value or expose the backend directly.

Django cannot authenticate the sender of this header. Setting TRUST_PROXY=true is an assertion about infrastructure, not an IP allowlist. Incorrect scheme forwarding can cause redirect loops; test HTTP-to-HTTPS redirection and HTTPS login on the real architecture before accepting traffic. An arbitrary client's forwarded-protocol header is ignored in the default configuration. No redirect exemptions are configured.

Use an appropriate production WSGI server selected for the eventual platform. `runserver` is for development. No server package, DNS, certificate or live hosting configuration is installed by Task 8.1.

## Cookies, headers and error reporting

Production session and CSRF cookies use Secure, HttpOnly and SameSite=Lax. Session expiry behavior is unchanged. Existing form tokens work with HttpOnly CSRF cookies: `static/js/app.js` reads the hidden form token for draft autosave rather than reading the cookie. All existing security/session/authentication/CSRF middleware and password validators remain enabled.

Nosniff, DENY framing and same-origin referrer policy are explicit. DEBUG=false uses generic error responses; tests verify that an exception sentinel, traceback and configuration names do not appear in an HTTP 500 response. Application diagnostics remain governed by existing administrator permissions.

Existing server-side exception logging remains intact for troubleshooting; DEBUG=false does not sanitize private server logs. Restrict log access and retention, do not publish logs as assets, and configure approved monitoring to redact credentials, cookies, request bodies and academic data. Do not enable verbose request-body/environment logging. No logging SaaS, email credentials or external reporting is configured. Hosted logging controls require deployment-specific review; the tests do not certify every exception message as free of sensitive content.

## HSTS rollout

Leave HSTS at zero during preparation. Once HTTPS works across the actual site, enable 300 seconds and verify the `Strict-Transport-Security` response header over HTTPS. Observe redirects, login, assets and renewal behavior before gradually increasing the duration. HSTS persists in browsers; do not enable long durations as a substitute for verifying TLS.

`SECURE_HSTS_INCLUDE_SUBDOMAINS` and `SECURE_HSTS_PRELOAD` stay false. No assumption is made that every subdomain supports HTTPS, and no preload submission is performed. Any future change requires a separate review of all subdomains, certificate coverage and rollback implications.

## Static files and private data

`STATIC_URL`, `STATICFILES_DIRS` (`static/`) and `STATIC_ROOT` (`staticfiles/`) are unchanged. Run `python manage.py collectstatic --noinput` in a controlled release workspace, then serve **only the collection directory** at the static URL through the chosen front server or asset service. Do not expose the repository root, `.env`, database, logs or private imports. No extra static-serving dependency is needed for collection.

There is no configured public media endpoint. Academic import payloads are stored in owner-bound database records; exports are generated by existing access-controlled application views. Preserve these routes and permissions instead of copying exports or uploads into public static folders. Protect any platform temporary-upload directory and its cleanup separately.

Verification used a new isolated collection directory and removed it afterward; production assets were not touched. Python's restrictive Windows temporary-directory permissions initially prevented access in the sandbox. Collection was rerun successfully using an ordinary isolated workspace directory, and the empty failed temporary directories were removed.

## Database and deployment preparation

SQLite development behavior, transaction handling, leases, snapshots and academic data are unchanged. The current settings support SQLite URLs only. A production database choice requires workload/concurrency testing, backups, restore drills, file permissions and an explicit migration plan. Do not assume switching ORM backends preserves SQLite-specific protection mechanisms without verification. No database migration or data change was performed.

Before a future deployment:

1. Keep the Django 5.2 LTS patch current and review the complete pinned dependency set for security advisories before release. See `DJANGO_52_UPGRADE.md`; dependency compatibility alone does not establish production readiness.
2. Choose a host, domain, production WSGI server, TLS arrangement, private backend boundary and protected secret injection mechanism.
3. Inject the production variables into each worker and management-command environment. Do not use sample accounts or run demo seed commands on production data.
4. Prepare backups and the database plan separately; review filesystem and log access.
5. Run deployment checks and collect static files in the release workspace. Resolve any new warnings rather than silencing them.
6. Verify real HTTPS, redirects, allowed hosts, login/logout, role permissions, CSRF, private exports and static delivery before exposure. Enable short-lived HSTS only after these checks.

### PowerShell checks

In a dedicated shell with the secret and actual allowed hosts already injected privately by your deployment mechanism:

```powershell
$env:SCHED_EASE_ENV = 'production'
$env:SCHED_EASE_DEBUG = 'false'
python manage.py check --deploy
# After HTTPS has been verified on the eventual host:
$env:SCHED_EASE_HSTS_SECONDS = '300'
python manage.py check --deploy
```

Close that shell when finished; use a normal development shell for local tests/runserver. Do not paste production secrets into terminal history. Missing required variables intentionally prevent these commands from starting. `.env.example` contains placeholders only and is not an executable production deployment recipe.

## Regression tests and verification

`schedules/test_security_settings.py` adds 17 isolated tests: missing/invalid secrets without legacy fallback, no secret disclosure, mode/Boolean parsing, hosts, origins, HSTS boundaries, secure defaults, HTTP redirects, default rejection of spoofed scheme headers, explicit proxy trust, private error responses, development HTTP, production startup without dotenv, HTTPS cookies/login/logout across all three roles, and CSRF rejection of missing tokens and unapproved origins. Tests use public fixtures and child-process environment copies; they do not modify the developer's `.env` or persistent environment.

| Check | Result |
|---|---|
| `python manage.py test schedules.test_security_settings --noinput` | 17 passed, 0 failures/errors/skips/expected failures. |
| `python manage.py test --noinput` | All 513 passed in 286.783 seconds: 496 existing + 17 new; 0 failures/errors, skipped, expected failures or unexpected successes. |
| `python manage.py check` | Passed, no issues. |
| `python manage.py makemigrations --check --dry-run` | Passed, no changes detected. |
| Production `python manage.py check --deploy`, HSTS=0 | Exit 0, warning W004: HSTS not yet enabled. |
| Production `python manage.py check --deploy`, HSTS=300 | Exit 0, warnings W005 and W021: subdomains/preload intentionally not enabled. |
| Isolated production `collectstatic --noinput` | 131 files collected; app CSS/JS present; no `.env`, database or private-key files found in the collected assets. |
| `git diff --check` | Passed; only Git's Windows LF-to-CRLF notice for README. New untracked files also passed a separate whitespace/conflict-marker check. |
| `python -m pip check` | Passed; no broken requirements. |

No warnings are suppressed. W004 awaits verified live HTTPS; W005/W021 require subdomain/preload decisions that cannot be made without hosting information. All deployment checks used temporary public fixture values in subprocesses, not real secrets. Passing checks does not prove a live server is secure. Live TLS/proxy configuration, monitoring and database readiness remain unverified because no deployment was performed.

Task 8.1's configuration-preparation acceptance criteria are complete. No application scheduling behavior, migrations, dependencies or existing environment files changed. No commits or deployment were performed; Task 8.2 has not begun.

## Reference guidance

- [Django deployment checklist](https://docs.djangoproject.com/en/5.0/howto/deployment/checklist/): production settings and release preparation.
- [Django proxy SSL header setting](https://docs.djangoproject.com/en/5.0/ref/settings/#secure-proxy-ssl-header): infrastructure trust prerequisites.
- [Django supported versions](https://www.djangoproject.com/download/#supported-versions): the existing Django 5.0 baseline is unsupported and must be upgraded before live deployment.
