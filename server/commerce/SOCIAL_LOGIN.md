# NADAUN SHOP social login

The existing member session, order owner and points wallet are shared by email
login and explicitly linked Kakao / Google / Naver identities. An equal email
address is never proof of account ownership and never causes automatic merging.

Production callbacks (register these exact HTTPS URLs in the respective app):

| Service | Callback |
| --- | --- |
| Kakao | `https://shop.nadaun.co/auth/kakao/callback` |
| Google | `https://shop.nadaun.co/auth/google/callback` |
| Naver | `https://shop.nadaun.co/auth/naver/callback` |

Each provider needs its own web-login app. Calendar desktop OAuth credentials
and Smartstore commerce credentials cannot be substituted.

Server-only variables, where `PROVIDER` is `KAKAO`, `GOOGLE` or `NAVER`:

- `SHOP_OAUTH_PROVIDER_CLIENT_ID`
- `SHOP_OAUTH_PROVIDER_CLIENT_SECRET`
- `SHOP_OAUTH_PROVIDER_ENABLED=true` only after app/domain/consent/review setup
- Optional `SHOP_OAUTH_KAKAO_JS_KEY` enables KakaoTalk handoff using official SDK
  2.8.3. Register `https://shop.nadaun.co` as the JavaScript SDK domain in the
  same app as its REST key. Without this key the REST web authorization is used.

Google requires a **Web application** client and only `openid profile email`.
Kakao needs login enabled, a registered callback and the allowed profile consent
items; Kakao Sync / automatic sign-up consent needs its separate app setup.
Naver needs Naver Login enabled, service URL, callback, allowed profile items
and service review as required by the developer console. Missing or unapproved
configuration leaves its button clearly disabled. Setting a key is not evidence
that provider approval or a real login test passed.

`GET /api/member-oauth?action=status` reports public readiness without keys.
`POST ...?action=start&provider=...` begins login (`mode=login`) or an explicit
recent-session link (`mode=link`). Callback state and browser cookies expire in
10 minutes and are consumed atomically. First-time users complete the site's
required age/terms/privacy form via `action=complete`. `action=cancel` clears
pending enrollment. Do not put provider tokens, secrets or pending tickets in
URLs, logs or browser storage. Tokens are used only for the server profile call.

Provider IDs are HMAC-protected and profiles are encrypted. OAuth-only accounts
have no password or password recovery credential. They can close their account
within 10 minutes of a fresh login. Closure erases identity bindings and profile;
rejoining never restores a previous wallet automatically. Existing email-member
password and recovery behavior is unchanged.

Apply the additive schema to both production and QA (`qa_shop_*`) namespaces.
QA mode derives separate encryption/HMAC keys and uses separate cookies. An
expired QA-mode cookie cannot complete a QA callback as a production login.
Keep operational order/payment/tax gates independent of member activation.

Verify after configuring each provider: new signup + consent, cancel, returning
login from a second browser, explicit link to an existing member, same orders /
wallet, wrong-session link rejection, logout and closure. Never claim real
provider login based on fixture tests. Source, private setup evidence and current
activation state: `_private/commerce/social-login-20261017/`.

Official implementation sources:

- https://developers.kakao.com/docs/ko/kakaologin/rest-api
- https://developers.kakao.com/docs/ko/kakaologin/js
- https://developers.kakao.com/docs/ko/javascript/download
- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/identity/openid-connect/openid-connect
- https://developers.naver.com/docs/login/api/api.md
