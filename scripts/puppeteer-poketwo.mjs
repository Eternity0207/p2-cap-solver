#!/usr/bin/env node
/**
 * Full Poketwo verification via puppeteer-extra + stealth plugin.
 * Uses Puppeteer's bundled Chromium (not Brave).
 *
 * Input: JSON on argv[2] { url, discordToken, nopechaApiKey, artifactsDir, profileDir }
 * Output: JSON on stdout { success, logs, screenshots, error }
 */

import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";
import puppeteer from "puppeteer-extra";
import StealthPlugin from "puppeteer-extra-plugin-stealth";

puppeteer.use(StealthPlugin());

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, "..");
const NOPECHA_EXT = path.join(ROOT, "extensions/nopecha");
const DISCORD_EXT = path.join(ROOT, "extensions/discord-token-login");
const DISCORD_EXT_ID = "pdmpkpjlmnndlfdllmnekbmgjikhghjg";

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function log(logs, step, message, level = "info") {
  logs.push({ step, message, level, t: Date.now() });
  console.error(`[${level}] ${step}: ${message}`);
}

async function screenshot(page, dir, name, shots) {
  const p = path.join(dir, `${name}.png`);
  await page.screenshot({ path: p, fullPage: true });
  shots.push(p);
  return p;
}

async function turnstileSolved(page) {
  return page.evaluate(() => {
    const el = document.querySelector('input[name="cf-turnstile-response"]');
    return !!(el && el.value && el.value.length > 10);
  });
}

async function waitCaptcha(page, logs, maxSec = 180) {
  for (let i = 0; i < maxSec; i += 2) {
    if (await turnstileSolved(page)) {
      log(logs, "captcha", "NopeCHA solved Turnstile");
      return true;
    }
    if (i > 0 && i % 15 === 0) log(logs, "captcha", `Waiting for NopeCHA... (${i}s)`);
    await sleep(2000);
  }
  return false;
}

async function clickText(page, text, timeout = 15000) {
  const btn = await page.waitForFunction(
    (t) => {
      const nodes = [...document.querySelectorAll("button, input[type=submit], a")];
      return nodes.find((n) => n.innerText?.includes(t) || n.value?.includes(t));
    },
    { timeout },
    text
  );
  const el = await btn.asElement();
  if (el) await el.click();
  return !!el;
}

async function discordExtensionLogin(browser, discordPage, token, logs) {
  const popup = await browser.newPage();
  try {
    await popup.goto(`chrome-extension://${DISCORD_EXT_ID}/popup/popup.html`, {
      waitUntil: "domcontentloaded",
      timeout: 30000,
    });
    const result = await popup.evaluate(async (t) => {
      await chrome.storage.sync.set({ token: t });
      const tabs = await chrome.tabs.query({ url: ["https://discord.com/*", "https://*.discord.com/*"] });
      const tab = tabs.find((x) => x.url?.includes("oauth2")) || tabs[0];
      if (!tab) return { ok: false, reason: "no_discord_tab" };
      await chrome.scripting.executeScript({
        target: { tabId: tab.id },
        func: (tok) => {
          const iframe = document.createElement("iframe");
          document.body.appendChild(iframe);
          iframe.contentWindow.localStorage.setItem("token", `"${tok}"`);
          iframe.remove();
          location.reload();
        },
        args: [t],
      });
      return { ok: true, tabUrl: tab.url };
    }, token);
    log(logs, "discord_login", JSON.stringify(result));
    await popup.close();
    await sleep(5000);
    await discordPage.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 30000 }).catch(() => {});
    const url = discordPage.url().toLowerCase();
    return url.includes("discord.com") && (url.includes("oauth2") || !url.includes("login"));
  } catch (e) {
    log(logs, "discord_login", String(e), "error");
    try {
      await popup.close();
    } catch {}
    return false;
  }
}

async function checkVerified(page, originalUrl, logs, maxSec = 60) {
  const patterns = ["verified", "successfully verified"];
  for (let i = 0; i < maxSec; i += 2) {
    if (!page.url().includes("poketwo") && !page.url().includes("verify.poketwo")) {
      await page.goto(originalUrl, { waitUntil: "domcontentloaded", timeout: 30000 }).catch(() => {});
    }
    const text = (await page.evaluate(() => document.body?.innerText || "")).toLowerCase();
    if (patterns.some((p) => text.includes(p))) {
      log(logs, "verify_result", "Verified text found");
      return true;
    }
    await sleep(2000);
  }
  return false;
}

