"""Resident anonymous Chromium. No account or application data is accepted."""
import asyncio
import base64
import hmac
import logging
import os
import time
from contextlib import asynccontextmanager
from urllib.parse import urlsplit, unquote

from fastapi import FastAPI, Header, HTTPException, Depends
from pydantic import BaseModel, ConfigDict, Field
from playwright.async_api import async_playwright
from playwright_stealth import Stealth

KEY = os.environ.get("SENTINEL_SOLVER_KEY", "")
TIMEZONE = os.environ.get("SENTINEL_SOLVER_TIMEZONE", "")
lock = asyncio.Lock()
page = None

# Keep field ordering in sync with the current 25-field requirements format.
PREPARE = """() => {
 const p = [screen.width + screen.height, new Date().toString(),
 performance.memory.jsHeapSizeLimit, 1, navigator.userAgent,
 performance.getEntriesByType('resource').map(e => e.name).find(s => /sentinel.*sdk.*\\.js/.test(s)) ||
 Array.from(document.scripts).map(s => s.src).find(s => typeof s === 'string' && s.includes('sentinel')) ||
 'https://chatgpt.com/backend-api/sentinel/sdk.js',
 document.documentElement.dataset.build || '', navigator.language,
 navigator.languages.join(','), Math.random(),
 'webdriver−' + navigator.webdriver, Object.keys(document)[0] || 'location',
 Object.keys(window)[0] || 'window', performance.now(), crypto.randomUUID(), '',
 navigator.hardwareConcurrency, performance.timeOrigin, 0,0,0,0,0,0,0];
 return {p: 'gAAAAAC' + btoa(unescape(encodeURIComponent(JSON.stringify(p)))),
 user_agent: navigator.userAgent, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
 timezone_offset_min: new Date().getTimezoneOffset(),
 sec_ch_ua: navigator.userAgentData.brands.map(b => '"'+b.brand+'";v="'+b.version+'"').join(', '),
 platform: navigator.userAgentData.platform};
}"""

# Uses the website's current module, discovered from the anonymous page assets.
# WeakMap binding follows MEIZU16/chatgpt2api's resident-page approach.
SOLVE = """async ({dx, p}) => {
 let asset = performance.getEntriesByType('resource').map(e => e.name)
   .find(s => /\\/turnstile-[^/]+\\.js/.test(s));
 const sources = [...new Set([...Array.from(document.scripts).map(s => s.src),
   ...performance.getEntriesByType('resource').map(e => e.name)])]
   .filter(s => typeof s === 'string' && s.startsWith(location.origin) && /\\.js(?:[?]|$)/.test(s));
 if (!asset) for (const source of sources.slice(0, 128)) {
   const text = await (await fetch(source)).text();
   const match = text.match(/(?:\\/unauth-mweb\\/assets\\/|\\.\\/|\\/assets\\/)?turnstile-[A-Za-z0-9_-]+\\.js/);
   if (match) { asset = new URL(match[0], source).href; break; }
 }
 if (!asset) throw Error('current Turnstile module not found');
 const mod = await import(asset);
 const ts = mod.turnstile || mod.default?.turnstile;
 if (!ts?.getEnforcementToken) throw Error('Turnstile export missing');
 const req = {turnstile: {required: true, dx}};
 const original = WeakMap.prototype.get;
 WeakMap.prototype.get = function(target) {
   if (this === ts.tokenCache) return original.call(this, target);
   return target === req ? p : original.call(this, target);
 };
 try { return await ts.getEnforcementToken(req); }
 finally { WeakMap.prototype.get = original; }
}"""


@asynccontextmanager
async def lifespan(app):
    global page
    if not KEY or not TIMEZONE:
        raise RuntimeError("solver key and verified egress timezone are required")
    async with async_playwright() as pw:
        proxy_url = os.environ.get("SENTINEL_SOLVER_PROXY", "")
        kwargs = {}
        if proxy_url:
            parts = urlsplit(proxy_url)
            kwargs["proxy"] = {"server": f"{parts.scheme}://{parts.hostname}:{parts.port}"}
            if parts.username:
                kwargs["proxy"].update(username=unquote(parts.username), password=unquote(parts.password or ""))
        browser = await pw.chromium.launch(channel="chromium", headless=False,
            args=["--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"], **kwargs)
        major = browser.version.split(".")[0]
        ua = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
              f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36")
        context = await browser.new_context(locale="en-US", timezone_id=TIMEZONE,
            user_agent=ua, viewport={"width": 1920, "height": 1080})
        await Stealth().apply_stealth_async(context)
        page = await context.new_page()
        yield
        await context.close()
        await browser.close()


def authenticate(authorization: str = Header(default="")):
    if not KEY or not hmac.compare_digest(authorization, "Bearer " + KEY):
        raise HTTPException(401, "unauthorized")


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None,
              dependencies=[Depends(authenticate)])


class Challenge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    p: str = Field(min_length=8, max_length=32768)
    dx: str = Field(min_length=1, max_length=1000000)


class PrepareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


@app.post("/v1/prepare")
async def prepare(body: PrepareRequest):
    async with lock:
        try:
            if page.url != "https://chatgpt.com/":
                await page.goto("https://chatgpt.com/", wait_until="domcontentloaded", timeout=60000)
            deadline = time.monotonic() + 60
            while True:
                title = await page.title()
                ready = "chatgpt" in title.lower()
                if ready and not any(s in title for s in ("Just a moment", "Attention Required", "请稍候")):
                    break
                if time.monotonic() > deadline:
                    raise RuntimeError(f"anonymous Chromium is not ready: title={title!r}")
                await asyncio.sleep(1)
            return await page.evaluate(PREPARE)
        except Exception as exc:
            logging.getLogger(__name__).exception("anonymous browser preparation failed")
            raise HTTPException(503, "anonymous browser is not ready") from exc


@app.post("/v1/turnstile")
async def turnstile(body: Challenge):
    async with lock:
        try:
            token = await asyncio.wait_for(page.evaluate(SOLVE, body.model_dump()), timeout=120)
            if not isinstance(token, str) or not token or token == body.p:
                raise ValueError("empty or echoed token")
            decoded = base64.b64decode(token, validate=True).decode()
            if ": " in decoded or decoded.isdigit():
                raise ValueError("challenge returned an error or timeout")
            return {"token": token}
        except Exception as exc:
            logging.getLogger(__name__).exception("anonymous browser challenge failed")
            raise HTTPException(503, "browser challenge failed") from exc


@app.get("/health")
async def health():
    return {"ready": page is not None and not page.is_closed(), "timezone": TIMEZONE}
