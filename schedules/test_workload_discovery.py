"""T8 discovery and explicit authorization of automatically identified candidates."""
from datetime import time
from django.core.exceptions import ValidationError
from django.urls import reverse
from . import models as m
from .test_known_defects import SchedulingDefectFixture
from . import test_workload_balancing as base_tests
from .services import workload_discovery as discovery
from .services import workload_balancing as balancing


class WorkloadDiscoveryTests(SchedulingDefectFixture):
    setUp = base_tests.WorkloadBalancingTests.setUp
    http_analyze = base_tests.WorkloadBalancingTests.http_analyze
    http_generate = base_tests.WorkloadBalancingTests.http_generate

    def analyze(self, **filters):
        return discovery.discover(self.admin, self.term, self.department, **filters)

    def test_auto_discovery_has_no_write_or_implicit_authorization(self):
        before = balancing.fingerprint()
        result, token = self.analyze()
        self.assertEqual((result['total'], result['eligible'], result['excluded'], result['alternatives']), (3, 3, 0, 1))
        self.assertTrue(result['can_proceed'])
        self.assertEqual(before, balancing.fingerprint())
        self.assertFalse(m.WorkloadApproval.objects.exists())
        self.client.force_login(self.admin)
        analyzed = self.http_analyze()
        self.assertContains(analyzed, 'eligible candidates (approval required)')
        response = self.client.post(reverse('workload_proposals'), {'action':'generate','analysis_token':analyzed.context['analysis_token'], 'comparable':'yes'})
        self.assertContains(response, 'Authorize the listed candidate assignments')
        self.assertNotIn('token', response.context)

    def test_lock_and_scheduled_term_reasons(self):
        schedule = m.Schedule.objects.create(term=self.term, name='Lock')
        schedule.entries.create(assignment=self.meetings[0],room=self.room,day=0,start_time=time(8),end_time=time(9))
        result, _ = self.analyze()
        self.assertEqual(result['eligible'], 0)
        self.assertIn('locked', result['exclusions'][0]['reason'])
        self.assertIn('unscheduled term', result['exclusions'][1]['reason'])

    def test_unqualified_alternative_is_explained(self):
        c = m.Credential.objects.create(name='Eligibility credential')
        m.SubjectCredentialRequirement.objects.create(subject=self.subject, required_credential=c)
        result, _ = self.analyze(assignments=[self.parent.pk])
        self.assertEqual(result['eligible'], 0)
        self.assertIn('qualification requirements', result['exclusions'][0]['reason'])

    def test_availability_and_limit_exclusions(self):
        for day in range(6):
            m.Availability.objects.create(faculty=self.other,day=day,start_time=time(7),end_time=time(19),kind=m.AvailabilityKind.UNAVAILABLE)
        result, _ = self.analyze()
        self.assertEqual(result['eligible'], 0)
        self.assertIn('availability', result['exclusions'][0]['reason'])
        m.Availability.objects.all().delete()
        self.other.max_weekly_hours = 1
        self.other.save()
        result, _ = self.analyze()
        self.assertEqual(result['eligible'], 0)
        self.assertIn('weekly limit', result['exclusions'][0]['reason'])

    def test_empty_scope_and_excluded_group(self):
        empty = m.Department.objects.create(code='EMPTY',name='Empty')
        result, _ = discovery.discover(self.admin,self.term,empty)
        self.assertEqual(result['total'], 0)
        self.assertFalse(result['can_proceed'])
        result, _ = self.analyze(exclude_faculty=self.faculty_ids)
        self.assertFalse(result['can_proceed'])
        self.assertTrue(result['warnings'])

    def test_manual_limits_exclusions_and_persistence(self):
        result, _ = self.analyze(assignments=self.ids[:2],exclude_assignments=[self.ids[1]])
        self.assertEqual(result['total'], 2)
        self.assertEqual(result['eligible'], 1)
        self.assertIn('Advanced Selection', result['exclusions'][0]['reason'])
        self.client.force_login(self.admin)
        response = self.http_analyze(assignments=self.ids[:2], faculty=self.faculty_ids)
        self.assertEqual(set(response.context['form']['assignments'].value()), set(map(str,self.ids[:2])))
        generated = self.client.post(reverse('workload_proposals'), {'action':'generate','analysis_token':response.context['analysis_token'],
            'scope_state':response.context['scope_state'],'authorize_scope':'yes','comparable':'yes'})
        self.assertEqual(set(generated.context['form']['assignments'].value()), set(map(str,self.ids[:2])))
        self.assertIn('token', generated.context)

    def test_out_of_scope_and_contradictory_filters_are_rejected(self):
        other = m.Department.objects.create(code='OTHER',name='Other')
        self.client.force_login(self.admin)
        response = self.http_analyze(department=other.pk,assignments=self.ids,faculty=self.faculty_ids)
        self.assertIn('assignments', response.context['form'].errors)
        self.assertIn('faculty', response.context['form'].errors)
        self.assertNotIn('analysis',response.context)
        response = self.http_analyze(assignments=[self.parent.pk],exclude_assignments=[self.parent.pk])
        self.assertIn('exclude_assignments', response.context['form'].errors)

    def test_new_analysis_invalidates_prior_proposal(self):
        self.client.force_login(self.admin)
        generated = self.http_generate()
        token = generated.context['token']
        reviewed = generated.context['reviewed']
        selected = generated.context['selected']
        self.http_analyze(exclude_assignments=[self.parent.pk])
        response = self.client.post(reverse('workload_proposals'), {'action':'approve','token':token,'selected':selected,'reviewed':reviewed,'confirm':'yes'})
        self.assertContains(response, 'replaced by a new analysis')
        self.assertFalse(m.WorkloadApproval.objects.exists())

    def test_changed_inputs_invalidate_discovery(self):
        _, token = self.analyze()
        self.other.max_weekly_hours = 8
        self.other.save()
        with self.assertRaisesMessage(ValidationError, 'stale'):
            discovery.authorize(self.admin,token)

    def test_default_form_and_advanced_checkbox_controls(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('workload_proposals'))
        self.assertContains(response, 'Analyze Workload')
        self.assertContains(response, 'Advanced Selection (optional)')
        self.assertNotContains(response, '<select name="assignments"')
        self.assertContains(response, 'type="checkbox" name="assignments"')
        self.assertFalse(response.context['form'].fields['assignments'].required)
        self.assertFalse(response.context['form'].fields['faculty'].required)
