import express from "express";
import fs from "fs";
import path from "path";
import { getConfig, getVersion, resolvePath } from "../config.js";
import { detectPlatform } from "../platform.js";
import { toPublicJob, JobType } from "../jobs/models.js";
import { waitForTerminal } from "../jobs/manager.js";

let _manager = null;

export function setManager(manager) {
  _manager = manager;
}

export function getManager() {
  if (!_manager) throw new Error("Service not initialized");
  return _manager;
}

function verifyApiKey(req, res, next) {
  const config = getConfig();
  if (!config.server.apiKey) return next();
  const key = req.headers["x-api-key"];
  if (key !== config.server.apiKey) {
    return res.status(401).json({ detail: "Invalid or missing API key" });
  }
  next();
}

function jobToVerifyResponse(job) {
  const result = job.result || {};
  return {
    jobId: job.id,
    status: job.status,
    success: Boolean(result.success),
    verified: Boolean(result.verified),
    finalUrl: result.finalUrl || null,
    error: result.error || null,
    attempts: result.attempts || job.attempt,
    durationSeconds: result.durationSeconds || 0,
  };
}

export function createRouter() {
  const router = express.Router();

  router.get("/health", (req, res) => {
    const platform = detectPlatform();
    res.json({
      status: "healthy",
      version: getVersion(),
      platform: {
        os: platform.os,
        distro: platform.distro,
        arch: platform.arch,
        hasDisplay: platform.hasDisplay,
        xvfbAvailable: platform.xvfbAvailable,
      },
    });
  });

  router.get("/stats", verifyApiKey, async (req, res) => {
    const stats = await getManager().getStats();
    res.json({ version: getVersion(), ...stats });
  });

  router.post("/jobs", verifyApiKey, async (req, res) => {
    const { url, discord_token, discordToken, job_type, jobType, max_retries, maxRetries, metadata } =
      req.body;
    const job = await getManager().createJob({
      url,
      discordToken: discord_token || discordToken,
      jobType: job_type || jobType || JobType.POKETWO_VERIFY,
      maxRetries: max_retries ?? maxRetries,
      metadata: metadata || {},
    });
    res.status(201).json(toPublicJob(job));
  });

  router.post("/verify", verifyApiKey, async (req, res) => {
    const { link, token, max_retries, maxRetries, metadata } = req.body;
    const wait = Math.min(Math.max(parseInt(req.query.wait || "0", 10), 0), 3600);
    const manager = getManager();

    const job = await manager.createJob({
      url: link,
      discordToken: token,
      jobType: JobType.POKETWO_VERIFY,
      maxRetries: max_retries ?? maxRetries,
      metadata: metadata || {},
    });

    if (wait <= 0) return res.json(jobToVerifyResponse(job));

    const finished = await waitForTerminal(manager, job.id, wait);
    if (!finished) return res.status(404).json({ detail: "Job not found" });
    res.json(jobToVerifyResponse(finished));
  });

  router.get("/jobs", verifyApiKey, async (req, res) => {
    const status = req.query.status || null;
    const limit = Math.min(Math.max(parseInt(req.query.limit || "50", 10), 1), 100);
    const offset = Math.max(parseInt(req.query.offset || "0", 10), 0);
    const jobs = await getManager().listJobs({ status, limit, offset });
    res.json({ jobs: jobs.map(toPublicJob), total: jobs.length, limit, offset });
  });

  router.get("/jobs/:jobId", verifyApiKey, async (req, res) => {
    const job = await getManager().getJob(req.params.jobId);
    if (!job) return res.status(404).json({ detail: "Job not found" });
    res.json(toPublicJob(job));
  });

  router.post("/jobs/:jobId/cancel", verifyApiKey, async (req, res) => {
    const job = await getManager().cancelJob(req.params.jobId);
    if (!job) return res.status(404).json({ detail: "Job not found" });
    res.json(toPublicJob(job));
  });

  router.get("/jobs/:jobId/screenshots/:filename", verifyApiKey, (req, res) => {
    const config = getConfig();
    const artifactsDir = path.join(resolvePath(config.jobs.artifactsDir), req.params.jobId);
    const filePath = path.resolve(artifactsDir, req.params.filename);
    if (!fs.existsSync(filePath) || !fs.statSync(filePath).isFile()) {
      return res.status(404).json({ detail: "Screenshot not found" });
    }
    if (!filePath.startsWith(path.resolve(artifactsDir) + path.sep)) {
      return res.status(403).json({ detail: "Access denied" });
    }
    res.type("png").sendFile(filePath);
  });

  router.get("/jobs/:jobId/report", verifyApiKey, async (req, res) => {
    const job = await getManager().getJob(req.params.jobId);
    if (!job) return res.status(404).json({ detail: "Job not found" });
    const config = getConfig();
    const artifactsDir = path.join(resolvePath(config.jobs.artifactsDir), req.params.jobId);
    res.json({
      job: toPublicJob(job),
      report: {
        summary: {
          success: job.result?.success || false,
          verified: job.result?.verified || false,
          attempts: job.attempt,
          durationSeconds: job.result?.durationSeconds || 0,
        },
        steps: (job.logs || []).map((log) => ({
          step: log.step,
          message: log.message,
          level: log.level,
          time: log.timestamp,
        })),
        screenshots: job.result?.screenshots || [],
        artifactsDir,
      },
    });
  });

  router.post("/admin/cleanup", verifyApiKey, async (req, res) => {
    const deleted = await getManager().cleanupOldJobs();
    res.json({ deletedJobs: deleted });
  });

  return router;
}
