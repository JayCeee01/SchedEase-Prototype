"""Render real admin GET pages with synthetic records in an in-memory database only."""
from pathlib import Path
import os
import re
import sys
from html.parser import HTMLParser

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sched_ease.settings')
from django.conf import settings
settings.DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
settings.ALLOWED_HOSTS = ['testserver']
settings.SECURE_SSL_REDIRECT = False
import django
django.setup()
from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from schedules.models import AcademicTerm, Schedule, Room
assert settings.DATABASES['default']['NAME'] == ':memory:'
call_command('migrate', verbosity=0)
user = get_user_model().objects.create_superuser('responsive-admin', 'fixture@example.invalid', 'fixture-only')
term = AcademicTerm.objects.create(name='First semester', school_year='2026', starts_on='2026-01-01', ends_on='2026-06-01', is_active=True)
schedule = Schedule.objects.create(name='Responsive draft', term=term)
room = Room.objects.create(name='Computer laboratory', room_type='LECTURE', capacity=40)
client = Client()
client.force_login(user)
routes = [(name, {}) for name in ['dashboard','generate_schedule','room_utilization','room_schedule','room_capacity_planning','generation_error_log','academic_import']]
routes += [('resource_list', {'resource': resource}) for resource in ['subjects','faculty','students','rooms','credentials','assignments','availability','departments','programs','sections']]
routes += [('resource_create', {'resource': resource}) for resource in ['subjects','assignments']]
routes += [('resource_delete', {'resource':'rooms','pk':room.pk}), ('schedule_detail', {'pk':schedule.pk})]
class Content(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.depth = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag == 'section' and (self.depth or ('class','content') in attrs):
            self.depth += 1
        if self.depth: self.parts.append(self.get_starttag_text())
    def handle_endtag(self, tag):
        if self.depth:
            self.parts.append('</'+tag+'>')
            if tag == 'section': self.depth -= 1
    def handle_data(self, data):
        if self.depth: self.parts.append(data)
    def handle_entityref(self, name):
        if self.depth: self.parts.append('&'+name+';')
    def handle_charref(self, name):
        if self.depth: self.parts.append('&#'+name+';')
sections=[]
for name, kwargs in routes:
    response=client.get(reverse(name,kwargs=kwargs))
    assert response.status_code == 200, (name,kwargs,response.status_code)
    parser=Content();parser.feed(response.content.decode())
    sections.append('<div data-page="'+name+str(kwargs).replace('"','')+'">'+''.join(parser.parts)+'</div>')
base=(root/'tests/browser/responsive_layout.html').read_text()
head=base[:base.index('<section class="content">')].replace('</head>', '<link rel="stylesheet" href="../../static/css/academic-import.css"></head>')
script='''<pre id="results">RUNNING</pre></div></div><script src="../../static/js/app.js"></script><script src="../../static/js/table-scroll.js"></script><script>
setTimeout(()=>{const errors=[];for(const page of document.querySelectorAll('[data-page]'))if(page.scrollWidth>page.clientWidth+1)errors.push(page.dataset.page);
const n=document.querySelectorAll('[data-page]').length;document.querySelector('#results').textContent=errors.length?'FAIL overflow: '+errors.join(', '):'PASS '+n+' rendered pages\\nviewport width '+innerWidth;},500);
</script></body></html>'''
(root/'tests/browser/rendered_responsive.html').write_text(head+''.join(sections)+script,encoding='utf-8')
print('Rendered',len(sections),'authenticated admin pages using isolated in-memory records.')
