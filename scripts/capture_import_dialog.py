"""截取工作台集成的数据导入弹窗，并验证旧 /import 路由回落工作台。"""
from __future__ import annotations
import argparse,base64,pathlib,subprocess,sys,time,uuid
SCRIPTS=pathlib.Path(__file__).resolve().parent;sys.path.insert(0,str(SCRIPTS))
from cdp_login_check import CDP,find_edge,free_port,wait_target
LOGIN="""(()=>{const s=(q,v)=>{const e=document.querySelector(q);if(!e)return;e.value=v;e.dispatchEvent(new Event('input',{bubbles:true}))};s('#username','admin');s('#password','admin');document.querySelector('form.login-card button')?.click();return 'ok'})()"""
def main():
 p=argparse.ArgumentParser();p.add_argument('--out',default='docs/screenshot-import-dialog.png');p.add_argument('--base',default='http://127.0.0.1:5173');a=p.parse_args();edge=find_edge();work=pathlib.Path('backend/var')/('imp-'+uuid.uuid4().hex[:6]);work.mkdir(parents=True,exist_ok=True);port=free_port();proc=subprocess.Popen([edge,'--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-sync','--disable-extensions',f'--user-data-dir={work}/p',f'--remote-debugging-port={port}','--window-size=1440,980','about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);cdp=None
 try:
  target=wait_target(port);cdp=CDP(target['webSocketDebuggerUrl']);cdp.call('Runtime.enable');cdp.call('Page.enable');cdp.call('Emulation.setDeviceMetricsOverride',{'width':1440,'height':980,'deviceScaleFactor':1,'mobile':False});cdp.call('Page.navigate',{'url':a.base+'/#/login'});time.sleep(2);cdp.evaluate(LOGIN);time.sleep(2);cdp.evaluate("location.hash='#/import'");time.sleep(2);print('old route=',cdp.evaluate('location.hash'));cdp.evaluate("location.hash='#/'");time.sleep(3);clicked=cdp.evaluate("(()=>{const b=[...document.querySelectorAll('button')].find(x=>x.textContent.includes('导入档案'));if(!b)return 'none';b.click();return 'clicked'})()");time.sleep(1);print('clicked=',clicked,'dialog=',cdp.evaluate("Boolean(document.querySelector('.import-dialog'))"));shot=cdp.call('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False});out=pathlib.Path(a.out);out.write_bytes(base64.b64decode(shot['data']));print('saved',out,out.stat().st_size);return 0
 finally:
  if cdp:cdp.close()
  proc.terminate()
  try:proc.wait(timeout=10)
  except:proc.kill()
if __name__=='__main__':raise SystemExit(main())
