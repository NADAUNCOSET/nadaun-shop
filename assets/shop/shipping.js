// Owner-approved domestic base fee, once per purchase order.
// The server must recompute this with current product records before payment.
export function shippingFee(products){
 const purchase=products.filter(p=>p?.kind==='purchase');
 if(!purchase.length)return null;
 return purchase.some(p=>p.shipping_class==='heavy_stand')?7000:4500;
}
