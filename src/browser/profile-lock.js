import fs from "fs";
import path from "path";
import lockfile from "proper-lockfile";
import { log } from "../logger.js";

const LOCK_FILES = ["SingletonLock", "SingletonSocket", "LOCK", "lockfile"];

export function cleanStaleLocks(profileDir) {
  if (!fs.existsSync(profileDir)) return;
  for (const name of LOCK_FILES) {
    const filePath = path.join(profileDir, name);
    if (fs.existsSync(filePath)) {
      try {
        fs.unlinkSync(filePath);
        log("INFO", "profile_lock_removed", "", { file: name, profile: profileDir });
      } catch (e) {
        log("WARN", "profile_lock_remove_failed", String(e), { file: name });
      }
    }
  }
}

export async function withProfileLock(profileDir, fn) {
  fs.mkdirSync(profileDir, { recursive: true });
  const lockPath = path.join(profileDir, ".capsolver.lock");
  if (!fs.existsSync(lockPath)) fs.writeFileSync(lockPath, "");
  const release = await lockfile.lock(lockPath, { retries: { retries: 10, minTimeout: 500 } });
  try {
    cleanStaleLocks(profileDir);
    return await fn();
  } finally {
    await release();
  }
}
