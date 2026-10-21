from django import forms
from .models import ScheduleConcern, Role, ScheduleEntry
from .services.concerns import authorized_entries, authorized_schedules


class EntryChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.effective_subject.code} / {obj.effective_section} - {obj.get_day_display()} {obj.start_time:%H:%M} ({obj.schedule.name})'


class ConcernForm(forms.Form):
    schedule = forms.ModelChoiceField(queryset=None, label='Published schedule')
    entry = EntryChoice(queryset=ScheduleEntry.objects.none(), required=False, label='Affected class (optional)',
                       help_text='Choose a class from the selected schedule. Leave blank for a missing subject or a schedule-wide concern.')
    category = forms.ChoiceField(choices=ScheduleConcern.Category.choices)
    description = forms.CharField(min_length=10, max_length=3000, widget=forms.Textarea(attrs={'rows': 5}),
                                  help_text='Explain the scheduling issue in 10-3000 characters.')

    def __init__(self, *args, user, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['schedule'].queryset = authorized_schedules(user).select_related('term')
        self.fields['entry'].queryset = authorized_entries(user).select_related(
            'schedule', 'assignment__subject', 'assignment__section__program', 'assignment__section__year_level',
            'subject_override', 'section_override__program', 'section_override__year_level')

    def clean(self):
        data = super().clean()
        if data.get('entry') and data.get('schedule') and data['entry'].schedule_id != data['schedule'].pk:
            self.add_error('entry', 'Choose a class from the selected schedule.')
        return data


class ReviewForm(forms.Form):
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    status = forms.ChoiceField(choices=ScheduleConcern.Status.choices)
    response = forms.CharField(max_length=3000, required=False, widget=forms.Textarea(attrs={'rows': 5}),
                               label='Administrator response', help_text='This response is visible to the reporter.')


class ConcernFilters(forms.Form):
    status = forms.ChoiceField(required=False, choices=[('', 'All statuses'), *ScheduleConcern.Status.choices])
    category = forms.ChoiceField(required=False, choices=[('', 'All categories'), *ScheduleConcern.Category.choices])
    reporter_role = forms.ChoiceField(required=False, choices=[('', 'All reporter roles'), (Role.STUDENT, 'Student'), (Role.FACULTY, 'Faculty')])
