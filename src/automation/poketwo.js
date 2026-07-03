import { waitUntilCloudflareClear } from "./cloudflare.js";
import { addLog, updateProgress, JobStatus } from "../jobs/models.js";
import { log } from "../logger.js";

const CAPTCHA_SOLVED_JS = `() => {
  const turnstile = document.querySelector('input[name="cf-turnstile-response"]')?.value || '';
  if (turnstile.length > 10) return true;
  for (const el of document.querySelectorAll('[name="h-captcha-response"], textarea')) {
    if (el.value && el.value.length > 10) return true;
  }
  return false;
}`;

const SUCCESS_JS = `() => {
  const body = (document.body?.innerText || '').toLowerCase();
  if (body.includes('thanks for verifying')) return true;
  if (body.includes('you can now close this page')) return true;
  if (/\\bsuccess!\\b/.test(body)) return true;
  return false;
}`;

const FIND_VERIFY_JS = `() => {
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
}`;

export class PoketwoAutomation {
  constructor(config) {
    this.config = config;
    this.poketwo = config.automation.poketwo;
  }

  async execute(job, session, onProgress) {
    const screenshots = [];
    const page = session.page;
    const nopechaKey = this.poketwo.captcha.nopechaApiKey;

    const progress = async (step, pct, msg = "") => {
      updateProgress(job, step, pct, msg);
      addLog(job, step, msg || step);
      if (onProgress) await onProgress(job);
    };

    const shot = async (name) => {
      try {
        screenshots.push(await session.screenshot(name));
      } catch (e) {
        addLog(job, "screenshot", `${name} skipped: ${e}`, "warning");
      }
    };

    try {
      const extNames = Object.keys(session.extensionIds).join(", ");
      if (!extNames) {
        addLog(job, "extensions", "No extensions loaded", "error");
        return false;
      }
      addLog(job, "extensions", `Ready: ${extNames}`);

      if (!nopechaKey) {
        addLog(job, "nopecha", "NOPECHA_API_KEY missing in .env", "error");
        return false;
      }

      await progress("navigate", 10, `Opening ${job.url}`);
      await page.goto(job.url, { waitUntil: "domcontentloaded", timeout: 120000 });

      await progress("cloudflare", 20, "Passing Cloudflare");
      if (!(await waitUntilCloudflareClear(page, job, this.config))) {
        await shot("00_cf_stuck");
        return false;
      }
      await shot("01_cf_clear");

      job.status = JobStatus.WAITING_CAPTCHA;
      await progress("captcha", 35, "Waiting for NopeCHA");
      if (!(await this._waitCaptchaAndVerify(page, job))) {
        await shot("02_captcha_timeout");
        return false;
      }
      await shot("02_captcha_done");

      job.status = JobStatus.WAITING_DISCORD;
      await progress("discord", 60, "Discord OAuth");
      if (!(await this._waitDiscord(page))) {
        await shot("03_no_discord");
        return false;
      }

      await progress("login", 70, "Discord token login");
      if (!(await this._tokenLogin(page, job.discordToken))) {
        await shot("04_login_fail");
        return false;
      }
      await shot("04_logged_in");

      job.status = JobStatus.WAITING_AUTHORIZE;
      await progress("authorize", 80, "Authorize bot");
      await page.waitForTimeout(2000);
      await this._clickAuthorize(page);
      await shot("05_authorized");

      job.status = JobStatus.VERIFYING;
      await progress("done", 90, "Checking verified");
      const verified = await this._checkVerified(page, job.url, job);
      await shot("06_final");

      if (verified) {
        await progress("complete", 100, "Verified");
        job.result.verified = true;
        job.result.finalUrl = page.url();
        job.result.screenshots = screenshots;
        return true;
      }
      return false;
    } catch (e) {
      addLog(job, "error", String(e), "error");
      log("ERROR", "poketwo_error", String(e), { jobId: job.id });
      return false;
    } finally {
      job.result.screenshots = screenshots;
    }
  }

  async _waitCaptchaAndVerify(page, job) {
    const cfg = this.poketwo.captcha;
    const oauth = this.poketwo.discord.oauthUrlPattern;
    let announced = false;

    for (let elapsed = 0; elapsed < cfg.maxWaitSeconds; elapsed += cfg.pollIntervalSeconds) {
      const url = page.url();
      if (oauth && url.includes(oauth)) {
        addLog(job, "verify", "Left captcha page — proceeding");
        return true;
      }
      if (url && !url.includes("poketwo.net/captcha")) {
        addLog(job, "verify", "Left captcha page — proceeding");
        return true;
      }

      if (await page.evaluate(CAPTCHA_SOLVED_JS)) {
        if (!announced) {
          addLog(job, "captcha", "Captcha solved — clicking Verify");
          announced = true;
        }
        if (await this._clickVerifyAndWait(page, job, oauth)) return true;
      }

      if (elapsed && elapsed % 15 === 0) {
        addLog(job, "captcha", `Waiting for NopeCHA... (${elapsed}s)`);
      }
      await page.waitForTimeout(cfg.pollIntervalSeconds * 1000);
    }
    return false;
  }

