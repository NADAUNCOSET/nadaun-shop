(function(root){
 'use strict';
 // Keep a card interface and its type in one search token: the A in a brand
 // or category must not make a Type B card match a Type A query.
 function prepare(value){return String(value??'').normalize('NFKC').toLocaleLowerCase()
  .replace(/(?:\bcf\s*express|\bcfe|cf\s*익스프레스|씨에프\s*익스프레스)(?:\s*[24]\.0)?\s*[- ]?\s*(?:type\s*)?([ab])(?:\s*타입|\b)/gi,(_,type)=>'cfexpress'+type.toLowerCase())
  .replace(/타월/g,'타올').replace(/에코백/g,'에코가방');}
 const normalize=value=>prepare(value).replace(/\s+/g,'');
 const tokens=value=>prepare(value).trim().slice(0,120).split(/[\s,，]+/).filter(Boolean);
 const api={normalize,tokens};
 if(typeof module==='object'&&module.exports)module.exports=api;
 else root.NadaunProductSearch=api;
})(typeof globalThis!=='undefined'?globalThis:this);
