import AdmZip from "adm-zip";
import fs from "fs";
import path from "path";
import { execSync } from "child_process";
import { getConfig, resolvePath } from "../config.js";
import { log } from "../logger.js";

export const EXTENSION_IDS = {
  nopecha: "dknlfmjaanfblgfdfebhijalfmhmjjjo",
  "discord-token-login": "pdmpkpjlmnndlfdllmnekbmgjikhghjg",
};

const NOPECHA_ID = EXTENSION_IDS.nopecha;
const DISCORD_ID = EXTENSION_IDS["discord-token-login"];

const CRX_URL =
  "https://clients2.google.com/service/update2/crx" +
  "?response=redirect&acceptformat=crx2,crx3&prodversion=131.0" +
  "&x=id%3D{ext_id}%26installsource%3Dondemand%26uc";

function cacheDir(name) {
  return path.join(resolvePath(getConfig().browser.userDataBase), "..", "ext_cache", name);
}

function braveExtRoots() {
  const home = process.env.HOME || "";
  return [
    path.join(home, ".config/BraveSoftware/Brave-Browser/Default/Extensions"),
    path.join(home, ".config/google-chrome/Default/Extensions"),
    path.join(home, ".config/chromium/Default/Extensions"),
  ];
}

async function downloadCrx(extId, dest) {
  const url = CRX_URL.replace("{ext_id}", extId);
  try {
    const resp = await fetch(url, { redirect: "follow" });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = Buffer.from(await resp.arrayBuffer());
    const start = data.indexOf(Buffer.from("PK\x03\x04"));
    if (start < 0) {
      log("WARN", "crx_not_a_zip", "", { id: extId });
      return false;
    }

    fs.rmSync(dest, { recursive: true, force: true });
    fs.mkdirSync(dest, { recursive: true });

    const zip = new AdmZip(data.subarray(start));
    zip.extractAllTo(dest, true);

    const meta = path.join(dest, "_metadata");
    if (fs.existsSync(meta)) fs.rmSync(meta, { recursive: true, force: true });

    if (!fs.existsSync(path.join(dest, "manifest.json"))) {
      log("WARN", "crx_no_manifest", "", { id: extId });
      return false;
    }
    log("INFO", "crx_downloaded", "", { id: extId, path: dest });
    return true;
  } catch (e) {
    log("WARN", "crx_download_failed", String(e), { id: extId });
    return false;
  }
}

function copyFromBrowser(extId, dest) {
  for (const root of braveExtRoots()) {
    const base = path.join(root, extId);
    if (!fs.existsSync(base)) continue;
    const versions = fs
      .readdirSync(base, { withFileTypes: true })
      .filter((d) => d.isDirectory())
      .map((d) => path.join(base, d.name))
      .filter((p) => fs.existsSync(path.join(p, "manifest.json")));
    if (!versions.length) continue;
    const src = versions.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
    fs.rmSync(dest, { recursive: true, force: true });
    fs.cpSync(src, dest, { recursive: true });
    log("INFO", "extension_copied_from_browser", "", { id: extId, src, dest });
    return true;
  }
  return false;
}

async function resolveExt(extId, name) {
  const config = getConfig();
  const localNopecha = resolvePath(config.browser.extensions.nopechaPath);
  const localDiscord = resolvePath(config.browser.extensions.discordTokenPath);

  if (name === "nopecha" && fs.existsSync(path.join(localNopecha, "manifest.json"))) {
    return localNopecha;
  }
  if (name === "discord-token-login" && fs.existsSync(path.join(localDiscord, "manifest.json"))) {
    return localDiscord;
  }

  const dest = cacheDir(name);
  if (await downloadCrx(extId, dest)) return dest;
  log("INFO", "crx_fallback_to_browser", "", { id: extId });
  if (copyFromBrowser(extId, dest)) return dest;
  throw new Error(
    `Could not fetch ${name} (${extId}). Install extensions locally or check network.`
  );
}

export async function resolveNopecha() {
  return resolveExt(NOPECHA_ID, "nopecha");
}

export async function resolveDiscord() {
  return resolveExt(DISCORD_ID, "discord-token-login");
}

export async function extensionsToLoad({ include = true } = {}) {
  const config = getConfig();
  if (!include) return [];
  if (config.browser.systemProfilePath) return [];

  const paths = [];
  if (config.browser.extensions.loadNopecha) {
    paths.push(await resolveNopecha());
  }
  paths.push(await resolveDiscord());

  const resolved = paths.map((p) => path.resolve(p));
  log("INFO", "extensions_resolved", "", { paths: resolved });
  return resolved;
}

export function extensionIdsFor(paths) {
  const ids = {};
  for (const p of paths) {
    const parent = path.basename(path.dirname(p));
    if (EXTENSION_IDS[parent]) {
      ids[parent] = EXTENSION_IDS[parent];
      continue;
    }
    const name = path.basename(p);
    if (EXTENSION_IDS[name]) ids[name] = EXTENSION_IDS[name];
  }
  return ids;
}

export function findBrowserBinary() {
  const config = getConfig();
  if (config.browser.executablePath && fs.existsSync(config.browser.executablePath)) {
    return config.browser.executablePath;
  }
  for (const name of ["brave", "brave-browser", "google-chrome-stable", "google-chrome", "chromium"]) {
    try {
      return execSync(`which ${name}`, { encoding: "utf8" }).trim();
    } catch {
      // continue
    }
  }
  return null;
}
