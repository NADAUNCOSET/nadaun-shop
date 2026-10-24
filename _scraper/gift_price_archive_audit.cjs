'use strict';
// Read-only boundary/VAT audit of every preserved public quantity-price table.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const pricing=require('../assets/shop/gift-pricing.js');
const root=path.resolve(__dirname,'..'),day=new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Seoul'}).replaceAll('-','');
const output=path.join(root,'_private/gift','archive-audit-'+day);fs.mkdirSync(output,{recursive:true});
const report={checked_at:new Date().toISOString(),products:0,options:0,tiers:0,cases:0,estimated:0,below_minimum:0,separate_quote_required:0,errors:[],source_requests:0,real_transactions:0};
const digest=crypto.createHash('sha256');
for(const name of fs.readdirSync(path.join(root,'data/gift/details')).filter(n=>/^[a-f0-9]{2}\.json$/.test(n)).sort()){
 const raw=fs.readFileSync(path.join(root,'data/gift/details',name));digest.update(name);digest.update(raw);
 for(const [id,detail] of Object.entries(JSON.parse(raw))){
  const p=detail.pricing;if(!p)continue;report.products++;
  try{pricing.validate(p);}catch(e){report.errors.push({id,kind:'public_calculator_rejects_table',message:e.message});continue;}
  for(const option of p.options){
   report.options++;report.tiers+=option.tiers.length;
   const samples=new Set([p.minimum_quantity,Math.max(1,p.minimum_quantity-1),...option.tiers.flatMap(t=>[t.minimum_quantity,Math.max(1,t.minimum_quantity-1)])]);
   for(const quantity of samples){
    report.cases++;
    try{
     const minimum=Math.max(p.minimum_quantity,option.tiers[0].minimum_quantity);
     if(quantity<minimum){
      const actual=pricing.calculate(p,quantity,option.id);
      if(actual.status!=='below_minimum'||actual.minimum_quantity!==minimum)throw Error('Minimum quantity boundary mismatch');
      report.below_minimum++;continue;
     }
     const eligible=option.tiers.filter(t=>t.minimum_quantity<=quantity),tier=eligible[eligible.length-1];
     const subtotal=BigInt(tier.unit_price_ex_vat)*BigInt(quantity),total=(subtotal*110n+50n)/100n;
     if(total>100000000n){
      let caught=false;try{pricing.calculate(p,quantity,option.id);}catch(e){if(!/큰 금액/.test(e.message))throw e;caught=true;}
      if(!caught)throw Error('Oversized order did not require a separate quote');
      report.separate_quote_required++;continue;
     }
     const actual=pricing.calculate(p,quantity,option.id);
     if(actual.status!=='estimated'||actual.unit_price_ex_vat!==tier.unit_price_ex_vat||actual.subtotal_ex_vat!==Number(subtotal)||actual.vat!==Number(total-subtotal)||actual.total_including_vat!==Number(total)||actual.shipping_included!==false)throw Error('Tier or complete-subtotal VAT mismatch');
     report.estimated++;
    }catch(e){report.errors.push({id,option_id:option.id,quantity,message:e.message});}
   }
  }
 }
}
report.price_buckets_sha256=digest.digest('hex');report.error_count=report.errors.length;
fs.writeFileSync(path.join(output,'calculation-audit.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({...report,errors:report.errors.slice(0,10)}));
if(report.error_count)process.exitCode=1;
