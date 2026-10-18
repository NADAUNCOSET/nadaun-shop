import {test} from 'node:test';
import assert from 'node:assert/strict';
import {resolveLanguage,translate,languages} from '../../assets/shop/i18n.js';
import {translations} from '../../assets/shop/i18n-data.js';
test('explicit supported language wins and invalid input never becomes a locale',()=>{
 assert.equal(resolveLanguage({query:'ja',stored:'en',browser:['ko-KR']}),'ja');
 assert.equal(resolveLanguage({query:'<script>',stored:'en',browser:['ko-KR']}),'en');
 assert.equal(resolveLanguage({query:'en-US',stored:'wrong',browser:['zh-TW']}),'zh-CN');
 assert.equal(resolveLanguage({browser:['de-DE','ja-JP']}),'ja');assert.equal(resolveLanguage({browser:['ko-KR','en']}),'ko');assert.equal(resolveLanguage({browser:['fr']}),'ko');
});
test('all interface phrases have all three translations and do not inject markup',()=>{
 assert.ok(Object.keys(translations).length>350);
 for(const [source,row] of Object.entries(translations))for(const language of languages.filter(l=>l.id!=='ko')){assert.ok(row[language.id],source);assert.doesNotMatch(row[language.id],/[<>]/);assert.equal(translate(source,language.id),row[language.id]);}
});
test('currency stays KRW, quantities and provider actions retain their meaning',()=>{
 assert.equal(translate('  450,000원 ','en'),'  450,000 KRW ');assert.equal(translate('-1,000원','ja'),'-1,000ウォン');
 assert.equal(translate('Google로 계속하기','en'),'Continue with Google');assert.equal(translate('네이버 · 연결됨','zh-CN'),'Naver · 已关联');
 assert.equal(translate('3개 구성 · 4개 선택','en'),'3 configurations · 4 items selected');assert.equal(translate('수량','ja'),'数量');
});
test('unknown product names and personal text are preserved, Korean restores source exactly',()=>{
 for(const value of ['SONY 소니 FE 90mm F2.8','james@nadaun.co','김태원','<img onerror=alert(1)>','여기에 없는 공급사 상세정보'])assert.equal(translate(value,'en'),value);
 assert.equal(translate('  로그인\n','ko'),'  로그인\n');assert.equal(translate('로그인','invalid'),'로그인');
});
