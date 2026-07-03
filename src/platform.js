import { execSync } from "child_process";
import fs from "fs";

export function detectPlatform() {
  const platform = process.platform;
  let distro = "";
  if (platform === "linux" && fs.existsSync("/etc/os-release")) {
    const content = fs.readFileSync("/etc/os-release", "utf8");
    const match = content.match(/^ID=(.+)$/m);
    if (match) distro = match[1].replace(/"/g, "");
  }

  const hasDisplay = Boolean(process.env.DISPLAY || process.env.WAYLAND_DISPLAY);
  let xvfbAvailable = false;
  if (platform === "linux") {
    try {
      execSync("which Xvfb", { stdio: "ignore" });
      xvfbAvailable = true;
    } catch {
      xvfbAvailable = false;
    }
  }

  return {
    os: platform,
    distro,
    arch: process.arch,
    hasDisplay,
    xvfbAvailable,
  };
}

export function ensureDisplay(display = ":99") {
  if (process.env.DISPLAY) return;
  if (process.platform !== "linux") return;

  try {
    execSync(`pgrep -f "Xvfb ${display}"`, { stdio: "ignore" });
    process.env.DISPLAY = display;
    return;
  } catch {
    // not running
  }

  try {
    execSync(`Xvfb ${display} -screen 0 1280x720x24 -ac +extension GLX +render -noreset`, {
      detached: true,
      stdio: "ignore",
    });
    process.env.DISPLAY = display;
  } catch {
    // Xvfb unavailable
  }
}
