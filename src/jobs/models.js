import { v4 as uuidv4 } from "uuid";

export const JobStatus = {
  PENDING: "pending",
  QUEUED: "queued",
  RUNNING: "running",
  WAITING_CAPTCHA: "waiting_captcha",
  WAITING_DISCORD: "waiting_discord",
  WAITING_AUTHORIZE: "waiting_authorize",
  VERIFYING: "verifying",
  COMPLETED: "completed",
  FAILED: "failed",
  RETRYING: "retrying",
  CANCELLED: "cancelled",
};

export const JobType = {
  POKETWO_VERIFY: "poketwo_verify",
};

const TERMINAL = new Set([
  JobStatus.COMPLETED,
  JobStatus.FAILED,
  JobStatus.CANCELLED,
]);

export function isTerminal(status) {
  return TERMINAL.has(status);
}

export function createJob({ url, discordToken, jobType = JobType.POKETWO_VERIFY, maxRetries = 3, metadata = {} }) {
  const now = new Date().toISOString();
  return {
    id: uuidv4(),
    status: JobStatus.QUEUED,
    jobType,
    url,
    discordToken,
    maxRetries,
    attempt: 0,
    progress: { currentStep: "", percent: 0, message: "" },
    logs: [],
    result: {
      success: false,
      verified: false,
      finalUrl: null,
      screenshots: [],
      error: null,
      attempts: 0,
      durationSeconds: 0,
    },
    metadata,
    createdAt: now,
    updatedAt: now,
    startedAt: null,
    completedAt: null,
  };
}

export function addLog(job, step, message, level = "info", data = {}) {
  job.logs.push({
    timestamp: new Date().toISOString(),
    level,
    step,
    message,
    data,
  });
  job.updatedAt = new Date().toISOString();
}

export function updateProgress(job, step, percent, message = "") {
  job.progress = { currentStep: step, percent, message };
  job.updatedAt = new Date().toISOString();
}

export function toPublicJob(job) {
  const { discordToken, ...rest } = job;
  return rest;
}
