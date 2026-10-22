"""Render T10 pages from authenticated Django responses in an isolated database."""
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
from django.test.utils import setup_test_environment
from schedules.test_smart_repair import SmartRepairTests

setup_test_environment()
call_command('migrate',verbosity=0)
SmartRepairTests.setUpTestData()
case=SmartRepairTests()
case.client=Client()
case.setUp()
start=case.client.get(f'/schedules/{case.source.pk}/repair/')
invalid=case.client.post(f'/schedules/{case.source.pk}/repair/',dict(kind='room',room=case.room.pk,days=[0],start='not-a-time',end='09:00',recurring='on'))
assert invalid.context['form'].errors
draft=case.draft()
preview=case.client.post(f'/schedules/{draft.pk}/repair/review/',{'action':'preview'})
assert preview.context['result']['success']
case.hours.end_time=__import__('datetime').time(10)
case.hours.save()
unresolved=case.client.post(f'/schedules/{draft.pk}/repair/review/',{'action':'preview'})
assert not unresolved.context['result']['success']
pages=[]
for name,response in [('start',start),('invalid',invalid),('preview',preview),('unresolved',unresolved)]:
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
check([...d.querySelectorAll('input:not([type=hidden]),select,textarea,button')].filter(e=>e.getClientRects().length).every(e=>e.getBoundingClientRect().right<=w.innerWidth+1),name+' controls contained');
if(name==='start'||name==='invalid'){
check([...d.querySelectorAll('[aria-describedby]')].every(e=>e.getAttribute('aria-describedby').split(/\\s+/).every(id=>d.getElementById(id))),name+' descriptions resolve');
check([...d.querySelectorAll('[name=days]')].every(e=>e.labels.length>0),'weekday checkbox labels');
check(d.querySelector('[name=days]').closest('fieldset').querySelector('legend').textContent==='Unavailable days','weekday group named');
}
if(name==='invalid'){
const input=d.querySelector('[name=start]');input.focus();
check(input.getAttribute('aria-invalid')==='true','invalid time announced');
check(input.getAttribute('aria-describedby').includes('id_start_errors')&&d.querySelector('#id_start_errors').textContent.trim().length>0,'error linked to invalid control');
check(d.activeElement===input&&w.getComputedStyle(input).outlineStyle!=='none','invalid control keyboard focus visible');
check(d.querySelector('[name=days]').checked,'invalid submission preserves selected day');
}
if(name==='start'){
const kind=d.querySelector('[name=kind]'),details=d.querySelector('#repair-replacements');
check(details.hidden,'room hides optional instructor approval');
const days=d.querySelectorAll('[name=days]');days[0].click();days[2].click();
check(days[0].checked&&days[2].checked,'multiple weekdays stay selected');
kind.value='faculty';kind.dispatchEvent(new w.Event('change',{bubbles:true}));
check(!details.hidden,'faculty exposes optional replacement group');details.open=true;
const box=d.querySelector('[name=replacement_meetings]');box.click();box.focus();
check(box.checked&&d.activeElement===box,'keyboard reachable meeting selection');
check(!d.querySelector('[name=comparable]').checked,'authorization not assumed');
kind.value='sections';kind.dispatchEvent(new w.Event('change',{bubbles:true}));
check(d.querySelector('[data-repair-field=days]').hidden,'new sections hides outage window');
check(box.disabled,'irrelevant replacements not submitted');
kind.value='faculty';kind.dispatchEvent(new w.Event('change',{bubbles:true}));
check(box.checked&&!box.disabled,'switching back preserves selection');
check(d.documentElement.scrollWidth<=w.innerWidth+1,'expanded fields no page overflow');
}
if(name==='preview'){
check(d.querySelectorAll('article').length===2,'before-after meetings rendered');
check(!d.querySelector('[name=confirm]').checked,'application requires fresh approval');
const form=d.querySelector('[name=confirm]').form,button=form.querySelector('[value=apply]');
form.addEventListener('submit',e=>e.preventDefault(),{once:true});
form.dispatchEvent(new w.SubmitEvent('submit',{bubbles:true,cancelable:true,submitter:button}));
check(button.disabled,'duplicate submissions disabled');
check(new w.FormData(form).get('action')==='apply','loading preserves action');
w.dispatchEvent(new w.PageTransitionEvent('pageshow',{persisted:true}));
check(!button.disabled&&!form.hasAttribute('aria-busy'),'back navigation restores actions');
check(!form.querySelector('[data-repair-transient]')&&!form.dataset.submitting,'back navigation clears transient action and busy state');
}
if(name==='unresolved')check(!d.querySelector('[value=apply]'),'unresolved cannot apply');
}
document.querySelector('#results').textContent=errors.length?'FAIL '+errors.join('; '):'PASS '+count+' repair checks\\nviewport width '+innerWidth;
},800));</script>'''
(root/'tests/browser/rendered_repair.html').write_text(head+''.join(pages)+script,encoding='utf-8')
print('Rendered repair setup, preview and unresolved pages using isolated synthetic records.')
