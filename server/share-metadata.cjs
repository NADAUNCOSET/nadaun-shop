const crypto=require('node:crypto');
const ORIGIN='https://shop.nadaun.co';
const esc=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const text=value=>String(value??'').replace(/\s+/g,' ').trim();

function imageURL(value){
 try{const url=new URL(text(value),ORIGIN);return ['http:','https:'].includes(url.protocol)&&!url.username&&!url.password?url.href:null;}catch{return null;}
}
function shareImageURL(kind,product){
 const version=crypto.createHash('sha256').update('share-jpeg-v1\0'+(imageURL(product.image)||'')).digest('hex').slice(0,16);
 return ORIGIN+'/share-image.jpg?'+new URLSearchParams({kind,id:String(product.id),v:version});
}
function socialMetadata(template,{title,description,canonical,image,imageAlt,siteName='나다운 스페이스',width,height}){
 title=text(title);description=Array.from(text(description)).slice(0,80).join('');
 const tags=[['name','description',description],['property','og:type','website'],['property','og:site_name',siteName],['property','og:locale','ko_KR'],['property','og:title',title],['property','og:description',description],['property','og:url',canonical],['name','twitter:card',image?'summary_large_image':'summary'],['name','twitter:title',title],['name','twitter:description',description]];
 if(image){
  tags.push(['property','og:image',image],['property','og:image:secure_url',image],['property','og:image:type','image/jpeg'],['property','og:image:alt',imageAlt||title],['name','twitter:image',image],['name','twitter:image:alt',imageAlt||title]);
  if(width&&height)tags.push(['property','og:image:width',width],['property','og:image:height',height]);
 }
 // Replace the entire metadata set: inherited logo/duplicate tags must never win
 // over the product identity when a crawler reads only the initial HTML.
 return template.replace(/<title>[\s\S]*?<\/title>/i,()=>'<title>'+esc(title)+'</title>')
  .replace(/<meta\b[^>]*\b(?:name|property)\s*=\s*["'](?:description|og:[^"']+|twitter:[^"']+)["'][^>]*>/gi,'')
  .replace(/<link\b[^>]*\brel\s*=\s*["']canonical["'][^>]*>/gi,'')
  .replace(/<\/head>/i,()=>tags.map(([attr,key,value])=>`<meta ${attr}="${key}" content="${esc(value)}">`).join('\n')+`\n<link rel="canonical" href="${esc(canonical)}">\n</head>`);
}
module.exports={ORIGIN,esc,imageURL,shareImageURL,socialMetadata};
