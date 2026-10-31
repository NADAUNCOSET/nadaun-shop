const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const routes=JSON.parse(fs.readFileSync('vercel.json','utf8')).routes;
function redirect(host,path){
 for(const r of routes){
  if(!r.src||!r.headers?.Location)continue;
  const m=path.match(new RegExp(r.src));if(!m)continue;
  if(r.has?.some(h=>h.type==='host'&&!new RegExp('^'+h.value+'$').test(host)))continue;
  return {status:r.status,url:r.headers.Location.replace(/\$(\d+)/g,(_,n)=>m[n])};
 }
}
test('test page entered from order uses the shop origin, without a canonical redirect loop',()=>{
 assert.deepEqual(redirect('order.nadaun.co','/payment-test.html'),{status:308,url:'https://shop.nadaun.co/payment-test.html'});
 assert.equal(redirect('shop.nadaun.co','/payment-test.html'),undefined);
});
test('extensionless test links resolve on both shop and order',()=>{
 for(const host of ['shop.nadaun.co','order.nadaun.co'])for(const path of ['/payment-test','/payment-test/'])assert.deepEqual(redirect(host,path),{status:308,url:'https://shop.nadaun.co/payment-test.html'});
});
test('existing account and full-order test redirects retain their hosts and paths',()=>{
 for(const page of ['account','test-shop','test-admin']){
  assert.deepEqual(redirect('order.nadaun.co','/'+page+'.html'),{status:308,url:'https://shop.nadaun.co/'+page+'.html'});
  assert.equal(redirect('shop.nadaun.co','/'+page+'.html'),undefined);
 }
});
