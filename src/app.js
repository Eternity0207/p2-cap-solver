import express from "express";
import cors from "cors";
import http from "http";
import { getConfig, getVersion, loadConfig, ensureDataDirs } from "./config.js";
import { initLogging, log } from "./logger.js";
import { detectPlatform, ensureDisplay } from "./platform.js";
import { JobManager } from "./jobs/manager.js";
import { createRouter, setManager } from "./api/routes.js";
import { attachWebSockets } from "./api/websocket.js";

export async function createApp() {
  const config = loadConfig();
  initLogging();
  ensureDataDirs(config);

  const platform = detectPlatform();
  if (!platform.hasDisplay) {
    ensureDisplay(config.platform.display);
  }

  const manager = new JobManager({ config });
  await manager.start();
  setManager(manager);

  const app = express();
  app.use(cors({ origin: config.server.corsOrigins, credentials: true }));
  app.use(express.json());

  app.get("/", (req, res) => {
    res.json({
      name: "Cap-Solver",
      version: getVersion(),
      docs: "/docs",
      health: "/api/v1/health",
    });
  });

  app.use("/api/v1", createRouter());

  const server = http.createServer(app);
  attachWebSockets(server);

  server.manager = manager;

  log("INFO", "cap_solver_started", "", {
    version: getVersion(),
    platform: platform.os,
    maxConcurrent: config.browser.maxConcurrent,
  });

  return { app, server, manager };
}
