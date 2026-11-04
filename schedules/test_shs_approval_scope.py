from .test_publication_helpers import finalize
"""Immutable SHS approval context and independent finalized dependency guards."""
from copy import deepcopy
from datetime import date
from importlib import import_module
from io import StringIO
import json
import subprocess
import sys
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.db import connection, IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, SimpleTestCase

from . import models as m
from .protection import archive_transition
from .services import shs_approval as approval
from .services.shs_scheduling import generate_shs, assert_prepared
from .services.publication import publish
from .test_replacement_protection import replace_copy


def fixture(owner, finalized=True):
    from .test_shs_generation import ControlledSHSGenerationTests
    from .test_contact_workload import ContactPolicyTests
    ControlledSHSGenerationTests.setUp(owner)
    owner.policy=ContactPolicyTests.policy(owner)
    owner.schedule=generate_shs(owner.term,owner.settings,actor=owner.actor,seed=17)
    if finalized: owner.schedule,_=publish(owner.schedule,owner.actor)
    owner.evidence=m.SHSApprovalEvidence.objects.get(term=owner.term)
    owner.frozen=list(m.ScheduleSnapshot.objects.values())
    owner.bindings=list(m.SHSMeetingBinding.objects.values())


class SHSScopeTests(TestCase):
    def setUp(self): fixture(self)

    def intact(self):
        self.assertEqual(list(m.ScheduleSnapshot.objects.values()),self.frozen)
        self.assertEqual(list(m.SHSMeetingBinding.objects.values()),self.bindings)
        connection.check_constraints()

    def legacy(self):
        # Simulate an earlier-schema database, never alter real historical data.
        with connection.cursor() as c:
            c.execute('DROP TRIGGER shs_scope_delete')
            c.execute('DELETE FROM schedules_shsapprovalevidence')
            c.execute(approval.policy.TRIGGERS['shs_scope_delete'])

    def test_preparation_evidence_contains_authority_and_exact_definitions(self):
        data=self.evidence.data
        self.assertEqual(self.evidence.kind,'PREPARATION')
        self.assertEqual(self.evidence.actor,self.actor)
        self.assertEqual(data['authority']['user_id'],self.actor.pk)
        self.assertEqual(data['reviewed_at'],self.evidence.created_at.isoformat())
        records={(r['model'],r['id']):r['definition'] for r in data['records']}
        self.assertEqual(records[('facultycontactminutepolicy',self.policy.pk)]['maximum_contact_minutes'],120)
        self.assertEqual(records[('deliverycomponent',self.component.pk)]['duration_minutes'],60)
        self.assertEqual(records[('curriculumsubjectrequirement',self.requirement.pk)]['curriculum_version_id'],self.requirement.curriculum_version_id)
        self.assertEqual(data['bindings'][0]['data'],self.bindings[0]['data'])
        self.assertEqual(len(data['weekly_minutes']),2)
        assert_prepared(self.term)

    def test_critical_edits_model_and_bulk(self):
        records=[(self.config,'is_confirmed',False),(self.plan,'is_approved',False),
            (self.requirement.curriculum_version,'is_active',False),(self.requirement,'is_active',False),
            (self.plan.offering,'is_approved',False),(self.component,'duration_minutes',61),
            (self.config.patterns.get(),'room_approval_reference','Changed approval'),
            (self.policy,'maximum_contact_minutes',1),(self.policy,'reference','Different authority'),
            (self.config,'calendar_reference','Different calendar')]
        for obj,field,value in records:
            with self.subTest(model=obj._meta.model_name,field=field):
                setattr(obj,field,value)
                with self.assertRaises(ValidationError): obj.save()
                with self.assertRaises(IntegrityError),transaction.atomic():
                    type(obj).objects.filter(pk=obj.pk).update(**{field:value})
                obj.refresh_from_db()
        self.intact()

    def test_original_curriculum_reassignment_and_deletion_blocked(self):
        version=self.requirement.curriculum_version
        other=m.CurriculumVersion.objects.create(family='Unrelated',revision='2')
        for obj in (self.requirement,self.section.cohort):
            with self.assertRaises(IntegrityError),transaction.atomic():
                type(obj).objects.filter(pk=obj.pk).update(curriculum_version=other)
        with self.assertRaises((ProtectedError,ValidationError)),transaction.atomic(): version.delete()
        with self.assertRaises(IntegrityError),transaction.atomic(),connection.cursor() as c:
            c.execute('DELETE FROM schedules_curriculumversion WHERE id=%s',[version.pk])
        self.intact()

    def test_policy_delete_replacement_and_activation_overlap_blocked(self):
        with self.assertRaises((ProtectedError,ValidationError)),transaction.atomic(): self.policy.delete()
        with self.assertRaises(IntegrityError),transaction.atomic(): replace_copy(self.policy,id=self.policy.pk,maximum_contact_minutes=180)
        inactive=m.FacultyContactMinutePolicy.objects.create(faculty=self.faculty,accounting_period='CALENDAR_WEEK',
            covered_levels='SHS_AND_TERTIARY',week_starts_on=0,starts_on=self.policy.starts_on,ends_on=self.policy.ends_on,
            maximum_contact_minutes=180,reference='Draft',is_verified=True,is_approved=True)
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.FacultyContactMinutePolicy.objects.filter(pk=inactive.pk).update(is_active=True)
        self.intact()

    def test_unrelated_policy_period_is_allowed(self):
        other=m.FacultyContactMinutePolicy.objects.create(faculty=self.faculty,accounting_period='CALENDAR_WEEK',
            covered_levels='SHS_AND_TERTIARY',week_starts_on=0,starts_on=date(2027,1,4),ends_on=date(2027,1,10),
            maximum_contact_minutes=180,reference='Future synthetic approval',is_verified=True,is_approved=True,is_active=True)
        other.maximum_contact_minutes=240; other.save()
        other.delete()
        assert_prepared(self.term)

    def test_pattern_component_inserts_and_old_new_relationships(self):
        with self.assertRaises(IntegrityError),transaction.atomic():
            replace_copy(self.config.patterns.get(),id=9999,sequence=2)
        with self.assertRaises(IntegrityError),transaction.atomic():
            replace_copy(self.component,id=9999,position=2)
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.SHSMeetingPattern.objects.filter(configuration=self.config).update(weekday=1)
        self.intact()

    def test_unique_collision_paths(self):
        records=[self.requirement.curriculum_version,self.section.cohort,self.requirement,
                 self.plan.offering,self.plan,self.component,self.config,self.config.patterns.get()]
        for obj in records:
            with self.subTest(model=obj._meta.model_name),self.assertRaises(IntegrityError),transaction.atomic():
                replace_copy(obj,id=9999)
        self.intact()

    def test_archived_definitions_and_evidence_remain_protected(self):
        finalize(self.schedule, archived=True)
        self.assertEqual(list(m.ScheduleSnapshot.objects.filter(schedule=self.schedule).values()),self.frozen)
        # Authorized supersession creates its own snapshot; retain both while
        # checking that rejected operational edits change neither history.
        self.frozen=list(m.ScheduleSnapshot.objects.values())
        with self.assertRaises(ValidationError):
            self.config.is_confirmed=False; self.config.save()
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.DeliveryComponent.objects.filter(pk=self.component.pk).update(duration_minutes=30)
        self.intact()

    def test_evidence_immutable_all_paths(self):
        with self.assertRaises(ValidationError): self.evidence.save()
        with self.assertRaises(ValidationError): self.evidence.delete()
        for sql in ('UPDATE schedules_shsapprovalevidence SET reason=reason', 'DELETE FROM schedules_shsapprovalevidence'):
            with self.assertRaises(IntegrityError),transaction.atomic(),connection.cursor() as c: c.execute(sql)
        with self.assertRaises(IntegrityError),transaction.atomic(): replace_copy(self.evidence,id=9999)
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.SHSApprovalEvidence.objects.bulk_create([m.SHSApprovalEvidence(term=self.term,actor=self.actor,
                kind='PREPARATION',reason='Forged',data=self.evidence.data)])
        self.assertEqual(m.SHSApprovalEvidence.objects.count(),1)

    def test_binding_identity_protected(self):
        with self.assertRaises(IntegrityError),transaction.atomic(): m.SHSMeetingBinding.objects.update(id=9999)
        self.intact()

    def test_legacy_not_backfilled_and_requires_explicit_review(self):
        self.legacy()
        with self.assertRaisesMessage(ValidationError,'scope is missing'): assert_prepared(self.term)
        self.assertEqual(m.SHSApprovalEvidence.objects.count(),0)
        data,token=approval.preview(actor=self.actor,term=self.term)
        self.assertEqual(m.SHSApprovalEvidence.objects.count(),0)
        evidence=approval.reapprove(actor=self.actor,term=self.term,scope_token=token,reason='Explicit current review')
        self.assertEqual(evidence.kind,'CURRENT_REVIEW')
        self.assertFalse(evidence.data['original_historical_scope_proven'])
        assert_prepared(self.term)
        with connection.cursor() as c:
            c.execute(f'SELECT 1 FROM {approval.policy.VIEW} WHERE uncertain=1')
            self.assertIsNotNone(c.fetchone())
        with self.assertRaises(ValidationError):
            self.requirement.curriculum_version.is_active=False
            self.requirement.curriculum_version.save()
        self.intact()

    def test_unauthorized_expired_and_wrong_actor_reviews(self):
        other=User.objects.create_user('not-admin',password='test')
        with self.assertRaises(ValidationError): approval.preview(actor=other,term=self.term)
        _,token=approval.preview(actor=self.actor,term=self.term)
        with self.assertRaises(ValidationError): approval.reapprove(actor=other,term=self.term,scope_token=token,reason='No')
        with self.assertRaises(ValidationError): approval.reapprove(actor=self.actor,term=self.term,scope_token='invalid',reason='No')
        with patch('django.core.signing.time.time',return_value=99999999999):
            with self.assertRaises(ValidationError): approval.reapprove(actor=self.actor,term=self.term,scope_token=token,reason='Expired')
        self.assertEqual(m.SHSApprovalEvidence.objects.count(),1)

    def test_stale_review_rejected_and_transaction_rolls_back(self):
        _,token=approval.preview(actor=self.actor,term=self.term)
        m.AcademicTerm.objects.filter(pk=self.term.pk).update(is_active=True)
        with self.assertRaisesMessage(ValidationError,'changed'):
            approval.reapprove(actor=self.actor,term=self.term,scope_token=token,reason='Stale')
        _,token=approval.preview(actor=self.actor,term=self.term)
        with patch('schedules.services.conflicts.schedule_validation_messages',return_value=['Synthetic conflict']):
            with self.assertRaisesMessage(ValidationError,'No reapproval was saved'):
                approval.reapprove(actor=self.actor,term=self.term,scope_token=token,reason='Must roll back')
        self.assertEqual(m.SHSApprovalEvidence.objects.count(),1)
        self.intact()

    def test_authorization_rechecked_after_preview(self):
        _,token=approval.preview(actor=self.actor,term=self.term)
        User.objects.filter(pk=self.actor.pk).update(is_active=False)
        with self.assertRaises(ValidationError): approval.reapprove(actor=self.actor,term=self.term,scope_token=token,reason='Revoked')
        self.assertEqual(m.SHSApprovalEvidence.objects.count(),1)

    def test_unrelated_records_and_noop_updates_allowed(self):
        other=m.CurriculumVersion.objects.create(family='Other draft',revision='1')
        other.reference_notes='Independent draft'; other.save(); other.delete()
        m.SHSAssignmentConfiguration.objects.filter(pk=self.config.pk).update(is_confirmed=True)
        assert_prepared(self.term)

    def test_frozen_curriculum_dependency_survives_live_chain_drift(self):
        old=self.requirement.curriculum_version
        new=m.CurriculumVersion.objects.create(family='Different synthetic source',revision='2',
            reference_title='Different reference',verification_status='VERIFIED',is_active=True)
        # Simulate prior unsafe bulk changes in isolated storage. Neither binding
        # nor approval evidence is changed; restore guards immediately.
        for model,pk in (('curriculumsubjectrequirement',self.requirement.pk),('cohort',self.section.cohort_id)):
            name=f'shs_scope_{model}_update'
            with connection.cursor() as c:
                c.execute('DROP TRIGGER '+name)
                c.execute(f'UPDATE schedules_{model} SET curriculum_version_id=%s WHERE id=%s',[new.pk,pk])
                c.execute(approval.policy.TRIGGERS[name])
        with self.assertRaises(ValidationError): assert_prepared(self.term)
        for version in (old,new):
            with self.assertRaises(IntegrityError),transaction.atomic(),connection.cursor() as c:
                c.execute('DELETE FROM schedules_curriculumversion WHERE id=%s',[version.pk])
        self.intact()

    def test_update_replace_collision_and_bulk_delete(self):
        original=self.requirement.curriculum_version
        unrelated=m.CurriculumVersion.objects.create(family='Free identity',revision='9')
        with self.assertRaises(IntegrityError),transaction.atomic(),connection.cursor() as c:
            c.execute('UPDATE OR REPLACE schedules_curriculumversion SET family=%s,revision=%s,education_level=%s WHERE id=%s',
                [original.family,original.revision,original.education_level,unrelated.pk])
        with self.assertRaises((ProtectedError,ValidationError)),transaction.atomic():
            m.FacultyContactMinutePolicy.objects.filter(pk=self.policy.pk).delete()
        unrelated.refresh_from_db()
        self.assertEqual(unrelated.family,'Free identity')
        self.intact()

    def test_missing_snapshot_fails_closed(self):
        guards=import_module('schedules.migrations.0012_historical_snapshots').TRIGGERS
        with connection.cursor() as c:
            c.execute('DROP TRIGGER h2_snapshot_delete')
            c.execute('DELETE FROM schedules_schedulesnapshot')
            c.execute(guards['h2_snapshot_delete'])
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.CurriculumVersion.objects.filter(pk=self.requirement.curriculum_version_id).update(is_active=False)

    def test_new_preparation_cannot_attest_existing_bindings(self):
        with self.assertRaises(ValidationError):
            with approval.new_preparation(actor=self.actor,term=self.term): pass
        self.assertEqual(m.SHSApprovalEvidence.objects.count(),1)

    def test_malformed_evidence_fails_closed(self):
        with connection.cursor() as c:
            c.execute('DROP TRIGGER shs_scope_update')
            c.execute("UPDATE schedules_shsapprovalevidence SET data='[]'")
            c.execute(approval.policy.TRIGGERS['shs_scope_update'])
        with self.assertRaises(ValidationError): assert_prepared(self.term)
        with self.assertRaises(IntegrityError),transaction.atomic():
            m.CurriculumVersion.objects.filter(pk=self.requirement.curriculum_version_id).update(is_active=False)

    def test_command_authentication_and_explicit_confirmation(self):
        output=StringIO()
        with patch('schedules.management.commands.review_shs_approval.getpass.getpass',return_value='test-only'):
            call_command('review_shs_approval',term=self.term.pk,administrator=self.actor.username,stdout=output)
        self.assertEqual(m.SHSApprovalEvidence.objects.count(),1)
        token=output.getvalue().split('Confirmation token (expires in one hour): ')[1].strip()
        with patch('schedules.management.commands.review_shs_approval.getpass.getpass',return_value='test-only'):
            call_command('review_shs_approval',term=self.term.pk,administrator=self.actor.username,
                confirm_token=token,reason='Explicit CLI review',stdout=StringIO())
        self.assertEqual(m.SHSApprovalEvidence.objects.count(),2)
        with patch('schedules.management.commands.review_shs_approval.getpass.getpass',return_value='wrong'):
            with self.assertRaises(CommandError):
                call_command('review_shs_approval',term=self.term.pk,administrator=self.actor.username)


