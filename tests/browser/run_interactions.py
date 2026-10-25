"""Run actual browser event-loop regressions with a disposable local profile."""
from pathlib import Path
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen
from cdp_browser import DevTools

root = Path(__file__).resolve().parents[2]
fixture = 'export_controls.html' if '--exports' in sys.argv else 'meeting_hours.html' if '--meeting-hours' in sys.argv else 'faculty_suggestions.html' if '--suggestions' in sys.argv else 'record_layout.html' if '--record-layout' in sys.argv else 'availability_owner.html' if '--availability' in sys.argv else 'rendered_repair.html' if '--repair' in sys.argv else 'rendered_workload.html' if '--workload' in sys.argv else 'rendered_concerns.html' if '--concerns' in sys.argv else 'rendered_faculty.html' if '--faculty' in sys.argv else 'rendered_student.html' if '--student' in sys.argv else 'rendered_editors.html' if '--editors' in sys.argv else 'rendered_responsive.html' if '--rendered' in sys.argv else 'responsive_layout.html' if '--responsive' in sys.argv else 'top_navigation.html' if '--topbar' in sys.argv else 'sidebar_navigation.html' if '--sidebar' in sys.argv else ('table_scrolling.html' if '--tables' in sys.argv else 'interaction_states.html')
candidates = [Path(os.environ.get('PROGRAMFILES', '')) / 'Google/Chrome/Application/chrome.exe',
              Path(os.environ.get('PROGRAMFILES(X86)', '')) / 'Microsoft/Edge/Application/msedge.exe']
browser = next((p for p in candidates if p.is_file()), None)
if browser is None:
    raise SystemExit('Chrome/Edge unavailable: run the documented manual checklist.')