async function runJob(opts) {
  const { url, discordToken, nopechaApiKey, artifactsDir, profileDir } = opts;
  const logs = [];
  const screenshots = [];
  fs.mkdirSync(artifactsDir, { recursive: true });
  fs.mkdirSync(profileDir, { recursive: true });

  const extJoined = `${NOPECHA_EXT},${DISCORD_EXT}`;
  log(logs, "launch", `Puppeteer stealth + Chromium, profile=${profileDir}`);

  const executablePath = puppeteer.executablePath();
  const browser = await puppeteer.launch({
    headless: false,
    executablePath,
    userDataDir: profileDir,
    args: [
      `--disable-extensions-except=${extJoined}`,
      `--load-extension=${extJoined}`,
      "--disable-blink-features=AutomationControlled",
    ],
    ignoreDefaultArgs: ["--enable-automation"],
    defaultViewport: { width: 1280, height: 720 },
  });

  const pages = await browser.pages();
  const page = pages[0] || (await browser.newPage());

  try {
    if (nopechaApiKey) {
      log(logs, "nopecha", "Configuring API key in extension");
      await page.goto(`https://nopecha.com/setup?api_key=${nopechaApiKey}`, {
        waitUntil: "domcontentloaded",
        timeout: 60000,
      });
      await sleep(3000);
    }

    log(logs, "navigate", `Opening ${url}`);
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 120000 });
    await screenshot(page, artifactsDir, "01_poketwo_opened", screenshots);

    log(logs, "captcha", "Waiting for NopeCHA extension");
    if (!(await waitCaptcha(page, logs))) {
      await screenshot(page, artifactsDir, "02_captcha_timeout", screenshots);
      return { success: false, logs, screenshots, error: "captcha_timeout" };
    }
    await screenshot(page, artifactsDir, "02_captcha_solved", screenshots);

    log(logs, "verify_click", "Clicking Verify");
    if (!(await clickText(page, "Verify"))) {
      await screenshot(page, artifactsDir, "03_verify_not_found", screenshots);
      return { success: false, logs, screenshots, error: "verify_button_not_found" };
    }
    await screenshot(page, artifactsDir, "03_after_verify", screenshots);

    log(logs, "discord_redirect", "Waiting for Discord OAuth");
    await page.waitForFunction(() => location.href.includes("discord.com/oauth2"), { timeout: 60000 });
    await screenshot(page, artifactsDir, "04_discord_oauth", screenshots);

    log(logs, "discord_login", "Discord Token Login extension");
    if (!(await discordExtensionLogin(browser, page, discordToken, logs))) {
      await screenshot(page, artifactsDir, "05_login_failed", screenshots);
      return { success: false, logs, screenshots, error: "discord_login_failed" };
    }
    await screenshot(page, artifactsDir, "05_logged_in", screenshots);

    log(logs, "authorize", "Clicking Authorize");
    await sleep(2000);
    try {
      await clickText(page, "Authorize", 20000);
    } catch {
      log(logs, "authorize", "Authorize button not found — may auto-redirect", "warning");
    }
    await screenshot(page, artifactsDir, "06_after_authorize", screenshots);

    log(logs, "verify_result", "Checking verified on Poketwo");
    const verified = await checkVerified(page, url, logs);
    await screenshot(page, artifactsDir, "07_final", screenshots);

    if (verified) {
      log(logs, "complete", "Success — cleaning temp profile");
      await browser.close();
      fs.rmSync(profileDir, { recursive: true, force: true });
      return { success: true, logs, screenshots, error: null };
    }

    await browser.close();
    return { success: false, logs, screenshots, error: "not_verified" };
  } catch (e) {
    log(logs, "error", String(e), "error");
    try {
      await screenshot(page, artifactsDir, "error", screenshots);
    } catch {}
    await browser.close().catch(() => {});
    return { success: false, logs, screenshots, error: String(e) };
  }
}

const input = JSON.parse(process.argv[2] || "{}");
runJob(input)
  .then((r) => {
    process.stdout.write(JSON.stringify(r));
    process.exit(r.success ? 0 : 1);
  })
  .catch((e) => {
    process.stdout.write(JSON.stringify({ success: false, error: String(e), logs: [], screenshots: [] }));
    process.exit(1);
  });
