'use strict';
const {ShopError}=require('./security.cjs');
const lineKey=line=>JSON.stringify([line.id,line.option||'']);
const lineView=line=>({id:line.id,option:line.option||'',name:line.name,quantity:line.quantity});
function shipments(row,customer){
 if(customer.rental)return [];
 if(Array.isArray(customer._admin_shipments))return customer._admin_shipments;
 if(row.fulfillment==='shipped')return [{id:'legacy',purpose:'original',items:JSON.parse(row.lines_json).map(lineView),carrier:row.carrier||'',tracking:row.tracking||'',created_at:null,updated_at:null}];
 return [];
}
function publicShipments(rows){
 return rows.map(s=>({id:s.id,purpose:s.purpose,case_id:s.case_id||null,items:s.items.map(lineView),carrier:s.carrier,tracking:s.tracking,created_at:s.created_at,updated_at:s.updated_at,delivery_status:s.delivered_at?'delivered':'in_transit',delivered_at:s.delivered_at||null,delivery_source:s.delivered_at?(s.delivery_source||'manual'):null}));
}
function purchaseWorkflow(row,customer){
 if(customer.rental||row.state!=='PAID'||row.payment_mode!=='live')return null;
 const history=shipments(row,customer),originals=history.filter(s=>s.purpose==='original');
 const delivered=row.fulfillment==='shipped'&&originals.length>0&&originalRemaining(row,history).length===0&&originals.every(s=>s.delivered_at);
 const stage=delivered?'delivered':row.fulfillment!=='unfulfilled'?'in_transit':customer._admin_purchase_workflow?.stage==='ready'?'ready':'preparing';
 return {stage,partial:row.fulfillment==='processing',delivered_at:delivered?Math.max(...originals.map(s=>s.delivered_at)):null,delivery_source:delivered?(originals.every(s=>s.delivery_source==='goodsflow')?'goodsflow':'manual'):null};
}
function remaining(allowed,used=[]){
 const counts=new Map();
 for(const item of used){const key=lineKey(item);if(!Number.isSafeInteger(item.quantity)||item.quantity<1)throw new ShopError(409,'저장된 품목 수량을 확인해주세요.');counts.set(key,(counts.get(key)||0)+item.quantity);}
 const keys=new Set(allowed.map(lineKey));
 if([...counts.keys()].some(key=>!keys.has(key)))throw new ShopError(409,'저장된 출고 품목과 주문을 확인해주세요.');
 return allowed.map(item=>{const quantity=item.quantity-(counts.get(lineKey(item))||0);if(!Number.isSafeInteger(quantity)||quantity<0)throw new ShopError(409,'이미 처리한 수량을 다시 확인해주세요.');return {...lineView(item),quantity};}).filter(item=>item.quantity>0);
}
function selectItems(input,allowed,{optional=false}={}){
 if(input===undefined&&optional)input=allowed.map(({id,option,quantity})=>({id,option,quantity}));
 if(!Array.isArray(input)||!input.length||input.length>30)throw new ShopError(400,'처리할 상품과 수량을 선택해주세요.');
 const source=new Map(allowed.map(item=>[lineKey(item),item])),seen=new Set();
 return input.map(item=>{
  if(!item||typeof item.id!=='string'||typeof item.option!=='string'||!Number.isSafeInteger(item.quantity)||item.quantity<1)throw new ShopError(400,'상품 구성과 수량을 확인해주세요.');
  const key=lineKey(item),original=source.get(key);
  if(seen.has(key))throw new ShopError(400,'같은 상품·구성은 수량으로 합쳐주세요.');seen.add(key);
  if(!original||item.quantity>original.quantity)throw new ShopError(409,'처리 가능한 잔여 수량을 초과했습니다. 최신 내역을 확인해주세요.');
  return {...lineView(original),quantity:item.quantity};
 });
}
function tracking(input){
 if(typeof input.carrier!=='string'||typeof input.tracking!=='string'||!/^[가-힣a-zA-Z0-9 .-]{2,40}$/.test(input.carrier)||!/^\d[\d-]{5,29}$/.test(input.tracking))throw new ShopError(400,'택배사와 운송장 번호를 확인해주세요.');
 return {carrier:input.carrier,tracking:input.tracking};
}
function originalRemaining(row,history){return remaining(JSON.parse(row.lines_json),history.filter(s=>s.purpose==='original').flatMap(s=>s.items));}
function caseRemaining(shipment,cases){return remaining(shipment.items,cases.filter(c=>c.shipment_id===shipment.id&&c.status!=='rejected').flatMap(c=>c.items));}
function replacementRemaining(item,history){return remaining(item.items,history.filter(s=>s.purpose==='exchange'&&s.case_id===item.id).flatMap(s=>s.items));}
function adminCases(cases,history){
 return cases.map(item=>{if(item.kind!=='exchange')return {...item};const replacement_remaining=replacementRemaining(item,history);return {...item,replacement_remaining,replacement_complete:replacement_remaining.length===0};});
}
module.exports={shipments,publicShipments,remaining,selectItems,tracking,originalRemaining,caseRemaining,replacementRemaining,adminCases,purchaseWorkflow};

