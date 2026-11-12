"""In-app notifications committed atomically with authorized publication."""
from django.contrib.auth import get_user_model
from schedules.models import Faculty, Student, ScheduleNotification, ScheduleStatus


def scope_for(user):
    from schedules.views import role
    if role(user) == 'FACULTY':
        pk = Faculty.objects.filter(user=user).values_list('pk', flat=True).first()
        return f'FACULTY:{pk}' if pk else None
    if role(user) == 'STUDENT':
        pk = Student.objects.filter(user=user).values_list('section_id', flat=True).first()
        return f'STUDENT:{pk}' if pk else None
    return None


def recipients(schedule):
    from schedules.views import entries_visible_to_user
    if not schedule:
        return {}
    entries = schedule.entries.filter(schedule__status=ScheduleStatus.PUBLISHED)
    result = {}
    for user in get_user_model().objects.filter(is_active=True, is_superuser=False):
        scope = scope_for(user)
        if scope and entries_visible_to_user(entries, user).exists():
            result[user.pk] = scope
    return result


def record_publication(schedule, previous, old_recipients):
    current = recipients(schedule)
    for user_id, scope in current.items():
        ScheduleNotification.objects.get_or_create(user_id=user_id, schedule=schedule,
            kind='UPDATED' if user_id in old_recipients else 'NEW', defaults={
                'scope': scope, 'schedule_name': schedule.name, 'term_label': str(schedule.term)})
    if previous:
        for user_id in old_recipients.keys() - current.keys():
            ScheduleNotification.objects.get_or_create(user_id=user_id, schedule=previous, kind='WITHDRAWN',
                defaults={'scope': old_recipients[user_id], 'schedule_name': previous.name, 'term_label': str(previous.term)})


def visible_notifications(user):
    from schedules.views import entries_visible_to_user
    scope = scope_for(user)
    if not scope:
        return []
    allowed, result = {}, []
    for notice in ScheduleNotification.objects.filter(user=user, scope=scope).select_related('schedule'):
        if notice.kind == 'WITHDRAWN':
            result.append(notice)
            continue
        if notice.schedule_id not in allowed:
            allowed[notice.schedule_id] = entries_visible_to_user(
                notice.schedule.entries.filter(schedule__status=ScheduleStatus.PUBLISHED), user).exists()
        if allowed[notice.schedule_id]:
            result.append(notice)
    return result


def notification_context(user, page=1):
    notices = visible_notifications(user)
    from django.core.paginator import Paginator
    return {'notifications': Paginator(notices, 10).get_page(page),
            'notification_unread': sum(n.read_at is None for n in notices)}
