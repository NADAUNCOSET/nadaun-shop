"""Browser geometry regression for animated category images and shipping guide.

Run on either OS against production, or --local to preview NAS CSS/policy files
over the current public catalogue without rebuilding supplier data.
Requires Python Playwright and the requested installed browser engines.
"""
import argparse
import json
from pathlib import Path
import platform

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CHECK = r"""() => {
 const frames=[...document.querySelectorAll('.category-image')];
 const invalid=[];
 for(const [index,frame] of frames.entries()){
  const plane=frame.querySelector('.motion-plane');
  const image=frame.querySelector('img');
  const details={index,frame:[frame.clientWidth,frame.clientHeight],
   plane:plane?[plane.clientWidth,plane.clientHeight]:null,
   image:image?[image.clientWidth,image.clientHeight]:null};
  if(plane&&(plane.offsetParent!==frame||Math.abs(plane.clientWidth-frame.clientWidth)>1||
    Math.abs(plane.clientHeight-frame.clientHeight)>1))invalid.push(details);
  if(image&&(image.clientWidth>frame.clientWidth+1||image.clientHeight>frame.clientHeight+1))invalid.push(details);
 }
 return {frameCount:frames.length,planeCount:frames.filter(f=>f.querySelector('.motion-plane')).length,
  documentWidth:document.documentElement.scrollWidth,viewportWidth:innerWidth,
  invalid,scrollY,active:document.body.dataset.motionActive};
}"""

def run(args):
    output=ROOT/'_private/windows-layout-pg-20261015'
    output.mkdir(parents=True,exist_ok=True)
    report={'phase':args.phase,'os':platform.platform(),'local_overrides':args.local,'cases':[]}
    sizes=[(2048,1087)] if args.phase=='before' else [(2048,1087),(1440,900),(1280,720),(390,844),(320,760)]
    with sync_playwright() as playwright:
        for name in args.browsers.split(','):
            engine=getattr(playwright,'chromium' if name in ['chrome','msedge'] else name)
            browser=engine.launch(headless=True,**({'channel':name} if name in ['chrome','msedge'] else {}))
            try:
                for preference in (['no-preference'] if args.phase=='before' else ['no-preference','reduce']):
                    context=browser.new_context(viewport={'width':sizes[0][0],'height':sizes[0][1]},reduced_motion=preference)
                    if args.local:
                        context.route('**/assets/shop/storefront.css*',lambda route:route.fulfill(
                            path=str(ROOT/'assets/shop/storefront.css'),content_type='text/css'))
                        context.route('**/shipping.html*',lambda route:route.fulfill(
                            path=str(ROOT/'shipping.html'),content_type='text/html; charset=utf-8'))
                    page=context.new_page()
                    errors=[]
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    page.goto(args.site+'/',wait_until='domcontentloaded')
                    page.locator('.category-image').first.wait_for()
                    page.wait_for_function("document.querySelector('.category-image .motion-plane') || document.body.dataset.motionActive==='false' || matchMedia('(prefers-reduced-motion:reduce)').matches")
                    page.evaluate('() => document.fonts.ready')
                    for width,height in sizes:
                        page.set_viewport_size({'width':width,'height':height})
                        page.evaluate('window.scrollTo(0,0)')
                        page.wait_for_timeout(200)
                        stages=[]
                        stages.append(page.evaluate(CHECK))
                        # Native wheel input, large jumps, reverse scrolling and resizing.
                        for delta in [120,120,900,1500,-700,-1500]:
                            page.mouse.wheel(0,delta)
                            page.wait_for_timeout(180)
                            stages.append(page.evaluate(CHECK))
                        if preference=='no-preference' and width in [2048,390]:
                            page.evaluate("document.querySelector('.category-gallery').scrollIntoView({block:'start'})")
                            page.wait_for_timeout(200)
                            page.screenshot(path=str(output/f'{args.phase}-{name}-{width}.png'))
                        # Focus and hover must not turn the clipping layer into a viewport layer.
                        link=page.locator('.category-image-tile').first
                        link.focus()
                        link.hover()
                        stages.append(page.evaluate(CHECK))
                        invalid=[stage for stage in stages if stage['invalid'] or stage['documentWidth']>stage['viewportWidth']+1]
                        case={'browser':name,'version':browser.version,'motion':preference,'viewport':[width,height],
                              'stages':len(stages),'passed':not invalid,'sample':stages[0],
                              'failures':invalid}
                        report['cases'].append(case)
                        (output/f'{args.phase}-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                    page.goto(args.site+'/shipping.html',wait_until='domcontentloaded')
                    text=page.locator('#main').inner_text()
                    policy={'browser':name,'motion':preference,'purchase_delivery':
                            '구매 후 배송완료까지 1주일 내에 완료됩니다.' in text,
                            'rental_section':bool(page.locator('#rental-period').count())}
                    if preference=='no-preference' and args.phase!='before':
                        page.set_viewport_size({'width':1440,'height':1080})
                        page.locator('#delivery').scroll_into_view_if_needed()
                        page.screenshot(path=str(output/f'{args.phase}-{name}-shipping.png'),full_page=True)
                    report.setdefault('policy',[]).append(policy)
                    report.setdefault('page_errors',[]).extend(errors)
                    context.close()
            finally:
                browser.close()
    report['layout_passed']=all(case['passed'] for case in report['cases'])
    (output/f'{args.phase}-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'phase':args.phase,'cases':len(report['cases']),
                      'layout_passed':report['layout_passed'],'page_errors':report.get('page_errors'),
                      'policy':report.get('policy')},ensure_ascii=False))
    return 0 if report['layout_passed'] else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['before','after','live'],default='live')
    parser.add_argument('--local',action='store_true')
    parser.add_argument('--site',default='https://shop.nadaun.co')
    parser.add_argument('--browsers',default='chromium')
    raise SystemExit(run(parser.parse_args()))
