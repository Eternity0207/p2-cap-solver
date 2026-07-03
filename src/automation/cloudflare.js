import { addLog } from "../jobs/models.js";

const CF_MARKERS = [
  "performing security verification",
  "verifying you are human",
  "just a moment",
  "checking your browser",
  "security service to protect",
  "this may take a few seconds",
  "ray id:",
];

async function pageBodyText(page) {
  try {
    return ((await page.innerText("body")) || "").toLowerCase();
  } catch {
    return "";
  }
}

export async function isPastCloudflare(page) {
  const text = await pageBodyText(page);
  if (!text) return false;
  if (CF_MARKERS.some((m) => text.includes(m))) return false;
  if (
    ["please verify", "i am human", "hcaptcha", "complete the captcha"].some((k) =>
      text.includes(k)
    )
  ) {
    return true;
  }
  const count = await page
    .locator('[data-hcaptcha-widget-id], iframe[src*="hcaptcha.com"]')
    .count();
  return count > 0;
}

export async function waitUntilCloudflareClear(page, job, config) {
  const maxWait = config.automation.poketwo.cloudflare.maxWaitSeconds;
  let elapsed = 0;
  addLog(job, "cloudflare", "Waiting for Poketwo page");

  while (elapsed < maxWait) {
    if (await isPastCloudflare(page)) {
      addLog(job, "cloudflare", "Poketwo verify page loaded");
      return true;
    }
    if (elapsed > 0 && elapsed % 30 === 0) {
      addLog(job, "cloudflare", `Still waiting (${elapsed}s)`);
    }
    await page.waitForTimeout(2000);
    elapsed += 2;
  }

  addLog(job, "cloudflare", `Timed out after ${maxWait}s`, "error");
  return false;
}
