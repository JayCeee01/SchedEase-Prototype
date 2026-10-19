"""Shared database-backed academic list search and page navigation."""
from django.core.paginator import Paginator
from django.db.models import Q

SEARCH = {
    'departments': ('code', 'name'), 'programs': ('code', 'name', 'department__code', 'department__name'),
    'year-levels': ('label',), 'sections': ('name', 'program__code', 'program__name', 'year_level__label'),
    'subjects': ('code', 'title'), 'credentials': ('name',),
    'faculty-credentials': ('faculty__full_name', 'faculty__employee_id', 'credential__name'),
    'subject-credential-requirements': ('subject__code', 'subject__title', 'required_credential__name', 'acceptable_equivalents__name'),
    'faculty': ('full_name', 'employee_id'), 'students': ('full_name', 'student_number', 'section__name', 'section__program__code'),
    'rooms': ('name', 'room_type'), 'terms': ('name', 'school_year'),
    'assignments': ('subject__code', 'subject__title', 'section__name', 'section__program__code', 'faculty__full_name', 'faculty__employee_id', 'term__name', 'term__school_year'),
    'availability': ('faculty__full_name', 'faculty__employee_id', 'room__name', 'kind'),
    'ga-settings': ('name',), 'schedules': ('name', 'term__name', 'term__school_year', 'status'),
    'credential-overrides': ('faculty__full_name', 'faculty__employee_id', 'subject__code', 'subject__title'),
}
RELATED = {
    'programs': ('department',), 'sections': ('program', 'year_level'),
    'faculty-credentials': ('faculty', 'credential'),
    'subject-credential-requirements': ('subject', 'required_credential'),
    'students': ('section__program', 'section__year_level'),
    'availability': ('faculty', 'room'), 'schedules': ('term',),
    'credential-overrides': ('faculty', 'subject'),
    'assignments': ('subject', 'section__program', 'section__year_level', 'faculty', 'term'),
}
RECORD_ORDER = {
    'departments': ('code', 'name'), 'programs': ('code', 'name'), 'year-levels': ('label',),
    'sections': ('program__code', 'year_level__level', 'name'), 'credentials': ('name',),
    'faculty-credentials': ('faculty__full_name', 'credential__name'),
    'subject-credential-requirements': ('subject__code', 'required_credential__name'),
    'faculty': ('full_name',), 'students': ('full_name',), 'rooms': ('name', 'room_type'),
    'terms': ('name', 'school_year'), 'availability': ('pk',), 'ga-settings': ('name',),
    'schedules': ('name',), 'credential-overrides': ('faculty__full_name', 'subject__code'),
}


def query_url(request, **changes):
    params = request.GET.copy()
    for key, value in changes.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    return '?' + params.urlencode()


def paginate(request, queryset, parameter='page', *, count=None):
    paginator = Paginator(queryset, 20)
    if count is not None:
        # Reuse an existing filtered summary count instead of repeating COUNT(*).
        paginator.count = count
    value = request.GET.get(parameter, '1')
    try:
        value = max(1, int(value))
    except (ValueError, TypeError):
        value = 1
    page = paginator.get_page(value)
    numbers = []
    for number in paginator.get_elided_page_range(page.number, on_each_side=2, on_ends=1):
        numbers.append({'number': number, 'url': None if number == paginator.ELLIPSIS
                        else query_url(request, **{parameter: number})})
    return page, dict(page=page, numbers=numbers,
        previous=query_url(request, **{parameter: page.previous_page_number()}) if page.has_previous() else None,
        next=query_url(request, **{parameter: page.next_page_number()}) if page.has_next() else None)


def search_records(queryset, resource, text, section_search):
    if not text:
        return queryset
    query = Q()
    for field in SEARCH[resource]:
        query |= Q(**{field + '__icontains': text})
    prefix = {'sections': '', 'assignments': 'section__', 'students': 'section__'}.get(resource)
    if prefix is not None:
        query |= section_search(prefix, text)
    if resource == 'year-levels' and text.isdigit() and len(text) < 10:
        query |= Q(level=int(text))
    if resource in ('rooms', 'availability'):
        from schedules.models import RoomKind, Weekday
        field, choices = ('room_type', RoomKind.choices) if resource == 'rooms' else ('day', Weekday.choices)
        query |= Q(**{field + '__in': [value for value, label in choices if text.casefold() in label.casefold()]})
    result = queryset.filter(query)
    return result.distinct() if resource == 'subject-credential-requirements' else result
