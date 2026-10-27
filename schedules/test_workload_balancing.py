"""T8 authorized allocation, coordinated metrics, and atomic approvals."""
from unittest.mock import patch
from datetime import time
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core import signing
from django.urls import reverse
from .test_known_defects import SchedulingDefectFixture
from . import models as m
from .services import workload_balancing as w


class WorkloadBalancingTests(SchedulingDefectFixture):
    def setUp(self):
        self.admin = User.objects.create_superuser('balancer', password='test')
        self.faculty.max_weekly_hours = 12
        self.faculty.save()
        self.other = m.Faculty.objects.create(department=self.department, employee_id='ALT', full_name='Alternative', max_weekly_hours=6)
        self.parents = [self.parent]
        for i in (2, 3):
            subject = m.Subject.objects.create(department=self.department, code=f'BAL{i}', title='Balance', lecture_hours=2, lab_hours=0)
            a = m.Assignment.objects.create(term=self.term, subject=subject, section=self.section, faculty=self.faculty)
            m.TeachingAssignment.objects.create(assignment=a, component='LECTURE', duration_minutes=120)
            self.parents.append(a)
        self.ids = [a.pk for a in self.parents]
        self.faculty_ids = [self.faculty.pk, self.other.pk]

    def http_analyze(self, **overrides):
        data = {'action':'analyze', 'term':self.term.pk, 'department':self.department.pk}
        data.update(overrides)
        return self.client.post(reverse('workload_proposals'), data)

    def http_generate(self):
        response = self.http_analyze()
        self.assertTrue(response.context['analysis']['can_proceed'])
        return self.client.post(reverse('workload_proposals'), {'action':'generate',
            'analysis_token':response.context['analysis_token'], 'scope_state':response.context['scope_state'],
            'authorize_scope':'yes', 'comparable':'yes'})

    def proposal(self):
        token, attention = w.propose(self.admin, self.term.pk, self.ids, self.faculty_ids)
        payload = signing.loads(token, salt=w.SALT)
        return token, list(payload['changes'])

    def test_reproducible_fairness_explanations_and_limits(self):
        token, selected = self.proposal()
        _, result = w.preview(self.admin, token, selected)
        self.assertEqual(len(selected), 1)
        self.assertAlmostEqual(result['before']['variance'], 625)
        self.assertAlmostEqual(result['after']['variance'], 0)
        self.assertEqual([r['minutes'] for r in result['after']['rows']], [240, 120])
        self.assertEqual(result['hard_violations'], 0)
        self.assertIn('credential rules', result['proposals'][0]['explanation'])
        second, selected2 = self.proposal()
        self.assertEqual(selected, selected2)
        self.assertEqual(signing.loads(token, salt=w.SALT)['changes'], signing.loads(second, salt=w.SALT)['changes'])
        self.assertEqual(m.WorkloadApproval.objects.count(), 0)
        self.assertTrue(all(a.faculty_id == self.faculty.pk for a in m.Assignment.objects.filter(pk__in=self.ids)))

    def test_selection_recalculation_and_atomic_audit(self):
        token, selected = self.proposal()
        _, empty = w.preview(self.admin, token, [])
        self.assertEqual(empty['improvement'], 0)
        with self.assertRaises(ValidationError):
            w.approve(self.admin, token, [])
        audit = w.approve(self.admin, token, selected)
        self.assertEqual(len(audit.evidence['result']['changes']), 1)
        self.assertEqual(audit.administrator, self.admin)
        self.assertTrue(m.TeachingAssignment.objects.filter(assignment_id=selected[0], faculty=self.other).exists())
        self.assertFalse(m.Schedule.objects.exists())
        with self.assertRaises(ValidationError):
            w.approve(self.admin, token, selected)
        self.assertEqual(m.WorkloadApproval.objects.count(), 1)

    def test_combined_changes_and_overload_rejected(self):
        result = w.evaluate(self.term.pk, self.ids, self.faculty_ids, {self.ids[0]: self.other.pk, self.ids[1]: self.other.pk})
        self.assertEqual([r['minutes'] for r in result['after']['rows']], [120, 240])
        self.other.max_weekly_hours = 3
        self.other.save()
        with self.assertRaisesMessage(ValidationError, 'weekly limit'):
            w.evaluate(self.term.pk, self.ids, self.faculty_ids, {self.ids[0]: self.other.pk, self.ids[1]: self.other.pk})

    def test_stale_inputs_and_signed_scope(self):
        token, selected = self.proposal()
        with self.assertRaises(ValidationError):
            w.preview(self.admin, token, ['999999'])
        self.other.max_weekly_hours = 8
        self.other.save()
        with self.assertRaisesMessage(ValidationError, 'stale'):
            w.approve(self.admin, token, selected)
        self.assertFalse(m.WorkloadApproval.objects.exists())

    def test_rollback_preserves_all_assignments(self):
        token, selected = self.proposal()
        with patch.object(m.WorkloadApproval, 'save', autospec=True, side_effect=[None, RuntimeError('audit failed')]):
            with self.assertRaises(RuntimeError):
                w.approve(self.admin, token, selected)
        self.assertTrue(all(a.faculty_id == self.faculty.pk for a in m.Assignment.objects.filter(pk__in=self.ids)))
        self.assertFalse(m.WorkloadApproval.objects.exists())

    def test_locked_draft_and_nonselected_assignments(self):
        schedule = m.Schedule.objects.create(term=self.term, name='Draft')
        m.ScheduleEntry.objects.create(schedule=schedule, assignment=self.meetings[0], room=self.room, day=0, start_time=time(8), end_time=time(9))
        with self.assertRaisesMessage(ValidationError, 'locked'):
            self.proposal()
        schedule.entries.all().delete()
        with self.assertRaises(ValidationError):
            w.evaluate(self.term.pk, [self.ids[0]], self.faculty_ids, {self.ids[1]: self.other.pk})

    def test_unavailable_and_unqualified_alternatives(self):
        for day in range(6):
            m.Availability.objects.create(faculty=self.other, day=day, start_time=time(7), end_time=time(19), kind=m.AvailabilityKind.UNAVAILABLE)
        token, selected = self.proposal()
        self.assertEqual(selected, [])
        m.Availability.objects.all().delete()
        credential = m.Credential.objects.create(name='Required')
        m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=credential)
        with self.assertRaises(ValidationError):
            w.evaluate(self.term.pk, self.ids, self.faculty_ids, {self.parent.pk: self.other.pk})

    def test_admin_only_http_and_service(self):
        ordinary = User.objects.create_user('ordinary', password='test')
        with self.assertRaises(PermissionDenied):
            w.propose(ordinary, self.term.pk, self.ids, self.faculty_ids)
        self.client.force_login(ordinary)
        self.assertEqual(self.client.get(reverse('workload_proposals')).status_code, 403)
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('workload_proposals')), 'Workload Balancing Proposals')

    def test_http_confirmation_required(self):
        self.client.force_login(self.admin)
        response = self.http_generate()
        self.assertEqual(response.status_code, 200)
        self.assertIn('token', response.context)
        token, selected = response.context['token'], response.context['selected']
        response = self.client.post(reverse('workload_proposals'), {'action':'approve', 'token':token, 'selected':selected, 'reviewed':response.context['reviewed']})
        self.assertContains(response, 'Confirm the selected batch')
        self.assertFalse(m.WorkloadApproval.objects.exists())

    def test_published_schedule_remains_unchanged(self):
        from .services.publication import publish
        schedule = m.Schedule.objects.create(term=self.term, name='Protected')
        start = 7
        for a in m.TeachingAssignment.objects.filter(term=self.term).order_by('pk'):
            hours = a.required_duration_minutes // 60
            schedule.entries.create(assignment=a, room=self.room, day=0, start_time=time(start), end_time=time(start + hours))
            start += hours
        schedule, _ = publish(schedule, self.admin)
        snapshot = schedule.snapshot.data
        with self.assertRaisesMessage(ValidationError, 'locked'):
            self.proposal()
        schedule.refresh_from_db()
        self.assertEqual(schedule.status, 'PUBLISHED')
        self.assertEqual(schedule.snapshot.data, snapshot)
        self.assertFalse(m.WorkloadApproval.objects.exists())

    def test_feasibility_rejects_joint_resource_conflict(self):
        # Six hours of teaching cannot occupy a single two-hour weekly window.
        m.Availability.objects.create(room=self.room, day=0, start_time=time(8), end_time=time(10), kind=m.AvailabilityKind.AVAILABLE)
        with self.assertRaisesMessage(ValidationError, 'conflict-free'):
            w.evaluate(self.term.pk, self.ids, self.faculty_ids, {self.parent.pk:self.other.pk})

    def test_two_change_batch_and_failure_after_first_save(self):
        self.other.max_weekly_hours = 12
        self.other.save()
        # Four two-hour assignments => two changes make 4h/4h.
        subject = m.Subject.objects.create(department=self.department, code='BAL4', title='Fourth', lecture_hours=2, lab_hours=0)
        parent = m.Assignment.objects.create(term=self.term, subject=subject, section=self.section, faculty=self.faculty)
        m.TeachingAssignment.objects.create(assignment=parent, component='LECTURE', duration_minutes=120)
        self.ids.append(parent.pk)
        token, selected = self.proposal()
        self.assertEqual(len(selected), 2)
        _, result = w.preview(self.admin, token, selected[:1])
        self.assertGreater(result['after']['variance'], 0)
        real_save = m.Assignment.save
        calls = []
        def failing_save(obj, *args, **kwargs):
            calls.append(obj.pk)
            if len(calls) == 2:
                raise ValidationError('simulated second update failure')
            return real_save(obj, *args, **kwargs)
        with patch.object(m.Assignment, 'save', failing_save):
            with self.assertRaises(ValidationError):
                w.approve(self.admin, token, selected)
        self.assertTrue(all(a.faculty_id == self.faculty.pk for a in m.Assignment.objects.filter(pk__in=self.ids)))
        self.assertFalse(m.WorkloadApproval.objects.exists())
        audit = w.approve(self.admin, token, selected)
        self.assertEqual(len(audit.evidence['result']['proposals']), 2)
        self.assertEqual(audit.evidence['result']['after']['variance'], 0)

    def test_no_improvement_keeps_unequal_legitimate_hours(self):
        self.parents[0].faculty = self.other
        self.parents[0].save()
        token, selected = self.proposal()
        self.assertEqual(selected, [])  # 4h/12h and 2h/6h are already equal utilization
        _, result = w.preview(self.admin, token, [])
        self.assertEqual(result['after']['variance'], 0)

    def test_http_changed_selection_requires_new_preview_and_csrf(self):
        from django.test import Client
        self.client.force_login(self.admin)
        response = self.http_generate()
        data = {'action':'approve', 'token':response.context['token'], 'selected':[], 'reviewed':response.context['reviewed'], 'confirm':'yes'}
        self.assertContains(self.client.post(reverse('workload_proposals'), data), 'selection changed')
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(reverse('workload_proposals'), data).status_code, 403)
        self.assertFalse(m.WorkloadApproval.objects.exists())

    def test_overlapping_published_term_blocks_alternative(self):
        from .services.publication import publish
        other_term = m.AcademicTerm.objects.create(name='Other', school_year='2026-2027', starts_on=self.term.starts_on, ends_on=self.term.ends_on)
        parent = m.Assignment.objects.create(term=other_term, subject=self.subject, section=self.section, faculty=self.other)
        meeting = m.TeachingAssignment.objects.create(assignment=parent, component='LECTURE', duration_minutes=120)
        m.Availability.objects.create(faculty=self.other, day=0, start_time=time(8), end_time=time(10), kind=m.AvailabilityKind.AVAILABLE)
        schedule = m.Schedule.objects.create(term=other_term, name='Published external')
        schedule.entries.create(assignment=meeting, room=self.room, day=0, start_time=time(8), end_time=time(10))
        publish(schedule, self.admin)
        with self.assertRaisesMessage(ValidationError, 'without conflicting with another published term'):
            w.evaluate(self.term.pk, self.ids, self.faculty_ids, {self.parent.pk:self.other.pk})

    def test_role_administrator_can_approve_faculty_cannot(self):
        admin = User.objects.create_user('roleadmin', password='test')
        m.Profile.objects.create(user=admin, role=m.Role.ADMIN)
        faculty_user = User.objects.create_user('teacher-role', password='test')
        m.Profile.objects.create(user=faculty_user, role=m.Role.FACULTY)
        token, _ = w.propose(admin, self.term.pk, self.ids, self.faculty_ids)
        selected = list(signing.loads(token, salt=w.SALT)['changes'])
        with self.assertRaises(PermissionDenied):
            w.approve(faculty_user, token, selected)
        self.assertEqual(w.approve(admin, token, selected).administrator, admin)

    def test_token_tampering_expiry_and_missing_comparability(self):
        token, selected = self.proposal()
        with self.assertRaises(ValidationError):
            w.preview(self.admin, token + 'invalid', selected)
        with patch('django.core.signing.time.time', return_value=9999999999):
            with self.assertRaisesMessage(ValidationError, 'expired'):
                w.preview(self.admin, token, selected)
        self.client.force_login(self.admin)
        analyzed = self.http_analyze()
        response = self.client.post(reverse('workload_proposals'), {'action':'generate','analysis_token':analyzed.context['analysis_token']})
        self.assertContains(response, 'confirm instructor comparability')
        self.assertNotIn('token', response.context)

    def test_http_preview_and_confirm_save_one_audited_batch(self):
        self.client.force_login(self.admin)
        response = self.http_generate()
        token, selected = response.context['token'], response.context['selected']
        response = self.client.post(reverse('workload_proposals'), {'action':'preview','token':token,'selected':selected})
        response = self.client.post(reverse('workload_proposals'), {'action':'approve','token':token,'selected':selected,'reviewed':response.context['reviewed'],'confirm':'yes'})
        self.assertRedirects(response, reverse('workload_proposals'))
        self.assertEqual(m.WorkloadApproval.objects.count(), 1)

    def test_available_boundary_and_adjacent_meetings(self):
        m.Availability.objects.create(faculty=self.other, day=0, start_time=time(8), end_time=time(10), kind=m.AvailabilityKind.AVAILABLE)
        result = w.evaluate(self.term.pk, self.ids, self.faculty_ids, {self.parent.pk:self.other.pk})
        moved = [p for p in result['placements'] if p['meeting'] in [a.pk for a in self.meetings]]
        self.assertEqual([(p['start'], p['end']) for p in moved], [('08:00:00','09:00:00'), ('09:00:00','10:00:00')])
        self.assertEqual(result['hard_violations'], 0)
