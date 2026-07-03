import fs from "fs";
import path from "path";
import yaml from "js-yaml";
import dotenv from "dotenv";

dotenv.config();

const VERSION = "1.0.0";

const defaults = {
  server: {
    host: "0.0.0.0",
    port: 8080,
    apiKey: "",
    corsOrigins: ["*"],
  },
  browser: {
    headless: false,
    maxConcurrent: 1,
    jobTimeoutSeconds: 300,
    navigationTimeoutMs: 60000,
    actionTimeoutMs: 30000,
    viewportWidth: 1280,
    viewportHeight: 720,
    args: [],
    extensions: {
      nopechaPath: "extensions/nopecha",
      discordTokenPath: "extensions/discord-token-login",
      loadNopecha: true,
    },
    userDataBase: "data/browser_profiles",
    executablePath: "",
    sharedProfile: true,
    sharedProfileId: "default",
    systemProfilePath: "",
    loadExtensionsAtStartup: true,
  },
  jobs: {
    maxRetries: 3,
    retryDelaySeconds: 5,
    cleanupAfterHours: 24,
    storePath: "data/jobs.db",
    artifactsDir: "data/artifacts",
  },
  automation: {
    poketwo: {
      verifyUrlPattern: "verify.poketwo.net/captcha/",
      captcha: {
        mode: "auto",
        nopechaApiKey: "",
        solvedSelector: 'input[name="cf-turnstile-response"]',
        solvedAttribute: "value",
        maxWaitSeconds: 120,
        pollIntervalSeconds: 2,
      },
      cloudflare: {
        maxWaitSeconds: 240,
        cfClearanceRequired: true,
      },
      verifyButton: {
        text: "Verify",
        selectors: [
          'button:has-text("Verify")',
          'input[type="submit"][value*="Verify"]',
          'a:has-text("Verify")',
        ],
      },
      discord: {
        oauthUrlPattern: "discord.com/oauth2",
        authorizeButton: {
          text: "Authorize",
          selectors: [
            'button:has-text("Authorize")',
            'span:has-text("Authorize")',
          ],
        },
        tokenLogin: {
          waitAfterLoginSeconds: 5,
        },
      },
      success: {
        textPatterns: [
          "thanks for verifying",
          "you can now close this page",
          "success!",
        ],
        maxWaitSeconds: 90,
      },
    },
  },
  logging: {
    level: "INFO",
    format: "json",
    file: "data/logs/cap-solver.log",
  },
  platform: {
    display: ":99",
  },
};

function deepMerge(base, override) {
  const result = { ...base };
  for (const [key, value] of Object.entries(override || {})) {
    if (
      key in result &&
      typeof result[key] === "object" &&
      result[key] !== null &&
      !Array.isArray(result[key]) &&
      typeof value === "object" &&
      value !== null &&
      !Array.isArray(value)
    ) {
      result[key] = deepMerge(result[key], value);
    } else {
      result[key] = value;
    }
  }
  return result;
}

function snakeToCamel(str) {
  return str.replace(/_([a-z])/g, (_, c) => c.toUpperCase());
}

function camelizeKeys(obj) {
  if (Array.isArray(obj)) return obj.map(camelizeKeys);
  if (obj && typeof obj === "object") {
    return Object.fromEntries(
      Object.entries(obj).map(([k, v]) => [snakeToCamel(k), camelizeKeys(v)])
    );
  }
  return obj;
}

function loadYaml(filePath) {
  if (!fs.existsSync(filePath)) return {};
  return yaml.load(fs.readFileSync(filePath, "utf8")) || {};
}

let _config = null;

export function getVersion() {
  return VERSION;
}

export function getBaseDir() {
  return path.resolve(process.env.CAPSOLVER_BASE_DIR || ".");
}

export function resolvePath(relative) {
  return path.resolve(getBaseDir(), relative);
}

export function loadConfig() {
  const baseDir = getBaseDir();
  const configPath = process.env.CAPSOLVER_CONFIG_PATH || "config/default.yaml";
  const localPath = process.env.CAPSOLVER_LOCAL_CONFIG_PATH || "config/local.yaml";

  let data = deepMerge(defaults, camelizeKeys(loadYaml(path.join(baseDir, configPath))));
  data = deepMerge(data, camelizeKeys(loadYaml(path.join(baseDir, localPath))));

  const nopechaKey = (process.env.NOPECHA_API_KEY || "").trim();
  if (nopechaKey) {
    data.automation.poketwo.captcha.nopechaApiKey = nopechaKey;
  }

  const apiKey =
    process.env.CAPSOLVER_API_KEY ||
    process.env.CAPSOLVER_SERVER__API_KEY ||
    data.server.apiKey;
  if (apiKey) data.server.apiKey = apiKey;

  _config = data;
  return data;
}

export function getConfig() {
  if (!_config) return loadConfig();
  return _config;
}

export function ensureDataDirs(config) {
  const dirs = [
    resolvePath(config.jobs.artifactsDir),
    path.dirname(resolvePath(config.jobs.storePath)),
    path.dirname(resolvePath(config.logging.file)),
    resolvePath(config.browser.userDataBase),
  ];
  for (const dir of dirs) {
    fs.mkdirSync(dir, { recursive: true });
  }
}