class SHSScopeMigrationTests(SimpleTestCase):
    def test_empty_reverse_populated_legacy_native_guards_and_reversal_refusal(self):
        script=r'''
import os,sqlite3
os.environ['DJANGO_SETTINGS_MODULE']='sched_ease.settings'
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
import django
django.setup()
from django.core.management import call_command
from django.db import connection
from schedules import models as m
from schedules.test_shs_generation import ControlledSHSGenerationTests
from schedules.test_contact_workload import ContactPolicyTests
from schedules.services.shs_scheduling import generate_shs
from schedules.services.publication import publish
from schedules.services import shs_approval as approval
call_command('migrate','auth',verbosity=0)
call_command('migrate','schedules','0032',verbosity=0)
f=ControlledSHSGenerationTests(); f.setUp(); ContactPolicyTests.policy(f)
s=generate_shs(f.term,f.settings,actor=f.actor,seed=17); s,_=publish(s,f.actor)
models=(m.Schedule,m.ScheduleEntry,m.ScheduleSnapshot,m.SHSMeetingBinding,m.CurriculumVersion,m.FacultyContactMinutePolicy)
before={x.__name__:list(x.objects.values()) for x in models}
with connection.cursor() as c:
    c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"); triggers=dict(c.fetchall())
for target in ('0033','0032','0033'):
    call_command('migrate','schedules',target,verbosity=0)
    assert before=={x.__name__:list(x.objects.values()) for x in models}
    with connection.cursor() as c:
        c.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'"); current=dict(c.fetchall())
        assert all(current[k]==v for k,v in triggers.items())
        c.execute('PRAGMA integrity_check'); assert c.fetchall()==[('ok',)]
        c.execute('PRAGMA foreign_key_check'); assert c.fetchall()==[]
assert m.SHSApprovalEvidence.objects.count()==0
_,token=approval.preview(actor=f.actor,term=f.term)
evidence=approval.reapprove(actor=f.actor,term=f.term,scope_token=token,reason='Synthetic explicit legacy review')
assert evidence.kind=='CURRENT_REVIEW' and not evidence.data['original_historical_scope_proven']
assert before=={x.__name__:list(x.objects.values()) for x in models}
try: call_command('migrate','schedules','0032',verbosity=0)
except RuntimeError as exc: assert 'approval evidence exists' in str(exc)
else: raise AssertionError('Reversal discarded evidence')
native=sqlite3.connect(':memory:')
from schedules.identity import normalize_identity
native.create_function('schedease_identity_v1',1,normalize_identity,deterministic=True)
connection.connection.backup(native)
for sql in ('UPDATE schedules_curriculumversion SET is_active=0','DELETE FROM schedules_facultycontactminutepolicy',
            'UPDATE schedules_shsapprovalevidence SET reason=reason'):
    try: native.execute(sql)
    except sqlite3.IntegrityError: native.rollback()
    else: raise AssertionError('Native SQL bypass: '+sql)
native.close()
'''
        result=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