for theme in ('light', 'dark'):
    for width in ((1360, 1024, 901, 768, 621, 500, 390) if '--responsive' in sys.argv or '--rendered' in sys.argv or '--editors' in sys.argv else (1360, 768, 500, 390) if '--exports' in sys.argv or '--meeting-hours' in sys.argv or '--suggestions' in sys.argv or '--record-layout' in sys.argv or '--repair' in sys.argv or '--workload' in sys.argv or '--concerns' in sys.argv or '--faculty' in sys.argv or '--student' in sys.argv or '--sidebar' in sys.argv or '--topbar' in sys.argv else (1360, 390)):
        with tempfile.TemporaryDirectory(prefix='schedease-ui-', dir=root/'tests/browser') as profile:
            assert Path(profile).resolve().parent == (root/'tests/browser').resolve()
            process = subprocess.Popen([str(browser), '--headless=new', '--disable-gpu', '--no-first-run',
                '--no-default-browser-check', '--allow-file-access-from-files', '--remote-debugging-port=0',
                '--remote-allow-origins=http://localhost', '--user-data-dir='+profile, 'about:blank'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            client = None
            try:
                port_file = Path(profile)/'DevToolsActivePort'
                deadline = time.monotonic() + 15
                while True:
                    try:
                        port = port_file.read_text().splitlines()[0]
                        break
                    except (OSError, IndexError):
                        if time.monotonic() > deadline:
                            raise TimeoutError('Browser did not start')
                        time.sleep(.1)
                with urlopen(Request(f'http://127.0.0.1:{port}/json/new?about:blank', method='PUT'), timeout=5) as response:
                    target = json.load(response)
                client = DevTools(target['webSocketDebuggerUrl'])
                client.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 768 if '--responsive' in sys.argv or '--rendered' in sys.argv or '--editors' in sys.argv else 900, 'deviceScaleFactor': 1, 'mobile': False})
                client.call('Page.bringToFront')
                client.call('Emulation.setFocusEmulationEnabled', {'enabled': True})
                client.call('Page.navigate', {'url': (root/'tests/browser'/fixture).as_uri()+'?theme='+theme})
                deadline = time.monotonic() + 20
                while True:
                    result = client.call('Runtime.evaluate', {'expression': 'document.querySelector("#results")?.textContent', 'returnByValue': True})
                    text = result.get('result', {}).get('value', '') or ''
                    if text.startswith(('PASS ', 'FAIL ')):
                        break
                    if time.monotonic() > deadline:
                        raise TimeoutError('Fixture did not finish: '+text)
                    time.sleep(.1)
                assert text.startswith('PASS '), text
                lines = text.splitlines()
                assert lines[1] == f'viewport width {width}', lines[1]
                if '--measure' in sys.argv:
                    metrics = client.call('Runtime.evaluate', {'expression': "JSON.stringify([...document.querySelectorAll('[data-page]')].filter(p=>/dashboard|resource_create|room_utilization/.test(p.dataset.page)).map(p=>({page:p.dataset.page,height:Math.round(p.getBoundingClientRect().height),firstPanel:Math.round((p.querySelector('.panel,.metrics')?.getBoundingClientRect().top||0)-p.getBoundingClientRect().top)})))", 'returnByValue': True})
                    print(theme, width, metrics['result']['value'], flush=True)
                if '--tables' in sys.argv:
                    client.call('Emulation.setDeviceMetricsOverride', {'width': width - 40, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
                    time.sleep(.2)
                    evaluation = client.call('Runtime.evaluate', {'expression': "document.querySelector('#first').parentElement.querySelector('.table-scroll-proxy').getBoundingClientRect().right <= innerWidth", 'returnByValue': True})
                    assert evaluation['result']['value'], 'proxy follows window resize'
                    client.call('Emulation.setDeviceMetricsOverride', {'width': width, 'height': 900, 'deviceScaleFactor': 1, 'mobile': False})
                    time.sleep(.2)
                    client.call('Runtime.evaluate', {'expression': "document.querySelector('#first').parentElement.querySelector('.table-scroll-proxy').focus()"})
                    client.call('Input.dispatchKeyEvent', {'type': 'rawKeyDown', 'key': 'ArrowRight', 'code': 'ArrowRight', 'windowsVirtualKeyCode': 39})
                    client.call('Input.dispatchKeyEvent', {'type': 'keyUp', 'key': 'ArrowRight', 'code': 'ArrowRight', 'windowsVirtualKeyCode': 39})
                    time.sleep(.3)
                    evaluation = client.call('Runtime.evaluate', {'expression': "document.querySelector('#first').scrollLeft > 0", 'returnByValue': True})
                    assert evaluation['result']['value'], 'native keyboard scrolling moves actual table'
                if '--record-layout' in sys.argv:
                    shot = client.call('Page.captureScreenshot', {'format': 'png'})
                    (root/f'ui-record-layout-{theme}-{width}.png').write_bytes(base64.b64decode(shot['data']))
                if '--sidebar' in sys.argv:
                    client.call('Runtime.evaluate', {'expression': 'document.querySelector("#results").textContent="RUNNING"'})
                    client.call('Page.reload')
                    deadline = time.monotonic() + 20
                    while True:
                        result = client.call('Runtime.evaluate', {'expression': 'document.querySelector("#results")?.textContent', 'returnByValue': True})
                        reloaded = result.get('result', {}).get('value', '') or ''
                        if reloaded.startswith(('PASS ', 'FAIL ')):
                            break
                        if time.monotonic() > deadline:
                            raise TimeoutError('Sidebar reload did not finish')
                        time.sleep(.1)
                    assert reloaded.startswith('PASS '), reloaded
                if '--screenshots' in sys.argv:
                    shot = client.call('Page.captureScreenshot', {'format': 'png'})
                    (root/f"{'tests/browser/t10' if '--repair' in sys.argv else 'ui-editor' if '--editors' in sys.argv else 'ui-refinement'}-{theme}-{width}.png").write_bytes(base64.b64decode(shot['data']))
                if '--sidebar' in sys.argv and '--screenshots' in sys.argv:
                    expression = "document.querySelector('[data-sidebar-collapse]').click()" if width > 900 else "document.querySelector('button[data-sidebar-toggle]').click()"
                    client.call('Runtime.evaluate', {'expression': expression})
                    time.sleep(.3)
                    shot = client.call('Page.captureScreenshot', {'format': 'png'})
                    (root/f'ui-sidebar-open-{theme}-{width}.png').write_bytes(base64.b64decode(shot['data']))
                print(fixture, theme, width, lines[0], '+ resize/keyboard checks' if '--tables' in sys.argv else '', flush=True)
            finally:
                if client:
                    try:
                        client.call("Browser.close")
                        time.sleep(.5)
                    except (OSError, RuntimeError):
                        pass
                    client.close()
                process.terminate()
                process.wait(timeout=10)
