/* Native scrolling drives the exhibition; links and text keep their layout. */
export function mountArtMotion(main,{gsap,ScrollTrigger:ST},env=window){
 if(!main||!gsap||!ST)return ()=>{};
 gsap.registerPlugin(ST);
 const doc=main.ownerDocument;
 const media=gsap.matchMedia();
 media.add({motion:'(prefers-reduced-motion:no-preference)',desktop:'(min-width:1000px) and (min-height:740px)',fine:'(pointer:fine)',mobile:'(max-width:700px)'},context=>{
  if(!context.conditions.motion)return;
  const {desktop,fine,mobile}=context.conditions;
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
  const scroll=(node,start='top bottom',end='bottom top')=>({trigger:node,start,end,scrub:mobile?.35:.65,invalidateOnRefresh:true});
  function photograph(frame,index){
   const img=frame.querySelector('img');if(!img)return;
   register(frame,()=>{
    const plane=doc.createElement('span');plane.className='motion-plane';
    img.before(plane);plane.append(img);
    const large=frame.matches('.department-visual,.editorial-visual');
    const distance=mobile?8:large?18:12;
    const tilt=(index%2?1:-1)*(mobile?.8:large?3:1.6);
    const timeline=gsap.timeline({scrollTrigger:scroll(frame)});
    timeline.fromTo(plane,{yPercent:distance,scale:large?.9:.95,rotation:tilt},{yPercent:0,scale:1,rotation:0,duration:.52,ease:'none'})
     .to(plane,{yPercent:-distance*.8,scale:large?1.06:1.025,rotation:-tilt*.35,duration:.48,ease:'none'});
    return ()=>{if(img.parentNode===plane)plane.replaceWith(img);else plane.remove()};
   });
  }
  function scan(){
   if(disposed)return;
   for(const node of records.keys())if(!node.isConnected||node.closest('[hidden]'))remove(node);
   main.querySelectorAll('.department-visual,.brand-object,.product-image,.editorial-visual').forEach(photograph);
   main.querySelectorAll('.section-head h2,.editorial-copy h2,.studio-amenities h2').forEach(heading=>register(heading,()=>{
    const lines=heading.querySelectorAll('.motion-line>span');
    if(lines.length)gsap.fromTo(lines,{yPercent:108,rotation:2},{yPercent:0,rotation:0,duration:1,stagger:.16,ease:'power2.out',scrollTrigger:scroll(heading,'top 96%','top 58%')});
    else gsap.fromTo(heading,{y:mobile?24:44},{y:0,ease:'none',scrollTrigger:scroll(heading,'top 96%','top 60%')});
   }));
   main.querySelectorAll('.section-head p,.section-index,.department-title').forEach(text=>register(text,()=>{
    gsap.fromTo(text,{y:mobile?12:24},{y:0,ease:'none',scrollTrigger:scroll(text,'top bottom','top 66%')});
   }));
   main.querySelectorAll('.cart-items>li,.checkout-services>section,.service-grid>section,.studio-gallery figure,.studio-specs>div,.studio-amenities li').forEach(node=>register(node,()=>{
    gsap.fromTo(node,{y:mobile?20:44},{y:0,ease:'none',scrollTrigger:scroll(node,'top bottom','top 66%')});
   }));
   const pair=main.querySelector('.editorial-pair');
   if(desktop&&pair)register(pair,()=>{
    pair.classList.add('has-stacked-motion');
    const [first,second]=pair.children;
    gsap.to(first,{scale:.93,y:-24,transformOrigin:'center top',ease:'none',scrollTrigger:scroll(second,'top 90%','top 18%')});
    return ()=>pair.classList.remove('has-stacked-motion');
   });
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
    const next=event.target.closest('.department-visual,.brand-object,.editorial-visual');
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
   releasePointer();progress.remove();
  };
 });
 return ()=>media.revert();
}
