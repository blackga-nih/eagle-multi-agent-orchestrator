#!/usr/bin/env python3
"""Debug login page - take screenshot to see what's happening."""
import asyncio
import sys

async def main():
    from playwright.async_api import async_playwright

    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://internal-eaglec-front-teerfwosqs71-1457581412.us-east-1.elb.amazonaws.com"
    email = sys.argv[2] if len(sys.argv) > 2 else "blackga@nih.gov"
    password = sys.argv[3] if len(sys.argv) > 3 else "Eagle2026!"

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=True)
    context = await browser.new_context(viewport={"width": 1280, "height": 720})
    page = await context.new_page()

    print(f"1. Navigating to {base_url}...")
    await page.goto(base_url, wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)
    print(f"   URL after load: {page.url}")
    await page.screenshot(path="/tmp/debug_01_initial.png")

    if "/login" in page.url:
        print(f"2. On login page. Filling credentials...")

        # Check what selectors exist
        email_el = await page.query_selector("#email")
        pass_el = await page.query_selector("#password")
        submit_el = await page.query_selector("button[type='submit']")
        print(f"   #email exists: {email_el is not None}")
        print(f"   #password exists: {pass_el is not None}")
        print(f"   submit button exists: {submit_el is not None}")

        if email_el and pass_el:
            await page.fill("#email", email)
            await page.fill("#password", password)
            await page.screenshot(path="/tmp/debug_02_filled.png")

            if submit_el:
                await submit_el.click()
                print("3. Clicked submit, waiting...")
                await page.wait_for_timeout(5000)
                print(f"   URL after submit: {page.url}")
                await page.screenshot(path="/tmp/debug_03_after_submit.png")

                # Check for error messages
                error_el = await page.query_selector(".text-red-500, .error, [role='alert']")
                if error_el:
                    error_text = await error_el.text_content()
                    print(f"   ERROR on page: {error_text}")

                await page.wait_for_timeout(5000)
                print(f"   URL after 10s: {page.url}")
                await page.screenshot(path="/tmp/debug_04_final.png")
        else:
            # Try alternate selectors
            inputs = await page.query_selector_all("input")
            print(f"   Found {len(inputs)} input elements")
            for i, inp in enumerate(inputs):
                inp_type = await inp.get_attribute("type")
                inp_id = await inp.get_attribute("id")
                inp_name = await inp.get_attribute("name")
                print(f"   input[{i}]: type={inp_type} id={inp_id} name={inp_name}")
    else:
        print(f"2. Not on login page, already at: {page.url}")

    await browser.close()
    await pw.stop()
    print("Done.")

asyncio.run(main())
