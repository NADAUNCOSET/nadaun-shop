/* Scroll-linked entrances, product photo changes and stable shopping links.
   Smooth desktop wheel scrolling; native touch and reduced-motion fallback. */
export function mountArtMotion(main,{gsap,ScrollTrigger:ST,Lenis,motionPreference='system'},env=window){
 if(!main||!gsap||!ST)return ()=>{};
 gsap.registerPlugin(ST);
 const doc=main.ownerDocument;
 const media=gsap.matchMedia();
 const preference=motionPreference==='on'?'all':motionPreference==='off'?'not all':'(prefers-reduced-motion:no-preference)';
 media.add({motion:preference,desktop:'(min-width:1000px) and (min-height:740px)',fine:'(pointer:fine)',mobile:'(max-width:700px)'},context=>{
  if(!context.conditions.motion)return;
  const {fine,mobile}=context.conditions;
  let releaseScroll=()=>{};
  if(Lenis&&fine&&!mobile){
   let smooth,tick;
   try{
    smooth=new Lenis({autoRaf:false,lerp:.14,smoothWheel:true,syncTouch:false,anchors:true,allowNestedScroll:true,stopInertiaOnNavigate:true,prevent:node=>node.matches?.('input,textarea,select,[contenteditable="true"],dialog,[role="dialog"],[data-lenis-prevent]')});
    smooth.on('scroll',ST.update);
    tick=time=>smooth.raf(time*1000);
    gsap.ticker.add(tick);
    releaseScroll=()=>{gsap.ticker.remove(tick);smooth.off('scroll',ST.update);smooth.destroy()};
   }catch(_error){if(tick)gsap.ticker.remove(tick);smooth?.destroy()}
  }
  const records=new Map();let timer,disposed=false;
  function remove(node){
   const entry=records.get(node);if(!entry)return;
   entry.context.revert();entry.cleanup?.();records.delete(node);
  }
  function register(node,build){
   if(!node||node.closest('[hidden]')||records.has(node))return;
   let cleanup;
   const scope=gsap.context(()=>{cleanup=build()},main);
   records.set(node,{context:scope,cleanup});
  }
  const scroll=(node,start='top bottom',end='bottom top')=>({trigger:node,start,end,scrub:mobile?.4:.85,invalidateOnRefresh:true});
  function photograph(frame,index){
   const img=frame.querySelector('img');if(!img)return;
   register(frame,()=>{
    const plane=doc.createElement('span');plane.className='motion-plane';
    img.before(plane);plane.append(img);
    const large=frame.matches('.department-visual,.editorial-visual');
    const home=!!frame.closest('.home-scene');
    const distance=home?12:mobile?20:large?24:30;
    const tilt=home?0:(index%2?1:-1)*(mobile?1.1:2.4);
    const phase=(index%(mobile?2:4))*3;
    const timeline=gsap.timeline({scrollTrigger:scroll(frame,`top ${98-phase}%`)});
    timeline.fromTo(plane,{yPercent:distance,scale:home?.97:.88,rotation:tilt,clipPath:home?'inset(0%)':'inset(14% 0% 10% 0% round 18px)'},{yPercent:0,scale:1,rotation:0,clipPath:'inset(0% 0% 0% 0% round 0px)',duration:.38,ease:'power2.out'})
     .to(plane,{yPercent:-3,scale:1.025,rotation:0,duration:.34,ease:'none'})
     .to(plane,{yPercent:mobile?-9:-14,scale:1.04,rotation:-tilt*.2,duration:.28,ease:'none'});
    // A real second view of the SAME product is revealed only after it loads.
    // The original photo stays underneath throughout failure/slow connections.
    const source=frame.dataset?.motionImage;
    let alternate,second,swapScope,loaded;
    if(source&&(/^(https?:\/\/)/.test(source)||(/^\/(?!\/)/.test(source)))){
     alternate=doc.createElement('span');alternate.className='motion-alternate';alternate.setAttribute('aria-hidden','true');
     second=doc.createElement('img');second.alt='';second.loading='lazy';second.decoding='async';second.referrerPolicy='no-referrer';
     loaded=()=>{
      if(disposed||!plane.isConnected||swapScope||!second.naturalWidth)return;
      frame.classList.add('has-motion-alternate');
      swapScope=gsap.context(()=>{
       gsap.fromTo(alternate,{opacity:0,xPercent:mobile?5:9,clipPath:'inset(0% 100% 0% 0%)'},{opacity:1,xPercent:0,clipPath:'inset(0% 0% 0% 0%)',ease:'power1.inOut',scrollTrigger:scroll(frame,`top ${64-phase}%`,`top ${24-phase}%`)});
      },main);
     };
     second.addEventListener('load',loaded);alternate.append(second);plane.append(alternate);second.src=source;
     if(second.complete)loaded();
    }
    return ()=>{
     if(second)second.removeEventListener('load',loaded);
     swapScope?.revert();alternate?.remove();frame.classList.remove('has-motion-alternate');
     if(img.parentNode===plane)plane.replaceWith(img);else plane.remove();
    };
   });
   const card=frame.closest('.product-card,.brand-tile');
   if(card)register(card,()=>{
    const labels=[...card.children].filter(el=>el.matches('.product-brand,.product-name,.product-price,.brand-label,small'));
    if(labels.length)gsap.fromTo(labels,{y:mobile?14:24},{y:0,stagger:.07,duration:.65,ease:'power2.out',scrollTrigger:scroll(frame,'top 86%','top 48%')});
   });
  }
  function scan(){
   if(disposed)return;
   for(const node of records.keys())if(!node.isConnected||node.closest('[hidden]'))remove(node);
   main.querySelectorAll('.department-visual,.brand-object,.product-image,.editorial-visual,.category-image').forEach(photograph);
   main.querySelectorAll('.section-head').forEach(section=>{if(section.closest('.home-scene'))return;register(section,()=>{
    section.classList.add('motion-section-head');
    gsap.fromTo(section,{'--section-line':0},{'--section-line':1,ease:'none',scrollTrigger:scroll(section,'top 92%','top 55%')});
    return ()=>section.classList.remove('motion-section-head');
   })});
   main.querySelectorAll('.section-head h2,.editorial-copy h2,.studio-amenities h2').forEach(heading=>{if(heading.closest('.home-scene'))return;register(heading,()=>{
    const lines=heading.querySelectorAll('.motion-line>span');
    if(lines.length)gsap.fromTo(lines,{yPercent:108,rotation:2},{yPercent:0,rotation:0,duration:1,stagger:.16,ease:'power2.out',scrollTrigger:scroll(heading,'top 96%','top 58%')});
    else gsap.fromTo(heading,{y:mobile?24:44},{y:0,ease:'none',scrollTrigger:scroll(heading,'top 96%','top 60%')});
   })});
   main.querySelectorAll('.section-head p,.section-index').forEach(text=>{if(text.closest('.home-scene'))return;register(text,()=>{
    gsap.fromTo(text,{y:mobile?12:24},{y:0,ease:'none',scrollTrigger:scroll(text,'top bottom','top 66%')});
   })});
   main.querySelectorAll('.cart-items>li,.checkout-services>section,.service-grid>section,.studio-gallery figure,.studio-specs>div,.studio-amenities li').forEach(node=>register(node,()=>{
    gsap.fromTo(node,{y:mobile?20:44},{y:0,ease:'none',scrollTrigger:scroll(node,'top bottom','top 66%')});
   }));
   ST.refresh();
  }
  const schedule=()=>{env.clearTimeout(timer);timer=env.setTimeout(scan,100)};
  const observer=new env.MutationObserver(schedule);
  observer.observe(main,{childList:true,subtree:true});
  doc.addEventListener('shop:content-updated',schedule);
  // Late image/font loads may change positions. Attribute writes never rescan.
  main.addEventListener('load',schedule,true);
  const progress=doc.createElement('span');progress.className='reading-progress';progress.setAttribute('aria-hidden','true');doc.body.append(progress);
  gsap.fromTo(progress,{scaleX:0},{scaleX:1,ease:'none',scrollTrigger:{trigger:main,start:'top top',end:'bottom bottom',scrub:true}});
  let releasePointer=()=>{};
  if(fine){
   const cursor=doc.createElement('span');cursor.className='art-cursor';cursor.textContent='보기 ↗';cursor.setAttribute('aria-hidden','true');doc.body.append(cursor);
   let active;
   const hide=()=>{
    cursor.classList.remove('visible');
    if(active){active.classList.remove('has-art-cursor');active.style.removeProperty('--hover-x');active.style.removeProperty('--hover-y');active=null}
   };
   const move=event=>{
    if(event.pointerType==='touch')return;
    const next=event.target.closest('.department-visual,.brand-object,.product-image,.editorial-visual,.category-image');
    if(!next||!main.contains(next)){hide();return}
    if(active!==next){hide();active=next;active.classList.add('has-art-cursor')}
    const box=active.getBoundingClientRect();
    active.style.setProperty('--hover-x',((event.clientX-box.left)/box.width-.5)*16+'px');
    active.style.setProperty('--hover-y',((event.clientY-box.top)/box.height-.5)*16+'px');
    cursor.style.left=event.clientX+'px';cursor.style.top=event.clientY+'px';cursor.classList.add('visible');
   };
   main.addEventListener('pointermove',move);main.addEventListener('pointerleave',hide);
   env.addEventListener('blur',hide);env.addEventListener('scroll',hide,{passive:true});
   doc.addEventListener('keydown',hide);
   releasePointer=()=>{main.removeEventListener('pointermove',move);main.removeEventListener('pointerleave',hide);env.removeEventListener('blur',hide);env.removeEventListener('scroll',hide);doc.removeEventListener('keydown',hide);hide();cursor.remove()};
  }
  scan();
  doc.fonts?.ready.then(()=>{if(!disposed)schedule()});
  return ()=>{
   disposed=true;env.clearTimeout(timer);observer.disconnect();
   doc.removeEventListener('shop:content-updated',schedule);main.removeEventListener('load',schedule,true);
   for(const node of records.keys())remove(node);
   releasePointer();releaseScroll();progress.remove();
  };
 });
 return ()=>media.revert();
}
