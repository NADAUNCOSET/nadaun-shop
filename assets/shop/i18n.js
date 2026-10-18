import {translations} from './i18n-data.js?v=20261018';
export const languages=Object.freeze([{id:'ko',label:'한국어'},{id:'en',label:'English'},{id:'ja',label:'日本語'},{id:'zh-CN',label:'简体中文'}]);
export const languageKey='nadaun-shop-language-v1';
const languageIds=new Set(languages.map(l=>l.id));
export function resolveLanguage({query,stored,browser=[]}={}){
 if(languageIds.has(query))return query;
 if(languageIds.has(stored))return stored;
 for(const raw of browser){const base=String(raw).toLowerCase();if(base==='zh'||base.startsWith('zh-'))return 'zh-CN';if(base==='ja'||base.startsWith('ja-'))return 'ja';if(base==='en'||base.startsWith('en-'))return 'en';if(base==='ko'||base.startsWith('ko-'))return 'ko';}
 return 'ko';
}
const pick=(locale,en,ja,zh)=>({en,ja,'zh-CN':zh}[locale]);
const providerNames={카카오:'Kakao',카카오톡:'KakaoTalk',Google:'Google',네이버:'Naver'};
export function translate(source,locale){
 if(locale==='ko'||!languageIds.has(locale)||typeof source!=='string')return source;
 const key=source.trim();if(!key)return source;
 let result=translations[key]?.[locale];
 if(result===undefined){let match;
  if((match=key.match(/^([+-]?[\d,]+)원$/)))result=pick(locale,`${match[1]} KRW`,`${match[1]}ウォン`,`${match[1]} 韩元`);
  else if((match=key.match(/^(Google|카카오톡|카카오|네이버)(로 계속하기| 로그인| 연결하기| · 연결됨|로 가입 완료하기)$/))){const name=providerNames[match[1]],suffix=match[2];result=suffix===' · 연결됨'?pick(locale,`${name} · Connected`,`${name}・連携済み`,`${name} · 已关联`):suffix===' 연결하기'?pick(locale,`Connect ${name}`,`${name}を連携`,`关联 ${name}`):suffix==='로 가입 완료하기'?pick(locale,`Finish joining with ${name}`,`${name}で登録を完了`,`使用 ${name} 完成注册`):pick(locale,`Continue with ${name}`,`${name}で続ける`,`使用 ${name} 继续`);}
  else if((match=key.match(/^(\d[\d,]*)개 선택$/)))result=pick(locale,`${match[1]} selected`,`${match[1]}点選択中`,`已选 ${match[1]} 件`);
  else if((match=key.match(/^(전체 )?(\d[\d,]*)개 브랜드$/)))result=pick(locale,`${match[2]} brands`,`${match[2]}ブランド`,`${match[2]} 个品牌`);
  else if((match=key.match(/^(\d[\d,]*)개 카테고리$/)))result=pick(locale,`${match[1]} categories`,`${match[1]}カテゴリー`,`${match[1]} 个类别`);
  else if((match=key.match(/^(\d[\d,]*)개 구성 · (\d[\d,]*)개( 선택)?$/)))result=pick(locale,`${match[1]} configurations · ${match[2]} items${match[3]?' selected':''}`,`${match[1]}構成・${match[2]}点${match[3]?'選択中':''}`,`${match[1]} 种配置 · ${match[2]} 件${match[3]?'已选':''}`);
  else if((match=key.match(/^(\d[\d,]*)개 구성$/)))result=pick(locale,`${match[1]} configurations`,`${match[1]}構成`,`${match[1]} 种配置`);
  else if((match=key.match(/^(\d[\d,]*)개$/)))result=pick(locale,`${match[1]} items`,`${match[1]}点`,`${match[1]} 件`);
  else if(key==='총')result=pick(locale,'Total','合計','共');
  else if(key==='개')result=pick(locale,'items','点','件');
  else if(key==='개 선택')result=pick(locale,'selected','点選択中','件已选');
  else if((match=key.match(/^제품 종류와 브랜드를 선택해 필요한 (상품|대여 장비)를 찾아보세요\.$/)))result=pick(locale,'Choose a category and brand to find your equipment.','種類とブランドを選んで、お探しの機材を見つけてください。','选择类别和品牌，寻找所需器材。');
 }
 if(result===undefined&&key.endsWith(' | 나다운 샵')){const base=key.split(' | ')[0];if(translations[base]?.[locale])result=translations[base][locale]+' | NADAUN SHOP';}
 if(result===undefined&&/[→↗]$/.test(key)){const base=key.slice(0,-1).trim();if(translations[base]?.[locale])result=translations[base][locale]+' '+key.slice(-1);}
 return result===undefined?source:source.slice(0,source.length-source.trimStart().length)+result+source.slice(source.trimEnd().length);
}
const blocked='script,style,noscript,code,pre,svg,[translate="no"],[data-no-translate],.product-name,.detail-info>h1,.cart-item-info>a,.member-data,.commerce-lines a,.commerce-address p,.crm-content';
const attributes=['placeholder','aria-label','title'];
export function mountLanguageUI(doc=document,win=window){
 if(doc.body.dataset.mode?.includes('admin')||doc.body.dataset.crmView||/\/(manage|test-admin|shop-test|payment-test)\.html$/.test(win.location.pathname))return;
 if(doc.body.dataset.mode==='policy'){const legal=doc.querySelector('#main');if(legal){legal.lang='ko';legal.setAttribute('translate','no');}}
 let stored;try{stored=win.localStorage.getItem(languageKey);}catch{}
 let locale=resolveLanguage({query:new URLSearchParams(win.location.search).get('lang'),stored,browser:win.navigator.languages||[win.navigator.language]});
 try{win.localStorage.setItem(languageKey,locale);}catch{}
 const originalText=new WeakMap(),originalAttributes=new WeakMap();let titleSource=doc.title,titleOutput=doc.title;
 const excluded=el=>!el||el.closest(blocked);
 function text(node){if(excluded(node.parentElement)||node.parentElement.closest('input,textarea'))return;const previous=originalText.get(node);const source=previous&&previous.output===node.data?previous.source:node.data;const output=translate(source,locale);originalText.set(node,{source,output});if(node.data!==output)node.data=output;}
 function attr(el){if(excluded(el))return;let saved=originalAttributes.get(el);if(!saved){saved={};originalAttributes.set(el,saved);}for(const name of attributes){if(!el.hasAttribute(name))continue;const value=el.getAttribute(name),previous=saved[name],source=previous&&previous.output===value?previous.source:value,output=translate(source,locale);saved[name]={source,output};if(output!==value)el.setAttribute(name,output);}}
 function walk(root){if(root.nodeType===3){text(root);return;}if(root.nodeType!==1||excluded(root))return;attr(root);const walker=doc.createTreeWalker(root,win.NodeFilter.SHOW_ELEMENT|win.NodeFilter.SHOW_TEXT,{acceptNode(node){return node.nodeType===1&&excluded(node)?win.NodeFilter.FILTER_REJECT:win.NodeFilter.FILTER_ACCEPT;}});while(walker.nextNode()){const node=walker.currentNode;node.nodeType===3?text(node):attr(node);}}
 const bar=doc.createElement('div');bar.className='language-bar';bar.setAttribute('translate','no');
 const label=doc.createElement('label');label.className='language-picker';label.htmlFor='shop-language';label.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c5 5 5 13 0 18-5-5-5-13 0-18Z"/></svg><span class="sr">Language / 언어</span>';
 const select=doc.createElement('select');select.id='shop-language';select.setAttribute('aria-label','Language / 언어');for(const language of languages){const option=doc.createElement('option');option.value=language.id;option.textContent=language.label;option.lang=language.id;select.append(option);}label.append(select);bar.append(label);
 const currency=doc.createElement('span');currency.className='language-currency';currency.textContent='KRW · ₩';bar.append(currency);
 const utility=doc.querySelector('.utility .wrap');if(utility)utility.append(bar);else (doc.querySelector('.masthead')||doc.body).prepend(bar);
 const help=doc.createElement('a');help.className='language-help';help.href='/global.html';help.textContent='Global guide';bar.append(help);
 const css=doc.createElement('link');css.rel='stylesheet';css.href='/assets/shop/i18n.css?v=20261018';doc.head.append(css);
 const observer=new win.MutationObserver(records=>{observer.disconnect();for(const record of records){if(record.type==='characterData')text(record.target);else if(record.type==='attributes')attr(record.target);else for(const node of record.addedNodes)walk(node);}observe();});
 function observe(){observer.observe(doc.body,{childList:true,subtree:true,characterData:true,attributes:true,attributeFilter:attributes});}
 function apply(persist){observer.disconnect();doc.documentElement.lang=locale;doc.documentElement.dataset.language=locale;select.value=locale;help.textContent=translate('글로벌 고객 안내',locale);walk(doc.body);if(doc.title!==titleOutput)titleSource=doc.title;titleOutput=translate(titleSource,locale);doc.title=titleOutput;if(persist){try{win.localStorage.setItem(languageKey,locale);}catch{}const url=new URL(win.location.href);url.searchParams.set('lang',locale);win.history.replaceState(win.history.state,'',url);}observe();doc.dispatchEvent(new win.CustomEvent('shop:language-changed',{detail:{language:locale}}));}
 select.addEventListener('change',()=>{locale=select.value;apply(true);});
 win.addEventListener('storage',event=>{if(event.key===languageKey&&languageIds.has(event.newValue)){locale=event.newValue;apply(false);}});
 apply(false);return {get language(){return locale;},disconnect(){observer.disconnect();}};
}
if(typeof document!=='undefined'&&typeof window!=='undefined'){if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>mountLanguageUI(),{once:true});else mountLanguageUI();}
