"""Shared database-backed academic list search and page navigation."""
from django.core.paginator import Paginator
from types import SimpleNamespace

from django.db.models import Q, Count, Value, CharField, F
from django.db.models.functions import Cast, Concat
from django.http import QueryDict

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

# All lookup paths are application-owned. URL values never become ORM field names.
EXTRA_SORTS = {
    'departments': [('name', 'Name', ('name',))],
    'programs': [('department', 'Department', ('department__code',))],
    'year-levels': [('level', 'Year level', ('level',))],
    'faculty': [('department', 'Department', ('department__code',))],
    'rooms': [('capacity', 'Capacity', ('capacity',)), ('type', 'Room type', ('room_type',)), ('active', 'Active status', ('is_active',))],
    'subjects': [('department', 'Department', ('department__code',)), ('units', 'Units', ('units',))],
    'sections': [('name', 'Section name', ('name',)), ('program', 'Program', ('program__code',)), ('year', 'Year level', ('year_level__level',))],
    'students': [('section', 'Section', ('section__program__code', 'section__year_level__level', 'section__name'))],
    'terms': [('start', 'Term start', ('starts_on',)), ('end', 'Term end', ('ends_on',))],
    'faculty-credentials': [('issued', 'Issue date', ('issued_on',)), ('expires', 'Expiration date', ('expires_on',))],
    'availability': [('day', 'Day', ('day',)), ('start', 'Start time', ('start_time',))],
    'schedules': [('term', 'Academic term', ('term__school_year', 'term__name')), ('status', 'Status', ('status',))],
}

# parameter, lookup; choices/labels are shared below.
FILTERS = {
    'programs': [('department', 'department_id')],
    'faculty': [('department', 'department_id')],
    'subjects': [('department', 'department_id'), ('room_type', 'required_room_type')],
    'sections': [('program', 'program_id'), ('year', 'year_level_id')],
    'students': [('program', 'section__program_id'), ('year', 'section__year_level_id')],
    'rooms': [('room_type', 'room_type'), ('active', 'is_active')],
    'terms': [('active', 'is_active')],
    'assignments': [('term', 'term_id'), ('department', 'subject__department_id'), ('program', 'section__program_id'), ('year', 'section__year_level_id')],
    'schedules': [('term', 'term_id'), ('status', 'status')],
    'faculty-credentials': [('department', 'faculty__department_id'), ('credential', 'credential_id')],
    'subject-credential-requirements': [('department', 'subject__department_id'), ('credential', 'required_credential_id')],
    'credential-overrides': [('department', 'faculty__department_id')],
    'availability': [('day', 'day'), ('kind', 'kind')],
}


def list_request(request, resource):
    """Canonical list navigation: one value per supported parameter only."""
    allowed = {'q', 'sort', 'page'} | {key for key, _ in FILTERS.get(resource, ())}
    if resource == 'schedules':
        allowed.add('tab')
    params = QueryDict(mutable=True)
    for key in request.GET:
        if key in allowed:
            params[key] = request.GET[key]
    return SimpleNamespace(GET=params)


def filter_records(queryset, resource, params):
    """Validate against admin-visible options, then filter in SQL.

    The caller must enforce the existing administrator-only permission first.
    Admins may see all academic records. UNION fetches FK choices in one query,
    regardless of the number of controls, without fetching related model objects.
    """
    from schedules import models as m
    definitions = FILTERS.get(resource, ())
    sources = {
        'department': ('Department', m.Department, Concat('code', Value(' — '), 'name')),
        'program': ('Program', m.Program, Concat('code', Value(' — '), 'name')),
        'year': ('Year level', m.YearLevel, Concat(Cast('level', CharField()), Value(' — '), 'label')),
        'term': ('Academic term', m.AcademicTerm, Concat('name', Value(' '), 'school_year')),
        'credential': ('Credential', m.Credential, F('name')),
    }
    choices = {
        'room_type': ('Room type', m.RoomKind.choices),
        'active': ('Active status', [('1', 'Active'), ('0', 'Inactive')]),
        'status': ('Schedule status', m.ScheduleStatus.choices),
        'day': ('Day', m.Weekday.choices),
        'kind': ('Availability kind', m.AvailabilityKind.choices),
    }
    option_queries = []
    options = {}
    for key, _ in definitions:
        if key in sources:
            label, model, expression = sources[key]
            options[key] = []
            option_queries.append(model.objects.order_by().annotate(
                option_group=Value(key, output_field=CharField()),
                option_value=Cast('pk', CharField()), option_label=expression,
            ).values_list('option_group', 'option_value', 'option_label'))
        else:
            options[key] = [(str(value), label) for value, label in choices[key][1]]
    if option_queries:
        combined = option_queries[0].union(*option_queries[1:], all=True) if len(option_queries) > 1 else option_queries[0]
        for key, value, label in combined:
            options[key].append((value, label))
        for key in sources.keys() & options.keys():
            options[key].sort(key=lambda item: (item[1].casefold(), item[0]))
    controls, errors = [], []
    for key, lookup in definitions:
        value = params.get(key, '')
        label = sources[key][0] if key in sources else choices[key][0]
        invalid = bool(value) and value not in {item[0] for item in options[key]}
        if invalid:
            errors.append(f'{label}: This selection is no longer available. Choose another option or select All.')
            queryset = queryset.none()
        elif value:
            queryset = queryset.filter(**{lookup: value == '1' if key == 'active' else value})
        controls.append(dict(name=key, label=label, value=value, options=options[key], invalid=invalid))
    return queryset, controls, errors


def record_counts(scope, filtered, narrowed):
    """Count both sets in one round trip; reuse matches for the paginator."""
    if not narrowed:
        total = scope.count()
        return total, total
    counts = scope.aggregate(total=Count('pk'), matching=Count('pk', filter=Q(pk__in=filtered.order_by().values('pk'))))
    return counts['total'], counts['matching']


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
