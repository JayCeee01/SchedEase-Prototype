from .test_publication_helpers import finalize, legacy_case, upgrade
from copy import deepcopy
from datetime import time
import subprocess
import sys
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection, IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from .services.credential_approval import approve_override, approval_token
from .services.credentials import teaching_eligibility
from .services.conflicts import schedule_validation_messages


class CredentialScopeTests(SchedulingDefectFixture):
    def setUp(self):
        self.actor = User.objects.create_superuser('scope-admin', password='isolated-test')
        self.a = m.Credential.objects.create(name='A')
        self.requirement = m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=self.a)

    def approve(self, meeting=None, actor=None, token=None):
        actor = actor or self.actor
        return approve_override(actor=actor, assignment=meeting or self.meetings[0], faculty=self.faculty,
            subject=self.subject, reason='Explicit synthetic approval',
            scope_token=token or approval_token(actor, self.faculty, self.subject, self.term))

    def eligible(self):
        return teaching_eligibility(self.faculty, self.subject, self.term, self.meetings[0])['eligible']

    def schedule(self, finalized=False):
        schedule = m.Schedule.objects.create(term=self.term, name='Scoped approval test')
        for index, meeting in enumerate(self.meetings):
            schedule.entries.create(assignment=meeting, room=self.room, day=0,
                                    start_time=time(8+index), end_time=time(9+index))
        if finalized:
            finalize(schedule)
        return schedule

    def test_new_requirement_cannot_inherit_old_approval_and_reapproval_is_explicit(self):
        old = self.approve()
        frozen = deepcopy(old.scope_evidence.data)
        self.assertTrue(self.eligible())
        b = m.Credential.objects.create(name='B')
        m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=b)
        self.assertFalse(self.eligible())
        self.assertTrue(schedule_validation_messages(self.schedule()))
        new = self.approve()
        self.assertEqual(len(new.scope_evidence.data['requirements']), 2)
        self.assertTrue(self.eligible())
        old.scope_evidence.refresh_from_db()
        self.assertEqual(old.scope_evidence.data, frozen)

    def test_qualified_a_b_and_legacy_scope(self):
        legacy = m.CredentialOverride.objects.create(assignment=self.meetings[0], faculty=self.faculty,
            subject=self.subject, admin_user=self.actor, reason='Historical A', missing_credentials='A')
        self.assertFalse(self.eligible())
        b = m.Credential.objects.create(name='B')
        m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=b)
        m.FacultyCredential.objects.create(faculty=self.faculty, credential=self.a, issued_on=self.term.starts_on)
        self.assertFalse(self.eligible())
        approved = self.approve()
        self.assertEqual([x['required_credential_id'] for x in approved.scope_evidence.data['requirements']], [b.pk])
        self.assertTrue(self.eligible())
        m.FacultyCredential.objects.create(faculty=self.faculty, credential=b, issued_on=self.term.starts_on)
        result = teaching_eligibility(self.faculty, self.subject, self.term, self.meetings[0])
        self.assertTrue(result['qualified'] and result['eligible'])
        self.assertFalse(m.CredentialApprovalEvidence.objects.filter(override=legacy).exists())

    def test_changed_equivalence_and_definition_require_new_approval(self):
        self.approve()
        equivalent = m.Credential.objects.create(name='Equivalent')
        self.requirement.acceptable_equivalents.add(equivalent)
        self.assertFalse(self.eligible())
        self.approve()
        self.assertTrue(self.eligible())
        self.requirement.required_credential = equivalent
        self.requirement.save()
        self.assertFalse(self.eligible())

    def test_stale_or_other_user_confirmation_cannot_approve_new_requirements(self):
        token = approval_token(self.actor, self.faculty, self.subject, self.term)
        b = m.Credential.objects.create(name='B')
        m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=b)
        with self.assertRaises(ValidationError): self.approve(token=token)
        other = User.objects.create_superuser('other-admin', password='test')
        token = approval_token(self.actor, self.faculty, self.subject, self.term)
        with self.assertRaises(ValidationError): self.approve(actor=other, token=token)
        self.assertFalse(m.CredentialOverride.objects.exists())

    def test_unauthorized_attempt_and_atomic_rollback(self):
        user = User.objects.create_user('faculty', password='test')
        with self.assertRaises(ValidationError): self.approve(actor=user)
        with patch.object(m.CredentialApprovalEvidence, 'save', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError): self.approve()
        self.assertFalse(m.CredentialOverride.objects.exists())
        self.assertFalse(m.CredentialApprovalEvidence.objects.exists())

    def test_evidence_and_scoped_override_immutable_even_in_drafts(self):
        override = self.approve()
        evidence = override.scope_evidence
        with self.assertRaises(ValidationError): evidence.save()
        with self.assertRaises(ValidationError): override.save()
        for operation in (
            lambda: m.CredentialApprovalEvidence.objects.filter(pk=evidence.pk).update(data={}),
            lambda: m.CredentialApprovalEvidence.objects.filter(pk=evidence.pk).delete(),
            lambda: m.CredentialOverride.objects.filter(pk=override.pk).update(reason='Changed'),
            lambda: m.CredentialApprovalEvidence.objects.bulk_create([m.CredentialApprovalEvidence(override=override, data=evidence.data)]),
        ):
            with self.assertRaises(IntegrityError), transaction.atomic(): operation()
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('UPDATE schedules_credentialapprovalevidence SET schema_version=2 WHERE id=%s', [evidence.pk])

    @legacy_case
    def test_legacy_history_remains_unchanged_and_evidence_cannot_be_forged(self):
        legacy = m.CredentialOverride.objects.create(assignment=self.meetings[0], faculty=self.faculty,
            subject=self.subject, admin_user=self.actor, reason='Old exception', missing_credentials='A')
        before = m.CredentialOverride.objects.values().get(pk=legacy.pk)
        # Represents a schedule finalized before scope evidence was introduced.
        schedule = self.schedule()
        schedule.status='PUBLISHED'; schedule.save()
        upgrade()
        frozen = deepcopy(m.ScheduleSnapshot.objects.get(schedule=schedule).data)
        messages = list(schedule_validation_messages(schedule))
        self.assertTrue(messages)
        self.assertIn('Legacy free-text approvals do not establish that scope', str(messages))
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('INSERT INTO schedules_credentialapprovalevidence (override_id,schema_version,data,created_at) VALUES (%s,1,%s,CURRENT_TIMESTAMP)', [legacy.pk, '{}'])
        self.assertEqual(m.CredentialOverride.objects.values().get(pk=legacy.pk), before)
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=schedule).data, frozen)
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, 'PUBLISHED')

    def test_finalized_requirement_and_equivalence_guards_and_history(self):
        equivalent = m.Credential.objects.create(name='Equivalent')
        self.requirement.acceptable_equivalents.add(equivalent)
        for meeting in self.meetings: self.approve(meeting)
        schedule = self.schedule(finalized=True)
        history = deepcopy(m.ScheduleSnapshot.objects.get(schedule=schedule).data)
        b = m.Credential.objects.create(name='B')
        with self.assertRaises(ValidationError):
            m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=b)
        with self.assertRaises(ValidationError), transaction.atomic(): self.requirement.acceptable_equivalents.clear()
        with self.assertRaises(ValidationError), transaction.atomic(): self.requirement.acceptable_equivalents.add(b)
        through = m.SubjectCredentialRequirement.acceptable_equivalents.through
        for operation in (
            lambda: m.SubjectCredentialRequirement.objects.bulk_create([m.SubjectCredentialRequirement(subject=self.subject, required_credential=b)]),
            lambda: m.SubjectCredentialRequirement.objects.filter(pk=self.requirement.pk).update(required_credential=b),
            lambda: through.objects.bulk_create([through(subjectcredentialrequirement=self.requirement, credential=b)]),
        ):
            with self.assertRaises(IntegrityError), transaction.atomic(): operation()
        for sql in ('DELETE FROM schedules_subjectcredentialrequirement_acceptable_equivalents',
                    'DELETE FROM schedules_subjectcredentialrequirement',
                    'UPDATE schedules_subjectcredentialrequirement_acceptable_equivalents SET credential_id=%s'):
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, [b.pk] if '%s' in sql else [])
        self.assertEqual(list(schedule_validation_messages(schedule)), [])
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=schedule).data, history)

    def test_archived_guards_cover_replacement_and_old_and_new_relationships(self):
        equivalent = m.Credential.objects.create(name='Equivalent')
        self.requirement.acceptable_equivalents.add(equivalent)
        for meeting in self.meetings: self.approve(meeting)
        schedule = self.schedule(finalized=True)
        from .services.publication import publish
        publish(self.schedule(), self.actor, replace_confirmed=True)
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, 'ARCHIVED')
        other = m.Subject.objects.create(department=self.subject.department, code='OTHER', title='Other')
        other_requirement = m.SubjectCredentialRequirement.objects.create(subject=other, required_credential=equivalent)
        through = m.SubjectCredentialRequirement.acceptable_equivalents.through
        row = through.objects.get(subjectcredentialrequirement=self.requirement)
        for sql, params in (
            ('INSERT OR REPLACE INTO schedules_subjectcredentialrequirement (id,subject_id,required_credential_id,notes) VALUES (%s,%s,%s,%s)', [self.requirement.pk, other.pk, equivalent.pk, '']),
            ('UPDATE schedules_subjectcredentialrequirement SET subject_id=%s WHERE id=%s', [self.subject.pk, other_requirement.pk]),
            ('UPDATE schedules_subjectcredentialrequirement_acceptable_equivalents SET subjectcredentialrequirement_id=%s WHERE id=%s', [other_requirement.pk, row.pk]),
            ('INSERT OR REPLACE INTO schedules_subjectcredentialrequirement_acceptable_equivalents (id,subjectcredentialrequirement_id,credential_id) VALUES (%s,%s,%s)', [row.pk, other_requirement.pk, self.a.pk]),
        ):
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, params)
        with self.assertRaises(ValidationError), transaction.atomic():
            equivalent.equivalent_subject_requirements.clear()


