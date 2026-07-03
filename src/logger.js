import fs from "fs";
import path from "path";
import { getConfig, resolvePath } from "./config.js";

const LEVELS = { DEBUG: 0, INFO: 1, WARN: 2, ERROR: 3 };

let logFile = null;

function initLogFile() {
  try {
    const config = getConfig();
    const filePath = resolvePath(config.logging.file);
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    logFile = filePath;
  } catch {
    logFile = null;
  }
}

function write(entry) {
  const line = JSON.stringify(entry);
  if (getConfig().logging.format === "json") {
    console.log(line);
  } else {
    console.log(`[${entry.level}] ${entry.event}: ${entry.message || ""}`);
  }
  if (logFile) {
    fs.appendFileSync(logFile, line + "\n");
  }
}

export function log(level, event, message = "", extra = {}) {
  const config = getConfig();
  const minLevel = LEVELS[config.logging.level?.toUpperCase()] ?? LEVELS.INFO;
  if (LEVELS[level] < minLevel) return;
  write({
    ts: new Date().toISOString(),
    level,
    event,
    message,
    ...extra,
  });
}

export function initLogging() {
  initLogFile();
}
