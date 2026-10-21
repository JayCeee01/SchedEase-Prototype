"""Render a populated Student response using disposable in-memory records only."""
from pathlib import Path
import os
import sys
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
from django.test import Client
from schedules.test_student_timetable import StudentTimetableTests
from schedules.services.publication import publish
call_command('migrate', verbosity=0)
if '--faculty' in sys.argv:
    from schedules.test_faculty_timetable import FacultyTimetableTests
    fixture_class = FacultyTimetableTests
else:
    fixture_class = StudentTimetableTests
fixture_class.setUpTestData()
case = fixture_class()
case.client = Client()
case.setUp()
publish(case.schedule, case.admin)
case.login()
response = case.client.get('/dashboard/')
assert response.status_code == 200
html = response.content.decode().replace('/static/', (root/'static').as_uri()+'/')
html = html.replace('<head>', '''<head><script>
localStorage.setItem('schedease-theme',new URLSearchParams(location.search).get('theme')||'light');
</script>''')
script = '''<pre id="results" style="position:fixed;bottom:0;left:0;z-index:9999;font-size:10px">RUNNING</pre>
<script>setTimeout(async()=>{
const errors=[];let checks=0;const check=(ok,text)=>{checks++;if(!ok)errors.push(text)};
const theme=new URLSearchParams(location.search).get('theme');
check(document.documentElement.dataset.theme===theme,'requested theme');
check(document.documentElement.scrollWidth<=innerWidth+1,'no horizontal page overflow');
const wrap=document.querySelector('.personal-timetable-wrap'), slot=document.querySelector('.personal-class-slot');
check(!!wrap&&!!slot,'populated Django timetable');
check(slot.innerText.includes('Original Teacher'),'instructor visible without hover');
check(slot.innerText.includes('REG101')&&slot.innerText.includes('Regression Room'),'course and room');
check(slot.innerText.includes('First Term')&&slot.innerText.includes('2026-2027'),'term context');
check(slot.innerText.includes('8:00 AM'),'class time');
check(getComputedStyle(wrap).overflowX==='auto'||getComputedStyle(wrap).overflowX==='scroll','table scrolling contained');
if(wrap.scrollWidth>wrap.clientWidth){wrap.scrollLeft=100;check(wrap.scrollLeft>0,'timetable scrolls');wrap.scrollLeft=0;}
const details=document.querySelector('.schedule-list-disclosure');details.open=true;
check(details.innerText.includes('Original Teacher'),'readable alternate list');
check(document.documentElement.scrollWidth<=innerWidth+1,'list does not widen page');
const toggle=document.querySelector('[data-theme-toggle]');toggle.click();
check(document.documentElement.dataset.theme!==theme,'theme toggle works');toggle.click();
const fg=getComputedStyle(slot.querySelector('.personal-class-faculty')).color;
check(fg!==getComputedStyle(slot).backgroundColor,'instructor foreground distinct');
document.querySelector('#results').textContent=errors.length?'FAIL '+errors.join('; '):'PASS '+checks+' student checks\\nviewport width '+innerWidth;
},600);</script>'''
if '--faculty' in sys.argv:
    script = script.replace("check(slot.innerText.includes('Original Teacher'),'instructor visible without hover');", "check(document.body.innerText.includes('2.00 hours')&&document.body.innerText.includes('120 minutes'),'published workload');")
    script = script.replace("details.innerText.includes('Original Teacher')", "details.innerText.includes('Original Teacher')")
    script = script.replace("slot.querySelector('.personal-class-faculty')", "slot.querySelector('strong')")
    script = script.replace("student checks", "faculty checks")
html=html.replace('</body>',script+'</body>')
(root/'tests/browser'/('rendered_faculty.html' if '--faculty' in sys.argv else 'rendered_student.html')).write_text(html,encoding='utf-8')
print('Rendered authenticated timetable using in-memory database.')
