# Diagnostic ONLY, on a dedicated branch. Does not alter the dashboard.
import asyncio, json, os, re, shutil, subprocess, time
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urlsplit
from playwright.async_api import async_playwright

BASE="https://www.ishikawa-railway.jp/ishi-train/"
OUT=Path("ir-capture")
OUT.mkdir(exist_ok=True)
TRAIN_RE=re.compile(r"(?<![0-9A-Za-z])\d{2,5}[MD]\b")
responses=[]
browser_errors=[]
pending=[]
def train_numbers(s):
    return sorted(set(TRAIN_RE.findall(str(s))))

async def main():
    started=datetime.now(timezone.utc).isoformat()
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,args=["--no-sandbox"])
        context=await browser.new_context(
            viewport={"width":1280,"height":1000},
            device_scale_factor=2,locale="ja-JP",timezone_id="Asia/Tokyo",
            ignore_https_errors=False)
        page=await context.new_page()
        def note_console(msg):
            if msg.type=="error" and len(browser_errors)<20:
                browser_errors.append("console: "+msg.text[:280])
        page.on("console",note_console)
        page.on("pageerror",lambda exc:browser_errors.append("js: "+str(exc)[:280]))
        async def capture_response(r):
            parsed=urlsplit(r.url)
            if parsed.hostname not in ("www.ishikawa-railway.jp","ishikawa-railway.jp"):
                return
            ctype=r.headers.get("content-type","").lower()
            record={"url":r.url,"status":r.status,
                    "content_type":ctype,"method":r.request.method}
            # Read JSON/text only, never execute any returned code.
            if ("json" in ctype or "javascript" in ctype
                    or r.request.resource_type in ("xhr","fetch")):
                try:
                    body=await r.body()
                    record["bytes"]=len(body)
                    decoded=body[:250000].decode("utf-8","replace")
                    record["train_numbers"]=train_numbers(decoded)
                    if "json" in ctype or r.request.resource_type in ("xhr","fetch"):
                        record["body_sample"]=decoded[:14000]
                    else:
                        record["script_keywords"]=sorted(set(
                            re.findall(r'["\x27][^"\x27\s]{1,80}(?:\.json|\.php|\/api\/)[^"\x27\s]*["\x27]',decoded)))[:30]
                except Exception as exc:
                    record["read_error"]=str(exc)[:160]
            responses.append(record)
        page.on("response",lambda resp:pending.append(asyncio.create_task(capture_response(resp))))
        navigation_error=""
        try:
            res=await page.goto(BASE,wait_until="domcontentloaded",timeout=25000)
            print("NAV",res.status if res else None,page.url)
            await page.wait_for_timeout(8500)
        except Exception as exc:
            navigation_error=str(exc)
            print("NAV_ERROR",navigation_error)
        await asyncio.gather(*pending,return_exceptions=True)
        screenshot=OUT/"ir-current.png"
        try:
            await page.screenshot(path=str(screenshot),full_page=True,
                                  animations="disabled",timeout=15000)
            print("SCREENSHOT",str(screenshot),screenshot.stat().st_size)
        except Exception as exc:
            print("SCREENSHOT_ERROR",str(exc))
        try:
            dom_text=(await page.locator("body").inner_text(timeout=3000))[:18000]
        except Exception as exc:
            dom_text="DOM_ERROR: "+str(exc)
        html=await page.content()
        (OUT/"rendered-dom.html").write_text(html,encoding="utf-8")
        (OUT/"rendered-text.txt").write_text(dom_text,encoding="utf-8")
        dom_numbers=train_numbers(dom_text)
        json_records=[r for r in responses if
                      ("json" in r.get("content_type","")
                       or r.get("method")=="POST"
                       or r.get("body_sample"))]
        network_numbers=sorted(set(n for r in json_records for n in r.get("train_numbers",[])))
        image_text=""
        image_numbers=[]
        if screenshot.exists() and shutil.which("tesseract"):
            proc=subprocess.run(
                ["tesseract",str(screenshot),"stdout","-l","eng","--psm","11"],
                text=True,capture_output=True,timeout=50)
            image_text=proc.stdout
            image_numbers=train_numbers(image_text)
            print("OCR_EXIT",proc.returncode)
        else:
            print("OCR_NOT_AVAILABLE")
        (OUT/"image-ocr.txt").write_text(image_text,encoding="utf-8")
        report={
            "captured_at_utc":datetime.now(timezone.utc).isoformat(),
            "started_at_utc":started,
            "page_url":page.url,"navigation_error":navigation_error,
            "page_title":await page.title(),"response_count":len(responses),
            "responses":responses,
            "dom_train_numbers":dom_numbers,"json_train_numbers":network_numbers,
            "screenshot_ocr_train_numbers":image_numbers,
            "dom_network_matches":sorted(set(dom_numbers)&set(network_numbers)),
            "image_network_matches":sorted(set(image_numbers)&set(network_numbers)),
            "image_network_only":sorted(set(image_numbers)-set(network_numbers)),
            "network_image_only":sorted(set(network_numbers)-set(image_numbers)),
            "browser_errors":browser_errors[:30],
            "dom_sample":dom_text[:7000],
        }
        (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print("=== DIAGNOSTIC SUMMARY ===")
        print(json.dumps({k:v for k,v in report.items() if k not in
                          ("responses","dom_sample")},ensure_ascii=False,indent=2))
        print("=== NETWORK RESPONSES ===")
        for r in responses:
            print(json.dumps({k:v for k,v in r.items() if k!="body_sample"},
                             ensure_ascii=False))
        print("=== DOM TEXT (START) ===")
        print(dom_text[:3500])
        print("=== OCR TEXT (START) ===")
        print(image_text[:3500])
        await browser.close()

asyncio.run(main())