class SHSScopeTests(TestCase):
    def test_scoped_approval_revalidates_shs_and_preserves_frozen_history(self):
        from .test_shs_generation import ControlledSHSGenerationTests
        from .test_contact_workload import ContactPolicyTests
        from .services.shs_scheduling import generate_shs
        from .services.publication import publish
        ControlledSHSGenerationTests.setUp(self)
        ContactPolicyTests.policy(self)
        schedule = generate_shs(self.term, self.settings, actor=self.actor, seed=17)
        entry = schedule.entries.get()
        credential = m.Credential.objects.create(name='Synthetic SHS license')
        m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=credential)
        self.assertTrue(schedule_validation_messages(schedule))
        approve_override(actor=self.actor, assignment=entry.assignment, faculty=self.faculty,
            subject=self.subject, reason='Synthetic explicit SHS exception',
            scope_token=approval_token(self.actor, self.faculty, self.subject, self.term))
        self.assertTrue(teaching_eligibility(self.faculty, self.subject, self.term, entry.assignment)['eligible'])
        # Existing SHS operational approval independently requires qualification.
        # A meeting-scoped exception must not bypass that stricter policy.
        self.assertTrue(list(schedule_validation_messages(schedule)))
        with self.assertRaises(ValidationError):
            publish(schedule, self.actor)
        m.FacultyCredential.objects.create(faculty=self.faculty, credential=credential, issued_on=self.term.starts_on)
        self.assertEqual(list(schedule_validation_messages(schedule)), [])
        binding = deepcopy(entry.assignment.shs_binding.data)
        published, _ = publish(schedule, self.actor)
        snapshot = deepcopy(m.ScheduleSnapshot.objects.get(schedule=published).data)
        with self.assertRaises(ValidationError):
            m.SubjectCredentialRequirement.objects.create(subject=self.subject,
                required_credential=m.Credential.objects.create(name='New SHS requirement'))
        entry.assignment.shs_binding.refresh_from_db()
        self.assertEqual(entry.assignment.shs_binding.data, binding)
        self.assertEqual(m.ScheduleSnapshot.objects.get(schedule=published).data, snapshot)


