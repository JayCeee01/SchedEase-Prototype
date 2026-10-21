"""Concern pages rendered from isolated, authenticated Django HTTP responses."""
from pathlib import Path
import html
import os
import sys
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','sched_ease.settings')
from django.conf import settings
settings.DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
settings.ALLOWED_HOSTS=['testserver']
settings.SECURE_SSL_REDIRECT=False
import django
django.setup()
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from schedules.test_concerns import ConcernTests
from schedules.services.concerns import review_concern
call_command('migrate',verbosity=0)
ConcernTests.setUpTestData()
case=ConcernTests()
case.client=Client()
case.setUp()
concern=case.submit(description='A long concern: '+'X'*500)
teacher_concern=case.submit(case.teacher)
review_concern(actor=case.admin,pk=concern.pk,revision=0,status='UNDER_REVIEW',response='We are reviewing the timetable.')
pages=[]
for actor,name,route,args in [
    (case.student,'student-new','concern_create',[]),(case.student,'student-list','concern_list',[]),
    (case.student,'student-detail','concern_detail',[concern.pk]),
    (case.teacher,'faculty-new','concern_create',[]),(case.teacher,'faculty-detail','concern_detail',[teacher_concern.pk]),
    (case.admin,'admin-list','concern_list',[]),(case.admin,'admin-review','concern_detail',[concern.pk])]:
    case.client.force_login(actor)
    response=case.client.get(reverse(route,args=args))
    assert response.status_code==200
    content=response.content.decode().replace('/static/',(root/'static').as_uri()+'/')
    pages.append(f'<iframe title="{name}" data-page="{name}" srcdoc="{html.escape(content,quote=True)}"></iframe>')
head='''<!doctype html><meta charset="utf-8"><style>body{margin:0}iframe{display:block;width:100%;height:1000px;border:0}#results{position:fixed;bottom:0;left:0;background:white;color:black;font-size:10px;z-index:9999}</style><script>localStorage.setItem('schedease-theme',new URLSearchParams(location.search).get('theme'));</script>'''
script='''<pre id="results">RUNNING</pre><script>window.addEventListener('load',()=>setTimeout(()=>{
let count=0;const errors=[];const check=(ok,text)=>{count++;if(!ok)errors.push(text)};
for(const frame of document.querySelectorAll('iframe')){
const d=frame.contentDocument,w=frame.contentWindow,name=frame.dataset.page;
check(d.documentElement.dataset.theme===new URLSearchParams(location.search).get('theme'),name+' theme');
check(d.documentElement.scrollWidth<=w.innerWidth+1,name+' no page overflow');
check(d.querySelector('h1')?.innerText.length>0,name+' heading');
check([...d.querySelectorAll('input:not([type=hidden]),select,textarea')].filter(e=>e.getClientRects().length).every(e=>e.getBoundingClientRect().right<=w.innerWidth+1),name+' controls contained');
check(!!d.querySelector('a[href="/schedules/concerns/"]'),name+' navigation');
if(name==='admin-review')check(!!d.querySelector('[name=status]')&&!!d.querySelector('[name=response]'),'review controls');
if(name==='student-detail')check(!d.querySelector('[name=status]')&&!d.querySelector('[name=response]'),'reporter read-only');
}
document.querySelector('#results').textContent=errors.length?'FAIL '+errors.join('; '):'PASS '+count+' concern checks\\nviewport width '+innerWidth;
},800));</script>'''
(root/'tests/browser/rendered_concerns.html').write_text(head+''.join(pages)+script,encoding='utf-8')
print('Rendered seven authenticated concern pages using synthetic in-memory records.')
