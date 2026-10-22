"""Task 8.3: alternate admin paths, publication authorization and safe methods."""
from datetime import time
import json
from django.contrib import admin
from django.contrib.auth.models import Permission, User
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory
from django.urls import reverse
from . import models as m
from .test_known_defects import SchedulingDefectFixture


class AdminPublicationSecurityTests(SchedulingDefectFixture):
    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.superuser = User.objects.create_superuser(username='audit-root', password='synthetic-only')
        cls.staff = User.objects.create_user(username='audit-staff', is_staff=True)
        cls.staff.user_permissions.set(Permission.objects.all())
        cls.staff_profile = m.Profile.objects.create(user=cls.staff, role=m.Role.STUDENT)
        cls.administrator = User.objects.create_user(username='audit-admin', is_staff=True)
        m.Profile.objects.create(user=cls.administrator, role=m.Role.ADMIN)
        cls.administrator.user_permissions.set(Permission.objects.filter(content_type__app_label='schedules'))
        cls.draft = m.Schedule.objects.create(term=cls.term, name='Synthetic private draft')
        cls.entries = [cls.draft.entries.create(assignment=meeting, room=cls.room, day=0,
            start_time=time(8+i), end_time=time(9+i)) for i, meeting in enumerate(cls.meetings)]
        cls.generation_run = m.GenerationRun.objects.create(term=cls.term, requested_name='Synthetic interrupted')
        cls.faculty_user=User.objects.create_user(username='audit-faculty',is_staff=True)
        m.Profile.objects.create(user=cls.faculty_user,role=m.Role.FACULTY)
        cls.faculty.user=cls.faculty_user
        cls.faculty.save(update_fields=['user'])
        cls.student_user=User.objects.create_user(username='audit-student')
        m.Profile.objects.create(user=cls.student_user,role=m.Role.STUDENT)
        m.Student.objects.create(user=cls.student_user,section=cls.section,student_number='AUDIT',full_name='Synthetic Student')
        cls.plain=User.objects.create_user(username='audit-plain')

    def test_staff_cannot_read_academic_admin_even_with_model_permissions(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('admin:schedules_faculty_changelist')).status_code,403)

    def test_staff_cannot_promote_own_profile(self):
        self.client.force_login(self.staff)
        response=self.client.post(reverse('admin:schedules_profile_change',args=[self.staff_profile.pk]),
            {'user':self.staff.pk,'role':'ADMIN','_save':'Save'})
        self.assertEqual(response.status_code,403)
        self.staff_profile.refresh_from_db()
        self.assertEqual(self.staff_profile.role,'STUDENT')

    def test_admin_status_payload_cannot_bypass_publication(self):
        self.client.force_login(self.superuser)
        self.client.post(reverse('admin:schedules_schedule_change',args=[self.draft.pk]),
            {'term':self.term.pk,'name':self.draft.name,'status':'PUBLISHED','fitness_score':0,'origin':'MANUAL','_save':'Save'})
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status,'DRAFT')
        self.assertFalse(m.ScheduleSnapshot.objects.filter(schedule=self.draft).exists())

    def test_error_log_get_does_not_recover_runs(self):
        self.client.force_login(self.superuser)
        self.assertEqual(self.client.get(reverse('generation_error_log')).status_code,200)
        self.generation_run.refresh_from_db()
        self.assertEqual(self.generation_run.status,'RUNNING')
        self.assertFalse(self.generation_run.issues.exists())

    def test_every_registered_model_requires_role_as_well_as_permissions(self):
        self.faculty_user.user_permissions.set(Permission.objects.all())
        for user in (self.staff,self.faculty_user):
            request=RequestFactory().get('/admin/')
            request.user=user
            for model, model_admin in admin.site._registry.items():
                with self.subTest(model=model.__name__,user=user.username):
                    self.assertFalse(model_admin.has_module_permission(request))
                    self.assertFalse(model_admin.has_view_permission(request))
                    self.assertFalse(model_admin.has_add_permission(request))
                    self.assertFalse(model_admin.has_change_permission(request))
                    self.assertFalse(model_admin.has_delete_permission(request))

    def test_direct_auth_urls_cannot_promote_staff_or_change_other_passwords(self):
        self.client.force_login(self.staff)
        for name,args in [('auth_user_change',[self.staff.pk]),('auth_user_add',[]),
                          ('auth_group_add',[]),('auth_user_password_change',[self.superuser.pk])]:
            url=reverse('admin:'+name,args=args)
            for method in (self.client.get,self.client.post):
                self.assertEqual(method(url,{'is_superuser':'on','is_staff':'on','password1':'forged','password2':'forged'}).status_code,403)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_superuser)

    def test_django_permissions_remain_required_for_role_administrators(self):
        self.administrator.user_permissions.clear()
        self.client.force_login(self.administrator)
        self.assertEqual(self.client.get(reverse('admin:schedules_room_changelist')).status_code,403)
        self.administrator.user_permissions.add(Permission.objects.get(codename='view_room'))
        self.assertEqual(self.client.get(reverse('admin:schedules_room_changelist')).status_code,200)
        self.assertEqual(self.client.post(reverse('admin:schedules_room_change',args=[self.room.pk]),{}).status_code,403)

    def test_authorized_academic_admin_edit_remains_available(self):
        self.client.force_login(self.administrator)
        response=self.client.post(reverse('admin:schedules_room_change',args=[self.room.pk]),
            {'name':'Updated synthetic room','capacity':30,'room_type':'LECTURE','is_active':'on','_save':'Save'})
        self.assertEqual(response.status_code,302)
        self.room.refresh_from_db()
        self.assertEqual(self.room.name,'Updated synthetic room')
        self.administrator.is_staff=False
        self.administrator.save(update_fields=['is_staff'])
        self.assertEqual(self.client.get(reverse('generate_schedule')).status_code,200)
        self.assertEqual(self.client.get(reverse('admin:index')).status_code,302)

    def test_direct_admin_entries_and_audits_are_read_only(self):
        audit=m.ScheduleEntryAudit.objects.create(schedule=self.draft,entry=self.entries[0],user=self.superuser,
            previous_values={},new_values={'day':0})
        self.client.force_login(self.superuser)
        for model,pk in [('scheduleentry',self.entries[0].pk),('scheduleentryaudit',audit.pk)]:
            self.assertEqual(self.client.get(reverse(f'admin:schedules_{model}_change',args=[pk])).status_code,200)
            for action,args in [('add',[]),('change',[pk]),('delete',[pk])]:
                self.assertEqual(self.client.post(reverse(f'admin:schedules_{model}_{action}',args=args),
                    {'day':2,'user':self.staff.pk,'new_values':'{}','post':'yes'}).status_code,403)
            response=self.client.post(reverse(f'admin:schedules_{model}_changelist'),
                {'action':'delete_selected','_selected_action':[pk],'post':'yes'})
            self.assertIn(response.status_code,(200,302))
        audit.refresh_from_db()
        self.assertEqual(audit.new_values,{'day':0})
        self.assertTrue(m.ScheduleEntry.objects.filter(pk=self.entries[0].pk).exists())

    def test_override_approval_actor_cannot_be_forged_in_either_interface(self):
        self.client.force_login(self.administrator)
        payload={'subject':self.subject.pk,'faculty':self.faculty.pk,'reason':'Synthetic authorized exception',
                 'missing_credentials':'Synthetic test','admin_user':self.superuser.pk}
        for url in (reverse('resource_create',args=['credential-overrides']),reverse('admin:schedules_credentialoverride_add')):
            response=self.client.post(url,payload)
            self.assertEqual(response.status_code,302)
            record=m.CredentialOverride.objects.latest('pk')
            self.assertEqual(record.admin_user_id,self.administrator.pk)
        self.client.force_login(self.superuser)
        response=self.client.post(reverse('resource_update',args=['credential-overrides',record.pk]),
                                  {**payload,'reason':'Updated reason','admin_user':self.staff.pk})
        self.assertEqual(response.status_code,302)
        record.refresh_from_db()
        self.assertEqual(record.admin_user_id,self.administrator.pk)

    def test_recovery_requires_csrf_and_authorized_post(self):
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.administrator)
        url=reverse('generation_error_log')
        client.get(url)
        self.assertEqual(client.post(url,{'action':'recover'}).status_code,403)
        token=client.cookies['csrftoken'].value
        self.assertEqual(client.post(url,{'action':'recover','csrfmiddlewaretoken':token}).status_code,302)
        self.generation_run.refresh_from_db()
        self.assertEqual(self.generation_run.status,'FAILED')
        self.assertEqual(self.generation_run.issues.count(),1)
        other=m.GenerationRun.objects.create(term=self.term,requested_name='Other interrupted')
        client.force_login(self.staff)
        self.assertEqual(client.post(url,{'action':'recover','csrfmiddlewaretoken':token}).status_code,302)
        other.refresh_from_db()
        self.assertEqual(other.status,'RUNNING')

    def test_role_matrix_for_direct_administrative_endpoints(self):
        urls=[reverse(name,args=args) for name,args in [
            ('resource_list',['faculty']),('resource_create',['rooms']),('resource_update',['rooms',self.room.pk]),
            ('resource_delete',['rooms',self.room.pk]),('generate_schedule',[]),('generation_error_log',[]),
            ('generation_run_detail',[self.generation_run.pk]),('room_utilization',[]),('room_utilization_csv',[]),
            ('room_utilization_pdf',[]),('room_schedule',[]),('room_capacity_planning',[]),
            ('entry_create',[self.draft.pk]),('entry_update',[self.draft.pk,self.entries[0].pk]),
            ('publish_schedule',[self.draft.pk]),('copy_schedule_to_draft',[self.draft.pk]),
            ('entry_remove',[self.draft.pk,self.entries[0].pk]),('entry_apply_suggestion',[self.draft.pk,self.entries[0].pk]),
            ('save_form_draft',[]),('discard_form_draft',[999999])]]
        for user in (None,self.plain,self.faculty_user,self.student_user,self.staff):
            self.client.force_login(user) if user else self.client.logout()
            for url in urls:
                for method in (self.client.get,self.client.post):
                    with self.subTest(user=getattr(user,'username','anonymous'),url=url):
                        response=method(url)
                        self.assertEqual(response.status_code,302)
                        self.assertNotIn(b'Synthetic private draft',response.content)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status,'DRAFT')
        self.assertEqual(self.draft.entries.count(),2)

    def test_publication_post_csrf_validation_and_atomic_service_authorization(self):
        from .services.publication import publish
        updated=self.draft.updated_at
        with self.assertRaises(ValidationError):
            publish(self.draft,self.staff)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.updated_at,updated)
        self.assertEqual(self.draft.edit_audits.count(),0)
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.administrator)
        client.get(reverse('schedule_detail',args=[self.draft.pk]))
        url=reverse('publish_schedule',args=[self.draft.pk])
        self.assertEqual(client.get(url).status_code,405)
        self.assertEqual(client.post(url).status_code,403)
        self.assertEqual(client.post(url,{'csrfmiddlewaretoken':client.cookies['csrftoken'].value}).status_code,302)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status,'PUBLISHED')
        self.assertTrue(m.ScheduleSnapshot.objects.filter(schedule=self.draft).exists())
        self.assertEqual(self.draft.edit_audits.count(),1)

    def test_invalid_schedule_cannot_publish_and_admin_cannot_set_new_state(self):
        from .services.publication import publish
        self.entries[1].delete()
        with self.assertRaises(ValidationError):
            publish(self.draft,self.administrator)
        self.client.force_login(self.superuser)
        for status in ('APPROVED','PUBLISHED','ARCHIVED'):
            self.client.post(reverse('admin:schedules_schedule_add'),
                {'term':self.term.pk,'name':'Forged '+status,'status':status,'fitness_score':0,'origin':'GENERATED'})
            record=m.Schedule.objects.get(name='Forged '+status)
            self.assertEqual(record.status,'DRAFT')
            self.assertEqual(record.origin,'MANUAL')
        self.assertFalse(m.ScheduleSnapshot.objects.exists())

    def test_timetable_exports_and_history_follow_object_scope(self):
        from .services.publication import publish
        publish(self.draft,self.superuser)
        for user in (self.faculty_user,self.student_user,self.plain,self.staff,None):
            self.client.force_login(user) if user else self.client.logout()
            for name in ('schedule_detail','export_csv','export_pdf'):
                response=self.client.get(reverse(name,args=[self.draft.pk]))
                expected=200 if user in (self.faculty_user,self.student_user) else (302 if user is None else 404)
                self.assertEqual(response.status_code,expected)
        self.client.force_login(self.administrator)
        self.client.post(reverse('copy_schedule_to_draft',args=[self.draft.pk]))
        copy=m.Schedule.objects.exclude(pk=self.draft.pk).get()
        self.client.force_login(self.student_user)
        for name in ('schedule_detail','export_csv','export_pdf'):
            self.assertEqual(self.client.get(reverse(name,args=[copy.pk])).status_code,404)
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.status,'PUBLISHED')

    def test_json_draft_csrf_and_privileged_fields_are_not_accepted(self):
        client=Client(enforce_csrf_checks=True)
        client.force_login(self.administrator)
        client.get(reverse('resource_create',args=['schedules']))
        url=reverse('save_form_draft')
        payload=json.dumps({'resource':'schedules','changed':True,'payload':{'name':'Synthetic','status':'PUBLISHED','is_superuser':True}})
        self.assertEqual(client.get(url).status_code,405)
        self.assertEqual(client.post(url,payload,content_type='application/json').status_code,403)
        response=client.post(url,payload,content_type='application/json',HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value)
        self.assertEqual(response.status_code,200)
        saved=m.FormDraft.objects.get(user=self.administrator)
        self.assertEqual(saved.payload,{'name':'Synthetic'})
        client.force_login(self.staff)
        self.assertEqual(client.post(url,payload,content_type='application/json',HTTP_X_CSRFTOKEN=client.cookies['csrftoken'].value).status_code,302)

    def test_no_public_backup_route_and_no_snapshot_admin_registration(self):
        self.assertNotIn(m.ScheduleSnapshot,admin.site._registry)
        for path in ('/backups/test.sqlite3','/media/test.sqlite3','/schedules/snapshots/1/'):
            self.assertEqual(self.client.get(path).status_code,404)

