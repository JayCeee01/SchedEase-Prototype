"""Explicit academic context. Callers must supply already-authorized terms.

This narrows permissions; it never creates them. No session/global selection.
"""
from dataclasses import dataclass
from urllib.parse import urlencode

from django.core.exceptions import PermissionDenied
from django.http import Http404

LEVELS = (('TERTIARY', 'Tertiary'), ('SHS', 'SHS'), ('COMBINED', 'Combined'))


@dataclass(frozen=True)
class EducationContext:
    level: str
    term_id: int | None
    explicit: bool

    @property
    def query(self):
        if not self.explicit:
            return ''
        values = {'education_level': self.level}
        if self.term_id:
            values['term'] = self.term_id
        return '?' + urlencode(values)

    @property
    def choices(self):
        return LEVELS

    def scope(self, queryset, term_path='term'):
        if self.level != 'COMBINED':
            queryset = queryset.filter(**{term_path + '__education_level': self.level})
        if self.term_id:
            queryset = queryset.filter(**{term_path + '_id': self.term_id})
        return queryset


def resolve_context(request, terms, *, write=False):
    data = request.POST if request.method == 'POST' else request.GET
    for key in ('education_level', 'term'):
        if len(data.getlist(key)) > 1:
            raise Http404('Specify one academic context.')
        if request.method == 'POST' and key in request.GET and request.GET[key] != data.get(key):
            raise Http404('The submitted academic context differs from the displayed context.')
    selected = data.get('education_level', '')
    if selected and selected not in dict(LEVELS):
        raise Http404('Unknown education level.')
    levels = set(terms.values_list('education_level', flat=True).distinct())
    raw_term = data.get('term', '')
    term = None
    if raw_term:
        if not raw_term.isascii() or not raw_term.isdecimal() or len(raw_term) > 18:
            raise Http404('Invalid academic term.')
        term = terms.filter(pk=int(raw_term)).first()
        if term is None:
            raise Http404('Academic term is unavailable.')
    level = selected or (term.education_level if term else next(iter(levels)) if len(levels) == 1 else 'COMBINED')
    if term and level != 'COMBINED' and term.education_level != level:
        raise Http404('The academic term does not belong to this education level.')
    if write and (level == 'COMBINED' or term is None or (len(levels) > 1 and not selected)):
        raise PermissionDenied('Choose an explicit education level and academic term before generating a schedule.')
    return EducationContext(level, term.pk if term else None, bool(selected))


def generation_scope_valid(term):
    """Do not pass mismatched academic assignments into either engine adapter."""
    return not term.assignment_set.exclude(section__program__education_level=term.education_level).exists()