  async _clickVerifyAndWait(page, job, oauth) {
    const target = await page.evaluate(FIND_VERIFY_JS);
    let clicked = false;
    if (target) {
      try {
        await page.mouse.click(target.x, target.y);
        addLog(job, "verify", `Verify clicked at (${Math.round(target.x)},${Math.round(target.y)})`);
        clicked = true;
      } catch (e) {
        addLog(job, "verify", `Mouse click failed: ${e}`, "warning");
      }
    }
    if (!clicked) {
      for (const sel of this.poketwo.verifyButton.selectors) {
        try {
          const loc = page.locator(sel).first();
          if ((await loc.count()) > 0) {
            await loc.click();
            clicked = true;
            addLog(job, "verify", "Verify clicked (fallback)");
            break;
          }
        } catch {
          // continue
        }
      }
    }
    if (!clicked) return false;

    for (let i = 0; i < 16; i++) {
      await page.waitForTimeout(500);
      const url = page.url();
      if (oauth && url.includes(oauth)) {
        addLog(job, "verify", "Redirected to Discord");
        return true;
      }
      if (url && !url.includes("poketwo.net/captcha")) return true;
    }
    return false;
  }

  async _waitDiscord(page, timeout = 90) {
    const pat = this.poketwo.discord.oauthUrlPattern;
    for (let i = 0; i < timeout * 2; i++) {
      try {
        if (page.url().includes(pat)) return true;
      } catch {
        // continue
      }
      await page.waitForTimeout(500);
    }
    return false;
  }

  async _tokenLogin(page, token) {
    const wait = this.poketwo.discord.tokenLogin.waitAfterLoginSeconds;
    try {
      await page.evaluate((t) => {
        setInterval(() => {
          try {
            const f = document.createElement("iframe");
            document.body.appendChild(f);
            f.contentWindow.localStorage.setItem("token", JSON.stringify(t));
          } catch (e) {
            // ignore
          }
        }, 50);
        setTimeout(() => location.reload(), 2500);
      }, token);
      await page.waitForTimeout((2.5 + wait) * 1000);
      const u = page.url().toLowerCase();
      return u.includes("discord.com") && !u.includes("login");
    } catch (e) {
      log("WARN", "token_login_failed", String(e));
      return false;
    }
  }

  async _clickAuthorize(page) {
    for (const sel of this.poketwo.discord.authorizeButton.selectors) {
      try {
        const loc = page.locator(sel).first();
        if ((await loc.count()) > 0) {
          await loc.click();
          return true;
        }
      } catch {
        // continue
      }
    }
    try {
      await page.getByText("Authorize", { exact: false }).first().click({ timeout: 15000 });
      return true;
    } catch {
      return false;
    }
  }

  async _checkVerified(page, url, job) {
    const patterns = this.poketwo.success.textPatterns.map((p) => p.toLowerCase());
    const waits = Math.floor(this.poketwo.success.maxWaitSeconds / 2);

    for (let i = 0; i < waits; i++) {
      try {
        if (await page.evaluate(SUCCESS_JS)) {
          addLog(job, "success", "Poketwo success screen detected");
          return true;
        }
        const body = ((await page.innerText("body")) || "").toLowerCase();
        if (patterns.some((p) => body.includes(p))) {
          addLog(job, "success", "Poketwo success text matched");
          return true;
        }
      } catch {
        // continue
      }

      const cur = page.url();
      if (!cur.includes("verify.poketwo.net")) {
        try {
          await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
          await page.waitForTimeout(2000);
        } catch {
          // continue
        }
      } else if (i && i % 5 === 0) {
        addLog(job, "success", `Waiting for success screen... (${i * 2}s)`);
      }
      await page.waitForTimeout(2000);
    }

    try {
      const snippet = ((await page.innerText("body")) || "").slice(0, 120).replace(/\n/g, " ");
      addLog(job, "success", `Success screen not found. Page: ${snippet}`, "warning");
    } catch {
      addLog(job, "success", "Success screen not found", "warning");
    }
    return false;
  }
}
