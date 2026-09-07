'use strict';
const crypto=require('node:crypto');
const {promisify}=require('node:util');
const scrypt=promisify(crypto.scrypt);
class ShopError extends Error {constructor(status,message){super(message);this.status=status;}}
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const random=()=>crypto.randomBytes(32).toString('base64url');
function keyFrom(value){if(!/^[a-f0-9]{64}$/i.test(value||''))throw new ShopError(503,'주문 서비스 연결을 준비 중입니다.');return Buffer.from(value,'hex');}
function protect(secret){
 const key=keyFrom(secret);
 return {
  encrypt(data){const iv=crypto.randomBytes(12),cipher=crypto.createCipheriv('aes-256-gcm',key,iv);const body=Buffer.concat([cipher.update(JSON.stringify(data),'utf8'),cipher.final()]);return Buffer.concat([iv,cipher.getAuthTag(),body]).toString('base64url');},
  decrypt(value){const raw=Buffer.from(value,'base64url');const decipher=crypto.createDecipheriv('aes-256-gcm',key,raw.subarray(0,12));decipher.setAuthTag(raw.subarray(12,28));return JSON.parse(Buffer.concat([decipher.update(raw.subarray(28)),decipher.final()]).toString('utf8'));}
 };
}
function sessions(secret,clock=()=>Date.now()){
 const key=keyFrom(secret);
 const signature=value=>crypto.createHmac('sha256',key).update(value).digest();
 return {
  issue(subject,role,seconds){const body=Buffer.from(JSON.stringify({sub:subject,role,exp:clock()+seconds*1000})).toString('base64url');return body+'.'+signature(body).toString('base64url');},
  read(token,role){try{const [body,sig,...extra]=String(token||'').split('.');if(extra.length||!body||!sig)return null;const given=Buffer.from(sig,'base64url'),expected=signature(body);if(given.length!==expected.length||!crypto.timingSafeEqual(given,expected))return null;const value=JSON.parse(Buffer.from(body,'base64url'));return value.role===role&&typeof value.sub==='string'&&value.exp>clock()?value.sub:null;}catch{return null;}}
 };
}
async function passwordHash(value){if(typeof value!=='string'||value.length<16||value.length>128)throw new ShopError(400,'관리자 비밀번호는 16~128자로 지정해주세요.');const salt=random();return salt+':'+(await scrypt(value,salt,64)).toString('hex');}
async function passwordMatches(value,stored){if(typeof value!=='string'||value.length>128||typeof stored!=='string')return false;const [salt,hex]=stored.split(':');if(!salt||!/^[a-f0-9]{128}$/.test(hex||''))return false;const computed=await scrypt(value,salt,64);return crypto.timingSafeEqual(computed,Buffer.from(hex,'hex'));}
module.exports={ShopError,hash,random,protect,sessions,passwordHash,passwordMatches};
