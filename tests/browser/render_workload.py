"""Workload pages rendered from isolated, authenticated Django HTTP responses."""
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
setup_test_environment()
from django.urls import reverse
from schedules.test_workload_balancing import WorkloadBalancingTests
call_command('migrate',verbosity=0)
WorkloadBalancingTests.setUpTestData()
case=WorkloadBalancingTests()
case.client=Client()
case.setUp()
case.client.force_login(case.admin)
pages=[]
initial=case.client.get(reverse('workload_proposals'))
analysis=case.http_analyze()
preview=case.client.post(reverse('workload_proposals'), {'action':'generate',
    'analysis_token':analysis.context['analysis_token'], 'scope_state':analysis.context['scope_state'],
    'authorize_scope':'yes','comparable':'yes'})
assert 'token' in preview.context
responses=[('scope',initial),('analysis',analysis),('preview',preview)]
for name,response in responses:
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
check(!d.querySelector('#workload-advanced').open,name+' advanced collapsed');
check(!d.querySelector('select[name=assignments]'),name+' no native multiselect');
if(name==='analysis'){
check(d.querySelector('#eligibility-heading').textContent.includes('Eligibility'),'eligibility summary');
check(!d.querySelector('[name=authorize_scope]').checked,'authorization not assumed');
check(!d.querySelector('[name=comparable]').checked,'comparability not assumed');
}
if(name==='scope'){
const term=d.querySelector('[name=term]'),dept=d.querySelector('[name=department]');
term.selectedIndex=1;dept.selectedIndex=1;dept.dispatchEvent(new w.Event('change',{bubbles:true}));
d.querySelector('#workload-advanced').open=true;
const picker=d.querySelector('[data-picker=assignments]');
const boxes=[...picker.querySelectorAll('input[type=checkbox]')];
boxes[0].click();boxes[1].click();
check(picker.querySelector('[data-picker-count]').textContent.startsWith('2 selected'),'selection count');
check(picker.querySelectorAll('[data-picker-summary] button').length===2,'removable summaries');
const search=picker.querySelector('[data-picker-search]');search.value='no such class';search.dispatchEvent(new w.Event('input',{bubbles:true}));
check(boxes[0].checked&&boxes[1].checked,'search preserves choices');
check(boxes[2].closest('label').parentElement.hidden,'search filters other rows');
const teachers=d.querySelector('[data-picker=faculty]');teachers.querySelector('input[type=checkbox]').click();
check(boxes[0].checked&&boxes[1].checked,'switching lists preserves choices');
picker.querySelector('[data-picker-summary] button').click();
check(picker.querySelector('[data-picker-count]').textContent.startsWith('1 selected'),'remove updates count');
check(d.activeElement===search,'remove restores keyboard focus');
const remaining=boxes.find(b=>b.checked);remaining.focus();check(d.activeElement===remaining,'checkbox focusable');
dept.value='';dept.dispatchEvent(new w.Event('change',{bubbles:true}));
check(remaining.getAttribute('aria-invalid')==='true','scope change marks invalid selection');
check(picker.querySelector('[data-picker-feedback]').textContent.includes('outside'),'invalid scope feedback');
check(d.querySelector('#workload-output').hidden,'scope change hides old output');
check(d.documentElement.scrollWidth<=w.innerWidth+1,'expanded advanced no overflow');
const form=d.querySelector('#workload-scope'),button=form.querySelector('[value=analyze]');
form.addEventListener('submit',e=>e.preventDefault(),{once:true});
form.dispatchEvent(new w.SubmitEvent('submit',{bubbles:true,cancelable:true,submitter:button}));
check(form.getAttribute('aria-busy')==='true','loading announced');
check(button.disabled,'duplicate submission disabled');
check(new w.FormData(form).get('action')==='analyze','loading preserves submit action');
}
if(name==='preview'){
const selected=d.querySelector('[name=selected]');check(!!selected,'selection checkbox');
check(!d.querySelector('[value=approve]').disabled,'reviewed batch approvable');
selected.checked=false;selected.dispatchEvent(new w.Event('change',{bubbles:true}));
check(d.querySelector('[value=approve]').disabled,'changed selection cannot approve');
check([...d.querySelectorAll('[data-batch-metrics]')].every(e=>e.hidden),'stale metrics hidden');
check(d.querySelector('#selection-notice').textContent.includes('Preview'),'preview instruction');
const dept=d.querySelector('[name=department]');dept.value='';dept.dispatchEvent(new w.Event('change',{bubbles:true}));
check(d.querySelector('#workload-output').hidden,'changed filters invalidate proposal UI');
}
}
document.querySelector('#results').textContent=errors.length?'FAIL '+errors.join('; '):'PASS '+count+' workload checks\\nviewport width '+innerWidth;
},800));</script>'''
(root/'tests/browser/rendered_workload.html').write_text(head+''.join(pages)+script,encoding='utf-8')
print('Rendered workload scope and preview using isolated synthetic records.')
