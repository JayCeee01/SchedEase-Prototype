"""Database leases with cooperative renewal and transaction-scoped write fencing."""
import logging
from contextlib import contextmanager
from datetime import timedelta
from time import monotonic
from uuid import uuid4

from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Q
from django.db.models.functions import Now

from schedules.models import GenerationLease

logger = logging.getLogger(__name__)
LEASE_SECONDS = 120


class GenerationBusy(Exception):
    pass


class GenerationLeaseLost(Exception):
    pass


class Lease:
    def __init__(self, term_id, owner, seconds=LEASE_SECONDS):
        self.term_id, self.owner, self.seconds = term_id, owner, seconds
        self.next_renewal = monotonic() + seconds / 3
        self.run_id = None

    def owned(self):
        return GenerationLease.objects.filter(term_id=self.term_id, owner=self.owner, expires_at__gt=Now())

    def checkpoint(self, *, force=False):
        if not force and monotonic() < self.next_renewal:
            return
        try:
            changed = self.owned().update(expires_at=Now() + timedelta(seconds=self.seconds))
        except OperationalError as exc:
            raise GenerationLeaseLost('Generation could not safely renew its reservation. Please try again.') from exc
        if changed != 1:
            raise GenerationLeaseLost('This generation reservation expired or was replaced. Please try again.')
        self.next_renewal = monotonic() + self.seconds / 3

    @contextmanager
    def saving(self):
        # The first operation is a conditional write, before reading schedule data.
        # It holds the lease row (SQLite: writer lock) through validation and commit.
        # An expired/replaced owner cannot renew or pass this fence.
        with transaction.atomic():
            self.checkpoint(force=True)
            yield

    def release(self):
        try:
            return GenerationLease.objects.filter(term_id=self.term_id, owner=self.owner).update(
                owner=None, expires_at=None)
        except OperationalError:
            # A busy database must not mask the original failure; expiry allows
            # recovery. The token condition prevents releasing a successor.
            logger.warning('Generation reservation cleanup deferred to expiry for term %s', self.term_id)
            return 0


def acquire(term_id, *, seconds=LEASE_SECONDS):
    if seconds <= 0:
        raise ValueError('Generation lease duration must be positive.')
    owner = uuid4()
    try:
        changed = GenerationLease.objects.filter(term_id=term_id).filter(
            Q(owner__isnull=True) | Q(expires_at__lte=Now())).update(
                owner=owner, expires_at=Now() + timedelta(seconds=seconds))
        if not changed:
            try:
                # The primary key arbitrates a race to create the first lease.
                with transaction.atomic():
                    GenerationLease.objects.create(term_id=term_id, owner=owner,
                        expires_at=Now() + timedelta(seconds=seconds))
            except IntegrityError as exc:
                raise GenerationBusy('A schedule is already being generated for this term. Please wait for it to finish.') from exc
    except OperationalError as exc:
        raise GenerationBusy('Generation is busy. Please wait a moment and try again.') from exc
    return Lease(term_id, owner, seconds)


@contextmanager
def generation_lease(term_id):
    lease = acquire(term_id)
    try:
        yield lease
    finally:
        lease.release()
