"""Poketwo verification — extensions, NopeCHA key, captcha, Discord OAuth."""

from __future__ import annotations

import asyncio
from typing import Awaitable, Callable

from capsolver.automation.base import AutomationExecutor
from capsolver.automation.cloudflare import CloudflareBypass
from capsolver.browser.nopecha_setup import read_nopecha_key
from capsolver.browser.page_adapter import AutomationTimeout, PageAdapter
from capsolver.browser.session import BrowserSession
from capsolver.core.config import AppConfig, PoketwoConfig, get_config
from capsolver.core.logging import get_logger
from capsolver.jobs.models import Job, JobStatus

logger = get_logger(__name__)

ProgressCallback = Callable[[str, int, str], Awaitable[None]]

_CAPTCHA_SOLVED_JS = """() => {
    const turnstile = document.querySelector('input[name="cf-turnstile-response"]')?.value || '';
    if (turnstile.length > 10) return true;
    for (const el of document.querySelectorAll('[name="h-captcha-response"], textarea')) {
        if (el.value && el.value.length > 10) return true;
    }
    return false;
}"""

_FIND_VERIFY_JS = """() => {
    const nodes = document.querySelectorAll('button, input[type="submit"], input[type="button"], a');
    for (const el of nodes) {
        const label = (el.innerText || el.textContent || el.value || '').replace(/\\s+/g, ' ').trim();
        if (!/\\bverify\\b/i.test(label)) continue;
        const style = window.getComputedStyle(el);
        if (style.display === 'none' || style.visibility === 'hidden') continue;
        if (el.disabled || el.getAttribute('aria-disabled') === 'true') continue;
        const r = el.getBoundingClientRect();
        if (r.width < 2 || r.height < 2) continue;
        return { x: r.x + r.width / 2, y: r.y + r.height / 2, tag: el.tagName };
    }
    return null;
}"""


