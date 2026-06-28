// Copyright (c) 2026, AFMCO and contributors
const e="966";function a(r,i=e){let s=(r||"").trim();if(!s)return"";const n=s.startsWith("+");let t=s.replace(/[^\d]/g,"");return!n&&t.startsWith("00")?(t=t.slice(2),t):n||t.startsWith(i)?t:t.startsWith("0")?i+t.slice(1):i+t}function u(r){return"https://wa.me/"+a(r)}export{u as w};
