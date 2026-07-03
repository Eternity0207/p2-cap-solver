import { chromium } from "playwright";
import { v4 as uuidv4 } from "uuid";
import fs from "fs";
import path from "path";
import { getConfig, resolvePath } from "../config.js";
import { log } from "../logger.js";
import { detectPlatform, ensureDisplay } from "../platform.js";
import { extensionsToLoad, extensionIdsFor, findBrowserBinary } from "./extensions.js";
import { withProfileLock } from "./profile-lock.js";

const STEALTH_INIT_SCRIPT = `
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = window.chrome || { runtime: {} };
`;

const BLOCKED_ARGS = new Set([
  "--no-sandbox",
  "--disable-setuid-sandbox",
  "--enable-automation",
  "--remote-debugging-port",
]);

export class PlaywrightLauncher {
  constructor(config = getConfig()) {
    this.config = config;
    this.platform = detectPlatform();
  }

  _profileDir(sessionId) {
    const cfg = this.config.browser;
    if (cfg.systemProfilePath && fs.existsSync(cfg.systemProfilePath)) {
      return path.resolve(cfg.systemProfilePath);
    }
    if (cfg.sharedProfile) {
      return resolvePath(path.join(cfg.userDataBase, `shared_${cfg.sharedProfileId}`));
    }
    return resolvePath(path.join(cfg.userDataBase, "temp", sessionId));
  }

  async createSession({ sessionId, withExtensions } = {}) {
    if (!this.platform.hasDisplay && this.platform.xvfbAvailable) {
      ensureDisplay(this.config.platform.display);
    }

    const includeExt =
      withExtensions !== undefined ? withExtensions : this.config.browser.loadExtensionsAtStartup;

    const extensionPaths = await extensionsToLoad({ include: includeExt });
    const sid = sessionId || uuidv4();
    const profileDir = this._profileDir(sid);
    fs.mkdirSync(profileDir, { recursive: true });

    const binary = findBrowserBinary();
    const args = ["--disable-blink-features=AutomationControlled"];
    if (extensionPaths.length) {
      const joined = extensionPaths.join(",");
      args.push(`--disable-extensions-except=${joined}`, `--load-extension=${joined}`);
    }
    for (const arg of this.config.browser.args) {
      const base = arg.split("=")[0];
      if (!BLOCKED_ARGS.has(base)) args.push(arg);
      else log("WARN", "blocked_browser_arg", "", { arg });
    }

    const launchOpts = {
      headless: false,
      executablePath: binary || undefined,
      args,
      ignoreDefaultArgs: ["--enable-automation"],
      viewport: {
        width: this.config.browser.viewportWidth,
        height: this.config.browser.viewportHeight,
      },
    };

    log("INFO", "launching_playwright", "", {
      sessionId: sid,
      profile: profileDir,
      extensions: extensionPaths.map((p) => path.basename(p)),
      binary,
    });

    const context = await withProfileLock(profileDir, async () =>
      chromium.launchPersistentContext(profileDir, launchOpts)
    );

    await context.addInitScript(STEALTH_INIT_SCRIPT);
    const page = context.pages()[0] || (await context.newPage());
    const extensionIds = extensionIdsFor(extensionPaths);

    const nopechaKey = this.config.automation.poketwo.captcha.nopechaApiKey;
    if (nopechaKey && extensionIds.nopecha) {
      await this._configureNopecha(page, nopechaKey);
    }

    log("INFO", "session_ready", "", { extensions: Object.keys(extensionIds) });
    return { context, page, profileDir, sessionId: sid, extensionIds };
  }

  async _configureNopecha(page, apiKey) {
    try {
      await page.goto(`https://nopecha.com/setup?api_key=${apiKey}`, {
        waitUntil: "domcontentloaded",
        timeout: 60000,
      });
      await page.waitForTimeout(3000);
      log("INFO", "nopecha_api_key_configured");
    } catch (e) {
      log("WARN", "nopecha_setup_failed", String(e));
    }
  }

  async cleanupSession(sessionId, profileDir) {
    const cfg = this.config.browser;
    if (cfg.systemProfilePath || cfg.sharedProfile) return;
    for (const base of [
      resolvePath(path.join(cfg.userDataBase, "temp", sessionId)),
      resolvePath(path.join(cfg.userDataBase, sessionId)),
      profileDir,
    ]) {
      if (base && fs.existsSync(base)) {
        fs.rmSync(base, { recursive: true, force: true });
        log("INFO", "temp_profile_deleted", "", { sessionId, path: base });
      }
    }
  }
}

export class BrowserSession {
  constructor({ launcher, sessionId, context, page, profileDir, extensionIds, artifactsDir }) {
    this.launcher = launcher;
    this.sessionId = sessionId;
    this.context = context;
    this.page = page;
    this.profileDir = profileDir;
    this.extensionIds = extensionIds;
    this.artifactsDir = artifactsDir;
    this._closed = false;
    fs.mkdirSync(artifactsDir, { recursive: true });
  }

  async screenshot(name) {
    const filePath = path.join(this.artifactsDir, `${name}.png`);
    try {
      await this.page.screenshot({ path: filePath, fullPage: true });
      log("INFO", "screenshot_captured", "", { sessionId: this.sessionId, path: filePath });
    } catch (e) {
      log("WARN", "screenshot_skipped", String(e), { sessionId: this.sessionId });
    }
    return filePath;
  }

  async close(cleanupProfile = true) {
    if (this._closed) return;
    this._closed = true;
    try {
      await this.context.close();
    } catch (e) {
      log("WARN", "browser_stop_error", String(e), { sessionId: this.sessionId });
    }
    if (cleanupProfile) {
      await this.launcher.cleanupSession(this.sessionId, this.profileDir);
    }
    log("INFO", "session_closed", "", { sessionId: this.sessionId });
  }
}

export class BrowserPool {
  constructor(config = getConfig()) {
    this.config = config;
    this.launcher = new PlaywrightLauncher(config);
    this.maxConcurrent = config.browser.maxConcurrent;
    this._active = new Map();
    this._queue = [];
    this._running = 0;
  }

  get activeCount() {
    return this._active.size;
  }

  async acquire(jobId) {
    await new Promise((resolve) => {
      const tryAcquire = () => {
        if (this._running < this.maxConcurrent) {
          this._running++;
          resolve();
        } else {
          this._queue.push(tryAcquire);
        }
      };
      tryAcquire();
    });

    const artifactsDir = path.join(resolvePath(this.config.jobs.artifactsDir), jobId);
    const suffix = uuidv4().slice(0, 8);
    const { context, page, profileDir, sessionId, extensionIds } =
      await this.launcher.createSession({
        sessionId: `${jobId}_${suffix}`,
        withExtensions: this.config.browser.loadExtensionsAtStartup,
      });

    const session = new BrowserSession({
      launcher: this.launcher,
      sessionId,
      context,
      page,
      profileDir,
      extensionIds,
      artifactsDir,
    });
    this._active.set(sessionId, session);
    log("INFO", "session_acquired", "", { jobId, sessionId, active: this.activeCount });
    return session;
  }

  async release(session, cleanupProfile = true) {
    const sessionId = session.sessionId;
    await session.close(cleanupProfile);
    this._active.delete(sessionId);
    this._running--;
    if (this._queue.length) {
      const next = this._queue.shift();
      next();
    }
    log("INFO", "session_released", "", { sessionId, active: this.activeCount });
  }

  async shutdown() {
    for (const session of [...this._active.values()]) {
      await this.release(session);
    }
  }
}