const INVOICE_HEADERS=['operation','order_id','version','shipment_id','carrier','tracking','item_id','option','quantity'];
function invoiceCSV(text){
 const rows=[];let row=[],cell='',quoted=false,closed=false;
 for(let i=0;i<text.length;i++){
  const c=text[i];
  if(quoted){if(c==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;closed=true;}}else cell+=c;continue;}
  if(c==='"'){if(cell||closed)throw new ShopError(400,'CSV 따옴표 형식을 확인해주세요.');quoted=true;continue;}
  if(c===','||c==='\r'||c==='\n'){
   row.push(cell);cell='';closed=false;
   if(c!==','){if(c==='\r'&&text[i+1]==='\n')i++;rows.push(row);row=[];if(rows.length>502)throw new ShopError(413,'송장 파일은 데이터 500행까지 지원합니다.');}continue;
  }
  if(closed)throw new ShopError(400,'CSV 닫는 따옴표 뒤의 내용을 확인해주세요.');cell+=c;
 }
 if(quoted)throw new ShopError(400,'CSV 따옴표가 닫히지 않았습니다.');
 if(cell||row.length||closed){row.push(cell);rows.push(row);}
 return rows;
}
function boundedZip(bytes){
 // Validate and inflate every entry under hard limits before the workbook parser.
 // A tiny compressed file must not allocate an unbounded XML/shared-string table.
 const zlib=require('node:zlib');let end=-1;
 for(let i=bytes.length-22;i>=Math.max(0,bytes.length-65557);i--)if(bytes.readUInt32LE(i)===0x06054b50){end=i;break;}
 if(end<0)throw new ShopError(400,'정상 XLSX 파일을 선택해주세요.');
 const count=bytes.readUInt16LE(end+10),start=bytes.readUInt32LE(end+16);if(!count||count>100)throw new ShopError(413,'XLSX 구성은 100개 파일 이내로 제한됩니다.');
 let offset=start,total=0;
 try{for(let n=0;n<count;n++){
  if(bytes.readUInt32LE(offset)!==0x02014b50)throw Error();
  const flags=bytes.readUInt16LE(offset+8),method=bytes.readUInt16LE(offset+10),compressed=bytes.readUInt32LE(offset+20),size=bytes.readUInt32LE(offset+24),name=bytes.readUInt16LE(offset+28),extra=bytes.readUInt16LE(offset+30),comment=bytes.readUInt16LE(offset+32),local=bytes.readUInt32LE(offset+42);
  if(flags&1||![0,8].includes(method)||size>8388608||total+size>8388608||bytes.readUInt32LE(local)!==0x04034b50)throw Error();
  const begin=local+30+bytes.readUInt16LE(local+26)+bytes.readUInt16LE(local+28);if(begin+compressed>bytes.length)throw Error();
  const data=bytes.subarray(begin,begin+compressed),raw=method===8?zlib.inflateRawSync(data,{maxOutputLength:8388608-total}):data;
  if(raw.length!==size)throw Error();total+=raw.length;offset+=46+name+extra+comment;
 }}catch{throw new ShopError(400,'손상되었거나 압축 해제 용량 8MiB를 초과한 XLSX입니다. CSV로 저장해 다시 확인해주세요.');}
}
async function invoiceFile(input){
 if(typeof input.file_base64==='string'&&input.file_base64.length>1398104)throw new ShopError(413,'송장 파일은 1MiB(1,048,576바이트)까지 지원합니다.');
 if(typeof input.filename!=='string'||!/\.(csv|xlsx)$/i.test(input.filename)||typeof input.file_base64!=='string'||!input.file_base64.length||input.file_base64.length%4||!/^[A-Za-z0-9+/]*={0,2}$/.test(input.file_base64))throw new ShopError(400,'1MiB(1,048,576바이트) 이하의 CSV 또는 XLSX 파일을 선택해주세요.');
 const bytes=Buffer.from(input.file_base64,'base64');if(bytes.length>1048576)throw new ShopError(413,'송장 파일은 1MiB(1,048,576바이트)까지 지원합니다.');
 let rows;
 if(/\.csv$/i.test(input.filename)){
  let value;try{value=new TextDecoder('utf-8',{fatal:true}).decode(bytes);}catch{throw new ShopError(400,'CSV를 UTF-8 형식으로 저장해주세요.');}
  rows=invoiceCSV(value.replace(/^\ufeff/,''));
 }else{
  boundedZip(bytes);const ExcelJS=require('exceljs'),book=new ExcelJS.Workbook();
  try{await book.xlsx.load(bytes);}catch{throw new ShopError(400,'XLSX 내용을 읽을 수 없습니다. CSV로 저장해 다시 확인해주세요.');}
  if(book.worksheets.length!==1)throw new ShopError(400,'송장 XLSX는 한 개 시트만 포함해야 합니다.');
  const sheet=book.worksheets[0];if(sheet.rowCount>501||sheet.columnCount>9)throw new ShopError(413,'송장 파일은 데이터 500행과 지정된 9개 열까지 지원합니다.');
  rows=[];for(let r=1;r<=sheet.rowCount;r++){
   const row=[];for(let c=1;c<=9;c++){
    const value=sheet.getCell(r,c).value;
    if(value!==null&&typeof value!=='string'&&!(r>1&&[3,9].includes(c)&&typeof value==='number'&&Number.isSafeInteger(value)))throw new ShopError(400,r+'행: 수식·링크·숫자형 운송장을 사용할 수 없습니다. 운송장과 식별자는 텍스트로 저장해주세요.');
    row.push(value==null?'':String(value));
   }rows.push(row);
  }
 }
 while(rows.length&&rows.at(-1).every(cell=>cell===''))rows.pop();
 if(rows.length<2||rows.length>501)throw new ShopError(400,'송장 파일에는 데이터 1~500행이 필요합니다.');
 if(rows[0].length!==9||rows[0].some((cell,i)=>cell.trim()!==INVOICE_HEADERS[i]))throw new ShopError(400,'송장 파일의 9개 열 이름과 순서를 양식과 일치시켜주세요.');
 return {bytes,rows:rows.slice(1)};
}
module.exports.invoiceFile=invoiceFile;
module.exports.INVOICE_HEADERS=INVOICE_HEADERS;