class PoketwoAutomation(AutomationExecutor):
    def __init__(self, config: AppConfig | None = None):
        self.config = config or get_config()
        self.poketwo: PoketwoConfig = self.config.automation.poketwo

    async def execute(
        self,
        job: Job,
        session: BrowserSession,
        on_progress: ProgressCallback | None = None,
    ) -> bool:
        screenshots: list[str] = []
        page = await session.get_or_create_page()
        nopecha_key = read_nopecha_key(self.poketwo.captcha.nopecha_api_key)

        async def progress(step: str, pct: int, msg: str = "") -> None:
            job.update_progress(step, pct, msg)
            job.add_log(step, msg or step)
            if on_progress:
                await on_progress(step, pct, msg)

        async def shot(name: str) -> None:
            try:
                screenshots.append(await session.screenshot(name))
            except Exception as e:
                job.add_log("screenshot", f"{name} skipped: {e}", level="warning")

        try:
            ext_names = ", ".join(session.extension_ids.keys())
            if not ext_names:
                job.add_log("extensions", "No extensions loaded", level="error")
                return False
            job.add_log("extensions", f"Ready: {ext_names}")

            if not nopecha_key:
                job.add_log("nopecha", "NOPECHA_API_KEY missing in .env", level="error")
                return False

            await progress("navigate", 10, f"Opening {job.url}")
            await page.goto(job.url, wait_until="domcontentloaded", timeout=120000)

            await progress("cloudflare", 20, "Passing Cloudflare")
            if not await CloudflareBypass(self.poketwo.cloudflare).wait_until_clear(page, job):
                await shot("00_cf_stuck")
                return False
            await shot("01_cf_clear")

            job.status = JobStatus.WAITING_CAPTCHA
            await progress("captcha", 35, "Waiting for NopeCHA")
            if not await self._wait_captcha_and_verify(page, job):
                await shot("02_captcha_timeout")
                return False
            await shot("02_captcha_done")

            job.status = JobStatus.WAITING_DISCORD
            await progress("discord", 60, "Discord OAuth")
            if not await self._wait_discord(page):
                await shot("03_no_discord")
                return False

            await progress("login", 70, "Discord token login")
            if not await self._token_login(page, job.discord_token):
                await shot("04_login_fail")
                return False
            await shot("04_logged_in")

            job.status = JobStatus.WAITING_AUTHORIZE
            await progress("authorize", 80, "Authorize bot")
            await asyncio.sleep(2)
            await self._click_authorize(page)
            await shot("05_authorized")

            job.status = JobStatus.VERIFYING
            await progress("done", 90, "Checking verified")
            verified = await self._check_verified(page, job.url)
            await shot("06_final")

            if verified:
                await progress("complete", 100, "Verified")
                if job.result:
                    job.result.verified = True
                    job.result.final_url = await page.current_url()
                    job.result.screenshots = screenshots
                return True
            return False

        except AutomationTimeout as e:
            job.add_log("error", str(e), level="error")
            return False
        except Exception as e:
            job.add_log("error", str(e), level="error")
            logger.exception("poketwo_error", job_id=job.id)
            return False
        finally:
            if job.result:
                job.result.screenshots = screenshots

    async def _wait_captcha_and_verify(self, page: PageAdapter, job: Job) -> bool:
        cfg = self.poketwo.captcha
        oauth = self.poketwo.discord.oauth_url_pattern
        announced = False

        for elapsed in range(0, cfg.max_wait_seconds, cfg.poll_interval_seconds):
            url = await page.current_url()
            if oauth in url or (url and "poketwo.net/captcha" not in url):
                job.add_log("verify", "Left captcha page — proceeding")
                return True

            if bool(await page.safe_evaluate(_CAPTCHA_SOLVED_JS)):
                if not announced:
                    job.add_log("captcha", "Captcha solved — clicking Verify")
                    announced = True
                if await self._click_verify_and_wait(page, job, oauth):
                    return True

            if elapsed and elapsed % 15 == 0:
                job.add_log("captcha", f"Waiting for NopeCHA... ({elapsed}s)")
            await asyncio.sleep(cfg.poll_interval_seconds)

        return False

    async def _click_verify_and_wait(self, page: PageAdapter, job: Job, oauth: str) -> bool:
        target = await page.safe_evaluate(_FIND_VERIFY_JS)
        clicked = False
        if target:
            try:
                await page._tab.mouse_click(float(target["x"]), float(target["y"]))
                job.add_log("verify", f"Verify clicked at ({int(target['x'])},{int(target['y'])})")
                clicked = True
            except Exception as e:
                job.add_log("verify", f"Mouse click failed: {e}", level="warning")
        if not clicked:
            clicked = await page.click_verify()
            if clicked:
                job.add_log("verify", "Verify clicked (fallback)")
        if not clicked:
            return False

        for _ in range(16):
            await asyncio.sleep(0.5)
            url = await page.current_url()
            if oauth in url:
                job.add_log("verify", "Redirected to Discord")
                return True
            if url and "poketwo.net/captcha" not in url:
                return True
        return False

    async def _wait_discord(self, page: PageAdapter, timeout: int = 90) -> bool:
        pat = self.poketwo.discord.oauth_url_pattern
        for _ in range(timeout * 2):
            try:
                if pat in await page.current_url():
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
        return False

    async def _token_login(self, page: PageAdapter, token: str) -> bool:
        wait = self.poketwo.discord.token_login.wait_after_login_seconds
        try:
            # Repeatedly write the token to localStorage (Discord clears it once),
            # then reload so the client picks it up and follows redirect_to.
            await page.safe_evaluate(
                """(t) => {
                    setInterval(() => {
                        try {
                            const f = document.createElement('iframe');
                            document.body.appendChild(f);
                            f.contentWindow.localStorage.setItem('token', JSON.stringify(t));
                        } catch (e) {}
                    }, 50);
                    setTimeout(() => location.reload(), 2500);
                }""",
                token,
            )
            await asyncio.sleep(2.5 + wait)
            u = (await page.current_url()).lower()
            return "discord.com" in u and "login" not in u
        except Exception as e:
            logger.warning("token_login_failed", error=str(e))
            return False

    async def _click_authorize(self, page: PageAdapter) -> bool:
        for sel in self.poketwo.discord.authorize_button.selectors:
            try:
                if await page.locator(sel).count() > 0:
                    await page.locator(sel).click()
                    return True
            except Exception:
                pass
        return await page.click_by_text("Authorize", timeout=15)

    async def _check_verified(self, page: PageAdapter, url: str) -> bool:
        patterns = [p.lower() for p in self.poketwo.success.text_patterns]
        for _ in range(self.poketwo.success.max_wait_seconds // 2):
            cur = await page.current_url()
            if "poketwo" not in cur:
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                except Exception:
                    pass
            try:
                body = (await page.inner_text("body")).lower()
                if any(p in body for p in patterns):
                    return True
            except Exception:
                pass
            await asyncio.sleep(2)
        return False
