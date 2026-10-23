"""Rolling failed-login limits. Redis is required in production; memory is dev-only.

One expiring source lease spans password verification. Atomic finish checks its
owner before recording failures or permitting a successful login. Redis TIME is
authoritative; clients never supply timestamps. No credentials are stored.
"""
import hashlib
import hmac
import ipaddress
import logging
from threading import RLock
from time import monotonic
from uuid import uuid4

from django.conf import settings

logger = logging.getLogger('schedease.authentication')
BUSY = 'Too many sign-in attempts. Please wait a few minutes and try again.'
UNAVAILABLE = 'Sign-in is temporarily unavailable. Please try again shortly.'
LEASE_SECONDS = 60


class Restricted(Exception):
    pass


def client_source(request):
    peer = ipaddress.ip_address(request.META.get('REMOTE_ADDR', '127.0.0.1'))
    if any(peer in ipaddress.ip_network(net) for net in settings.LOGIN_TRUSTED_PROXIES):
        # Only a single, overwritten X-Real-IP from an explicitly trusted peer.
        forwarded = request.META.get('HTTP_X_REAL_IP')
        if forwarded:
            peer = ipaddress.ip_address(forwarded)
    return str(getattr(peer, 'ipv4_mapped', None) or peer)


def key_parts(request, identifier):
    def digest(value):
        return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()
    return digest(client_source(request)), digest(identifier.casefold())


# KEYS: source lease, source failures, source block, pair failures, pair block.
# Every key shares a source hash tag, so the operation also fits one cluster slot.
SCRIPT = '''
local clock = redis.call('TIME')
local now = tonumber(clock[1]) + tonumber(clock[2]) / 1000000
local window = tonumber(ARGV[3])
local block = tonumber(ARGV[4])
if ARGV[1] == 'begin' then
    if redis.call('EXISTS', KEYS[3]) == 1 or redis.call('EXISTS', KEYS[5]) == 1 then return 0 end
    if not redis.call('SET', KEYS[1], ARGV[2], 'NX', 'EX', 60) then return 0 end
    return 1
end
if redis.call('GET', KEYS[1]) ~= ARGV[2] then return -1 end
if ARGV[1] == 'success' then
    redis.call('DEL', KEYS[4], KEYS[5])
else
    for _, index in ipairs({2, 4}) do
        redis.call('ZREMRANGEBYSCORE', KEYS[index], '-inf', now - window)
        redis.call('ZADD', KEYS[index], now, ARGV[2])
        redis.call('EXPIRE', KEYS[index], math.max(window, block))
        local threshold = tonumber(ARGV[index == 2 and 6 or 5])
        if redis.call('ZCARD', KEYS[index]) >= threshold then
            redis.call('SET', KEYS[index+1], '1', 'EX', block)
            redis.call('DEL', KEYS[index])
        end
    end
end
redis.call('DEL', KEYS[1])
return 1
'''


class RedisStore:
    def __init__(self):
        from redis import Redis
        if not settings.LOGIN_REDIS_URL:
            raise RuntimeError('Login storage not configured')
        self.client = Redis.from_url(settings.LOGIN_REDIS_URL, socket_timeout=2,
                                     socket_connect_timeout=2, decode_responses=True)

    def operation(self, action, source, pair, token):
        base = 'schedease:login:v1:{' + source + '}:'
        keys = [base + 'lease', base + 'fail', base + 'block', base + pair + ':fail', base + pair + ':block']
        result = self.client.eval(SCRIPT, 5, *keys, action, token, settings.LOGIN_WINDOW_SECONDS,
                                  settings.LOGIN_BLOCK_SECONDS, settings.LOGIN_MAX_FAILURES,
                                  settings.LOGIN_SOURCE_MAX_FAILURES)
        if result == 0:
            raise Restricted(BUSY)
        if result != 1:
            raise RuntimeError('Login lease lost')


class MemoryStore:
    """Single-process development equivalent, deliberately not a production cache."""
    def __init__(self):
        self.lock = RLock()
        self.leases, self.failures, self.blocks = {}, {}, {}

    def operation(self, action, source, pair, token):
        with self.lock:
            now = monotonic()
            self.leases = {k: v for k, v in self.leases.items() if v[1] > now}
            self.blocks = {k: v for k, v in self.blocks.items() if v > now}
            self.failures = {k: [t for t in v if t > now - settings.LOGIN_WINDOW_SECONDS]
                             for k, v in self.failures.items() if any(t > now - settings.LOGIN_WINDOW_SECONDS for t in v)}
            keys = [source, (source, pair)]
            if action == 'begin':
                if source in self.leases or any(k in self.blocks for k in keys):
                    raise Restricted(BUSY)
                if len(self.failures) + len(self.blocks) + len(self.leases) >= 10000:
                    raise RuntimeError('Development limiter capacity reached')
                self.leases[source] = (token, now + LEASE_SECONDS)
                return
            if self.leases.get(source, (None,))[0] != token:
                raise RuntimeError('Login lease lost')
            if action == 'success':
                self.failures.pop(keys[1], None)
                self.blocks.pop(keys[1], None)
            else:
                for key, maximum in zip(keys, [settings.LOGIN_SOURCE_MAX_FAILURES, settings.LOGIN_MAX_FAILURES]):
                    values = self.failures.setdefault(key, [])
                    values.append(now)
                    if len(values) >= maximum:
                        self.blocks[key] = now + settings.LOGIN_BLOCK_SECONDS
                        del self.failures[key]
            del self.leases[source]


_memory = MemoryStore()


def get_store():
    if settings.LOGIN_STORAGE == 'redis':
        return RedisStore()
    if settings.LOGIN_STORAGE == 'memory' and settings.LOGIN_MEMORY_ALLOWED:
        return _memory
    raise RuntimeError('Unsafe login storage configuration')


def begin(request, identifier):
    try:
        source, pair = key_parts(request, identifier)
        store, token = get_store(), uuid4().hex
        store.operation('begin', source, pair, token)
        return store, source, pair, token
    except Restricted:
        logger.warning('Login temporarily restricted')
        raise
    except Exception:
        logger.error('Login protection unavailable')
        raise Restricted(UNAVAILABLE) from None


def finish(ticket, success):
    store, source, pair, token = ticket
    try:
        store.operation('success' if success else 'failure', source, pair, token)
    except Exception:
        logger.error('Login protection completion failed')
        raise Restricted(UNAVAILABLE) from None
    logger.info('Login accepted' if success else 'Login rejected')
