const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const rental=require('../../assets/shop/rental-content.js');
const {rentalSchedule}=require('../../server/commerce/rental.cjs');

function fixture(saved={},now='2026-10-16T00:00:00Z'){
 const fields=Object.fromEntries(['start_date','end_date','pickup_time','return_time','quantity','option'].map(name=>[name,{value:name==='quantity'?'1':'',min:'',max:'',disabled:false,error:'',events:{},setCustomValidity(value){this.error=value;},addEventListener(name,fn){this.events[name]=fn;},reportValidity(){return this.disabled||(!this.error&&(name==='option'||this.value!=='')&&(!this.min||this.value>=this.min)&&(!this.max||this.value<=this.max));}}]));
 const preview={textContent:''},window={textContent:''},feedback={hidden:true,textContent:''},save={},writes=[];
 const nodes={'[data-rental-preview]':preview,'[data-rental-window]':window,'[data-rental-feedback]':feedback,'[data-rental-submit]':{},'[data-rental-save]':save};
 const form={dataset:{productId:'rental-test'},isConnected:true,querySelector(selector){const name=selector.match(/^\[name="([a-z_]+)"\]$/)?.[1];return name?fields[name]:nodes[selector]||null;}};
 class Clock extends Date{static now(){return Date.parse(now);}}
 const context=vm.createContext({module:{exports:{}},Date:Clock,console,localStorage:{getItem(){return JSON.stringify(saved);},setItem(key,value){writes.push(JSON.parse(value));}},fetch:async()=>({ok:true,json:async()=>({rentalRequestsEnabled:false})})});
 vm.runInContext(fs.readFileSync('assets/shop/rental-content.js','utf8'),context);
 context.module.exports.mount({querySelector(selector){return selector==='[data-rental-request]'?form:null;},querySelectorAll(){return [];}});
 return {fields,preview,window,writes,save(){save.onclick();},setClock(value){now=value;},change(name,value){fields[name].value=value;fields[name].events.change();}};
}

test('one calendar month clamps month ends and handles leap years and December',()=>{
 for(const [start,end] of [['2026-10-16','2026-11-16'],['2026-01-31','2026-02-28'],['2028-01-31','2028-02-29'],['2028-02-29','2028-03-29'],['2026-12-31','2027-01-31']])assert.equal(rental.calendarMonthLimit(start),end);
 for(const day of ['',null,'2026-02-30','2026-13-01','2026-1-01'])assert.equal(rental.calendarMonthLimit(day),'');
});

test('both calendars end one month from KST today regardless of pickup date',()=>{
 const f=fixture();assert.equal(f.fields.end_date.disabled,true);assert.equal(f.fields.start_date.min,'2026-10-16');assert.equal(f.fields.start_date.max,'2026-11-16');assert.equal(f.fields.end_date.max,'2026-11-16');
 f.change('start_date','2026-10-31');assert.equal(f.fields.end_date.disabled,false);assert.equal(f.fields.end_date.min,'2026-10-31');assert.equal(f.fields.end_date.max,'2026-11-16');
 f.change('start_date','2026-12-01');assert.match(f.fields.start_date.error,/오늘부터 한 달/);assert.equal(f.fields.end_date.disabled,true);assert.equal(f.fields.end_date.max,'2026-11-16');
 f.change('start_date','');assert.equal(f.fields.end_date.disabled,true);assert.equal(f.fields.end_date.max,'2026-11-16');
});

test('saved drafts outside the new calendar range are shown as invalid and cannot be resaved',()=>{
 const f=fixture({start_date:'2026-10-31',end_date:'2026-12-01',pickup_time:'12:15',return_time:'12:15',quantity:'1',option:''});
 assert.equal(f.fields.end_date.value,'2026-12-01');assert.match(f.fields.end_date.error,/한 달 이내/);assert.match(f.preview.textContent,/한 달 이내/);f.save();assert.equal(f.writes.length,0);
 f.change('end_date','2026-11-14');assert.equal(f.fields.end_date.error,'');assert.equal(f.fields.return_time.error,'');f.save();assert.equal(f.writes.length,1);
 f.change('start_date','2026-11-20');assert.equal(f.fields.end_date.disabled,true);assert.equal(f.fields.end_date.max,'2026-11-16');f.save();assert.equal(f.writes.length,1);
});

test('browser and server enforce fourteen elapsed KST days down to the minute',()=>{
 for(const [now,start,end] of [['2026-10-16T00:00:00Z','2026-10-31','2026-11-14'],['2026-12-16T00:00:00Z','2026-12-25','2027-01-08']]){
  const raw={start_date:start,end_date:end,pickup_time:'12:15',return_time:'12:15'},f=fixture(raw,now);assert.equal(f.fields.return_time.error,'');f.save();assert.equal(f.writes.length,1);
  assert.doesNotThrow(()=>rentalSchedule(raw,()=>Date.parse(now)));
  f.change('return_time','12:16');assert.match(f.fields.return_time.error,/2주\(14일\)/);f.save();assert.equal(f.writes.length,1);
  assert.throws(()=>rentalSchedule({...raw,return_time:'12:16'},()=>Date.parse(now)),{status:400,message:f.fields.return_time.error});
  f.change('return_time','12:14');assert.equal(f.fields.return_time.error,'');
 }
});

test('month-end, leap-year and year-end bounds agree between form and server',()=>{
 for(const [today,limit,over] of [['2026-01-31','2026-02-28','2026-03-01'],['2028-01-31','2028-02-29','2028-03-01'],['2026-12-31','2027-01-31','2027-02-01']]){
  const now=today+'T00:00:00+09:00',raw={start_date:limit,end_date:limit,pickup_time:'12:00',return_time:'12:01'},f=fixture(raw,now);
  assert.equal(f.fields.start_date.max,limit);assert.equal(f.fields.end_date.max,limit);f.save();assert.equal(f.writes.length,1);assert.doesNotThrow(()=>rentalSchedule(raw,()=>Date.parse(now)));
  f.change('end_date',over);f.save();assert.equal(f.writes.length,1);assert.throws(()=>rentalSchedule({...raw,end_date:over},()=>Date.parse(now)),{status:400,message:f.fields.end_date.error});
  f.change('start_date',over);assert.throws(()=>rentalSchedule({...raw,start_date:over,end_date:over},()=>Date.parse(now)),{status:400,message:f.fields.start_date.error});
 }
});

test('KST midnight refreshes the window and invalidates a saved pickup that became past',()=>{
 const f=fixture({start_date:'2026-10-19',end_date:'2026-10-20',pickup_time:'23:59',return_time:'10:00'},'2026-10-19T14:58:00Z');
 assert.equal(f.fields.start_date.min,'2026-10-19');assert.equal(f.fields.start_date.max,'2026-11-19');
 f.setClock('2026-10-19T15:01:00Z');f.save();assert.equal(f.fields.start_date.min,'2026-10-20');assert.equal(f.fields.start_date.max,'2026-11-20');assert.match(f.fields.start_date.error,/오늘부터/);assert.equal(f.writes.length,0);
});
