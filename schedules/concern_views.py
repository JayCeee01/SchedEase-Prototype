from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods
from .models import ScheduleConcern
from .views import admin_required
from .concern_forms import ConcernForm, ReviewForm, ConcernFilters
from .services.concerns import reporter_allowed, authorized_schedules, submit_concern, review_concern


def concern_user(user):
    return admin_required(user) or reporter_allowed(user)


@login_required
@user_passes_test(concern_user)
@require_http_methods(['GET'])
def concern_list(request):
    administrative = admin_required(request.user)
    rows = ScheduleConcern.objects.select_related('reporter')
    filters = ConcernFilters(request.GET)
    if not administrative:
        rows = rows.filter(reporter=request.user)
    if filters.is_valid():
        for key, value in filters.cleaned_data.items():
            if value:
                rows = rows.filter(**{key: value})
    else:
        rows = rows.none()
    page = Paginator(rows, 20).get_page(request.GET.get('page'))
    query = request.GET.copy()
    query.pop('page', None)
    return render(request, 'schedules/concerns/list.html', {'page_obj': page, 'filters': filters,
        'admin_review': administrative, 'filter_query': query.urlencode()})


@login_required
@user_passes_test(reporter_allowed)
@require_http_methods(['GET', 'POST'])
def concern_create(request):
    form = ConcernForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        try:
            concern = submit_concern(actor=request.user, schedule_id=form.cleaned_data['schedule'].pk,
                entry_id=getattr(form.cleaned_data['entry'], 'pk', None),
                category=form.cleaned_data['category'], description=form.cleaned_data['description'])
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Concern submitted. You can track the administrator response here.')
            return redirect('concern_detail', pk=concern.pk)
    return render(request, 'schedules/concerns/form.html', {'form': form,
        'has_schedules': form.fields['schedule'].queryset.exists()})


@login_required
@user_passes_test(concern_user)
@require_http_methods(['GET', 'POST'])
def concern_detail(request, pk):
    administrative = admin_required(request.user)
    rows = ScheduleConcern.objects.select_related('reporter', 'reviewed_by')
    if not administrative:
        rows = rows.filter(reporter=request.user)
    concern = get_object_or_404(rows, pk=pk)
    if request.method == 'POST' and not administrative:
        raise PermissionDenied
    form = ReviewForm(request.POST or None, initial={'revision': concern.revision,
                      'status': concern.status, 'response': concern.response}) if administrative else None
    if request.method == 'POST' and form.is_valid():
        try:
            review_concern(actor=request.user, pk=concern.pk, **form.cleaned_data)
        except ValidationError as exc:
            form.add_error(None, exc)
        else:
            messages.success(request, 'Review saved. Scheduling records have not been changed.')
            return redirect('concern_detail', pk=pk)
    can_open_schedule = bool(concern.schedule_id and (administrative or
        authorized_schedules(request.user).filter(pk=concern.schedule_id).exists()))
    return render(request, 'schedules/concerns/detail.html', {'concern': concern, 'form': form,
        'admin_review': administrative, 'can_open_schedule': can_open_schedule,
        'reviews': concern.reviews.select_related('administrator') if administrative else []})