class ScopeMigrationTests(SimpleTestCase):
    def test_legacy_preserved_no_backfill_forward_reverse(self):
        script = r'''
import os
os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
import django
django.setup()
from django.core.management import call_command
from django.db import connection
from schedules.test_credential_scope import CredentialScopeTests
from schedules import models as m
from schedules.services.credential_approval import approve_override, approval_token
call_command('migrate','auth',verbosity=0)
call_command('migrate','schedules','0028',verbosity=0)
f=CredentialScopeTests()
f.setUpTestData()
f.setUp()
legacy=m.CredentialOverride.objects.create(assignment=f.meetings[0],faculty=f.faculty,subject=f.subject,admin_user=f.actor,reason='Legacy',missing_credentials='A')
before=list(m.CredentialOverride.objects.values())
f.schedule(finalized=True)
history=list(m.ScheduleSnapshot.objects.values())
schedules=list(m.Schedule.objects.values())
entries=list(m.ScheduleEntry.objects.values())
f.term=m.AcademicTerm.objects.create(name='Future approval term',school_year=f.term.school_year,
    starts_on=f.term.starts_on,ends_on=f.term.ends_on)
draft_meeting=m.TeachingAssignment.objects.create(term=f.term,subject=f.subject,faculty=f.faculty,
    section=f.section,component='LECTURE',meeting_index=3,duration_minutes=60)
call_command('migrate','schedules','0029',verbosity=0)
assert list(m.CredentialOverride.objects.values())==before
assert not m.CredentialApprovalEvidence.objects.exists()
assert list(m.ScheduleSnapshot.objects.values())==history
assert list(m.Schedule.objects.values())==schedules
assert list(m.ScheduleEntry.objects.values())==entries
call_command('migrate','schedules','0028',verbosity=0)
assert list(m.CredentialOverride.objects.values())==before
assert list(m.ScheduleSnapshot.objects.values())==history
call_command('migrate','schedules','0029',verbosity=0)
f.approve(meeting=draft_meeting)
try:
    call_command('migrate','schedules','0028',verbosity=0)
except RuntimeError as exc:
    assert 'evidence exists' in str(exc)
else:
    raise AssertionError('Must not delete populated approval evidence during reversal')
assert m.CredentialApprovalEvidence.objects.count()==1
with connection.cursor() as c:
    c.execute('PRAGMA integrity_check')
    assert c.fetchall()==[('ok',)]
    c.execute('PRAGMA foreign_key_check')
    assert c.fetchall()==[]
'''
        result = subprocess.run([sys.executable, '-B', '-c', script], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
