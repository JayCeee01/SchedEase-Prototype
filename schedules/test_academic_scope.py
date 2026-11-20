from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from . import models as m
from . import test_education_context as context_tests
from .services.manual_edits import copy_to_draft, save_manual_entry, revision_token, FIELDS
from .services.publication import publish
from .services.conflicts import schedule_validation_messages


class ScheduleScopeTests(TestCase):
    def setUp(self):
        context_tests.EducationContextTests.setUp(self)
        self.original, self.section, self.faculty = context_tests.EducationContextTests.published(self)
        self.draft = copy_to_draft(source_id=self.original.pk, actor=self.admin)
        program = m.Program.objects.create(code='SCOPE-SHS', name='SHS',
            education_level='SHS', department=self.section.program.department)
        year, _ = m.YearLevel.objects.get_or_create(level=11, defaults={'label':'Grade 11'})
        self.other = m.Section.objects.create(program=program, year_level=year, name='A', size=10)

    def test_direct_manual_service_rejects_effective_section_and_rolls_back(self):
        entry=self.draft.entries.get()
        proposed={field:getattr(entry,field) for field in FIELDS}
        proposed['section_override_id']=self.other.pk
        before=self.draft.updated_at
        with self.assertRaisesMessage(ValidationError,'education level'):
            save_manual_entry(schedule_id=self.draft.pk,entry_id=entry.pk,actor=self.admin,
                revision=revision_token(self.draft,self.admin,entry),proposed=proposed)
        entry.refresh_from_db()
        self.draft.refresh_from_db()
        self.assertIsNone(entry.section_override_id)
        self.assertEqual(self.draft.updated_at,before)

    def test_direct_publication_checks_context_and_preserves_history(self):
        snapshot=self.original.snapshot.data
        before=self.draft.updated_at
        with self.assertRaisesMessage(ValidationError,'education level'):
            publish(self.draft,self.admin,True,education_level='SHS')
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.updated_at,before)
        self.assertEqual(self.draft.status,'DRAFT')
        self.assertEqual(self.original.snapshot.data,snapshot)
        with self.assertRaises(ValidationError):
            publish(self.draft,self.admin,True,term_id=self.shs.pk)
        published,_=publish(self.draft,self.admin,True,education_level='TERTIARY',term_id=self.ter.pk)
        self.assertEqual(published.status,'PUBLISHED')
        self.original.refresh_from_db()
        self.assertEqual(self.original.status,'ARCHIVED')
        self.assertEqual(self.original.snapshot.data,snapshot)

    def test_publication_revalidates_existing_mismatched_draft(self):
        entry=self.draft.entries.get()
        # Draft SQL updates represent an alternative writer; final validation
        # must still reject incompatible academic identity.
        m.ScheduleEntry.objects.filter(pk=entry.pk).update(section_override=self.other)
        self.assertTrue(any('education level' in str(e) for e in schedule_validation_messages(self.draft)))
        with self.assertRaises(ValidationError): publish(self.draft,self.admin,True)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status,'DRAFT')

    def test_forged_view_context_is_rejected(self):
        entry=self.draft.entries.get()
        routes=[('entry_create',[self.draft.pk]),('entry_update',[self.draft.pk,entry.pk]),
                ('publish_schedule',[self.draft.pk]),('entry_remove',[self.draft.pk,entry.pk]),
                ('copy_schedule_to_draft',[self.original.pk])]
        for route,args in routes:
            with self.subTest(route=route):
                self.assertEqual(self.client.post(reverse(route,args=args),{'education_level':'SHS'}).status_code,404)
        self.assertEqual(self.client.post(reverse('publish_schedule',args=[self.draft.pk]),
            {'education_level':'COMBINED'}).status_code,404)
        self.assertEqual(self.client.post(reverse('resource_delete',args=['schedules',self.draft.pk]),
            {'education_level':'SHS'}).status_code,404)
        self.assertEqual(self.client.post(reverse('resource_update',args=['schedules',self.draft.pk]),
            {'education_level':'SHS'}).status_code,404)

    def test_valid_shared_resources_and_finalized_edit_protection(self):
        entry=self.draft.entries.get()
        proposed={field:getattr(entry,field) for field in FIELDS}
        saved=save_manual_entry(schedule_id=self.draft.pk,entry_id=entry.pk,actor=self.admin,
            revision=revision_token(self.draft,self.admin,entry),proposed=proposed,
            education_level='TERTIARY',term_id=self.ter.pk)
        self.assertEqual(saved.room_id,entry.room_id)
        self.assertEqual(saved.effective_faculty.pk,self.faculty.pk)
        original=self.original.entries.get()
        with self.assertRaises(ValidationError):
            save_manual_entry(schedule_id=self.original.pk,entry_id=original.pk,actor=self.admin,
                revision=revision_token(self.original,self.admin,original),proposed=proposed)
