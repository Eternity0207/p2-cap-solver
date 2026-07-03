import { getConfig } from "../config.js";
import { log } from "../logger.js";
import { PoketwoAutomation } from "../automation/poketwo.js";
import { BrowserPool } from "../browser/launcher.js";
import { createJob, addLog, JobStatus, JobType, isTerminal } from "./models.js";
import { JobStore } from "./store.js";

export class JobManager {
  constructor({ store, pool, config } = {}) {
    this.config = config || getConfig();
    this.store = store || new JobStore();
    this.pool = pool || new BrowserPool(this.config);
    this._queue = [];
    this._subscribers = new Map();
    this._globalSubscribers = [];
    this._activeJobs = new Map();
    this._running = false;
    this._workers = [];
    this._automations = {
      [JobType.POKETWO_VERIFY]: new PoketwoAutomation(this.config),
    };
  }

  async start(workerCount) {
    await this.store.connect();
    this._running = true;
    const count = workerCount || this.config.browser.maxConcurrent;
    for (let i = 0; i < count; i++) {
      this._workers.push(this._workerLoop(i));
    }
    log("INFO", "job_manager_started", "", { workers: count });
  }

  async stop() {
    this._running = false;
    await Promise.allSettled(this._workers);
    this._workers = [];
    for (const [, controller] of this._activeJobs) {
      controller.abort();
    }
    this._activeJobs.clear();
    await this.pool.shutdown();
    this.store.close();
    log("INFO", "job_manager_stopped");
  }

  subscribe(jobId, callback) {
    if (!this._subscribers.has(jobId)) this._subscribers.set(jobId, []);
    this._subscribers.get(jobId).push(callback);
  }

  unsubscribe(jobId, callback) {
    const list = this._subscribers.get(jobId) || [];
    this._subscribers.set(
      jobId,
      list.filter((c) => c !== callback)
    );
  }

  subscribeAll(callback) {
    this._globalSubscribers.push(callback);
  }

  async _notify(job) {
    this.store.save(job);
    for (const cb of this._subscribers.get(job.id) || []) {
      try {
        await cb(job);
      } catch (e) {
        log("WARN", "subscriber_error", String(e), { jobId: job.id });
      }
    }
    for (const cb of this._globalSubscribers) {
      try {
        await cb(job);
      } catch (e) {
        log("WARN", "global_subscriber_error", String(e));
      }
    }
  }

  async createJob(request) {
    const job = createJob({
      url: request.url,
      discordToken: request.discordToken,
      jobType: request.jobType || JobType.POKETWO_VERIFY,
      maxRetries: request.maxRetries ?? this.config.jobs.maxRetries,
      metadata: request.metadata || {},
    });
    addLog(job, "created", `Job queued for ${job.url}`);
    this.store.save(job);
    this._queue.push(job.id);
    await this._notify(job);
    log("INFO", "job_created", "", { jobId: job.id, url: job.url });
    return job;
  }

  async getJob(jobId) {
    return this.store.get(jobId);
  }

  async cancelJob(jobId) {
    const job = this.store.get(jobId);
    if (!job) return null;
    if (isTerminal(job.status)) return job;
    job.status = JobStatus.CANCELLED;
    job.completedAt = new Date().toISOString();
    addLog(job, "cancelled", "Job cancelled by user");
    await this._notify(job);
    const active = this._activeJobs.get(jobId);
    if (active) active.abort();
    return job;
  }

  async listJobs(opts) {
    return this.store.listJobs(opts);
  }

  async getStats() {
    return {
      queueSize: this._queue.length,
      activeBrowsers: this.pool.activeCount,
      maxConcurrent: this.pool.maxConcurrent,
      jobsByStatus: this.store.countByStatus(),
    };
  }

  async cleanupOldJobs() {
    return this.store.cleanupOld(this.config.jobs.cleanupAfterHours);
  }

  async _workerLoop(workerId) {
    log("INFO", "worker_started", "", { workerId });
    while (this._running) {
      if (!this._queue.length) {
        await new Promise((r) => setTimeout(r, 200));
        continue;
      }
      const jobId = this._queue.shift();
      const job = this.store.get(jobId);
      if (!job || job.status === JobStatus.CANCELLED) continue;

      const controller = new AbortController();
      this._activeJobs.set(jobId, controller);
      try {
        await this._executeJob(jobId, controller.signal);
      } catch (e) {
        log("ERROR", "job_worker_error", String(e), { jobId, workerId });
      } finally {
        this._activeJobs.delete(jobId);
      }
    }
  }

  async _executeJob(jobId, signal) {
    let job = this.store.get(jobId);
    if (!job || job.status === JobStatus.CANCELLED) return;

    const start = Date.now();
    job.startedAt = new Date().toISOString();
    job.status = JobStatus.RUNNING;
    await this._notify(job);

    const automation = this._automations[job.jobType];
    if (!automation) {
      job.status = JobStatus.FAILED;
      job.result.error = `Unknown job type: ${job.jobType}`;
      job.completedAt = new Date().toISOString();
      await this._notify(job);
      return;
    }

    const maxAttempts = job.maxRetries + 1;
    let success = false;

    for (let attempt = 1; attempt <= maxAttempts; attempt++) {
      if (signal.aborted) return;

      job = this.store.get(jobId);
      if (!job || job.status === JobStatus.CANCELLED) return;

      job.attempt = attempt;
      if (attempt > 1) {
        job.status = JobStatus.RETRYING;
        addLog(job, "retry", `Attempt ${attempt}/${maxAttempts}`);
        await this._notify(job);
        await new Promise((r) => setTimeout(r, this.config.jobs.retryDelaySeconds * 1000));
      }

      let session = null;
      try {
        const onProgress = async (updated) => {
          await this._notify(updated);
        };

        session = await this.pool.acquire(job.id);

        const timeoutMs = this.config.browser.jobTimeoutSeconds * 1000;
        success = await Promise.race([
          automation.execute(job, session, onProgress),
          new Promise((_, reject) =>
            setTimeout(() => reject(new Error("Job exceeded timeout")), timeoutMs)
          ),
        ]);

        if (success) break;
      } catch (e) {
        addLog(job, e.message === "Job exceeded timeout" ? "timeout" : "error", String(e), "error");
        log("ERROR", "job_execution_error", String(e), { jobId: job.id, attempt });
      } finally {
        if (session) await this.pool.release(session, true);
      }
    }

    const duration = (Date.now() - start) / 1000;
    job.result.success = success;
    job.result.verified = success;
    job.result.attempts = job.attempt;
    job.result.durationSeconds = duration;
    job.completedAt = new Date().toISOString();

    if (success) {
      job.status = JobStatus.COMPLETED;
      addLog(job, "completed", "Verification successful");
    } else {
      job.status = JobStatus.FAILED;
      job.result.error = job.result.error || "Verification failed after all retries";
      addLog(job, "failed", job.result.error, "error");
    }

    await this._notify(job);
    log("INFO", "job_finished", "", {
      jobId: job.id,
      success,
      attempts: job.attempt,
      duration,
    });
  }
}

export async function waitForTerminal(manager, jobId, timeoutSeconds) {
  const deadline = Date.now() + timeoutSeconds * 1000;
  while (Date.now() < deadline) {
    const job = await manager.getJob(jobId);
    if (!job) return null;
    if (isTerminal(job.status)) return job;
    await new Promise((r) => setTimeout(r, 1000));
  }
  return manager.getJob(jobId);
}
