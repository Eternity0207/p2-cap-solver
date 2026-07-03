import fs from "fs";
import path from "path";
import initSqlJs from "sql.js";
import { getConfig, resolvePath } from "../config.js";
import { log } from "../logger.js";
import { JobStatus } from "./models.js";

export class JobStore {
  constructor(dbPath) {
    this.dbPath = dbPath || resolvePath(getConfig().jobs.storePath);
    this.db = null;
    this.SQL = null;
  }

  async connect() {
    fs.mkdirSync(path.dirname(this.dbPath), { recursive: true });
    this.SQL = await initSqlJs();
    if (fs.existsSync(this.dbPath)) {
      const buffer = fs.readFileSync(this.dbPath);
      this.db = new this.SQL.Database(buffer);
    } else {
      this.db = new this.SQL.Database();
    }
    this.db.run(`
      CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        data TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      )
    `);
    this.db.run(`CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)`);
    this.db.run(`CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)`);
    this._persist();
    log("INFO", "job_store_connected", "", { path: this.dbPath });
  }

  close() {
    if (this.db) {
      this._persist();
      this.db.close();
      this.db = null;
    }
  }

  _persist() {
    const data = this.db.export();
    fs.writeFileSync(this.dbPath, Buffer.from(data));
  }

  save(job) {
    const now = new Date().toISOString();
    this.db.run(
      `INSERT INTO jobs (id, status, data, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET
         status = excluded.status,
         data = excluded.data,
         updated_at = excluded.updated_at`,
      [job.id, job.status, JSON.stringify(job), job.createdAt, now]
    );
    this._persist();
  }

  get(jobId) {
    const stmt = this.db.prepare("SELECT data FROM jobs WHERE id = ?");
    stmt.bind([jobId]);
    if (!stmt.step()) {
      stmt.free();
      return null;
    }
    const row = stmt.getAsObject();
    stmt.free();
    return JSON.parse(row.data);
  }

  listJobs({ status, limit = 50, offset = 0 } = {}) {
    let query;
    let params;
    if (status) {
      query = "SELECT data FROM jobs WHERE status = ? ORDER BY created_at DESC LIMIT ? OFFSET ?";
      params = [status, limit, offset];
    } else {
      query = "SELECT data FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?";
      params = [limit, offset];
    }
    const stmt = this.db.prepare(query);
    stmt.bind(params);
    const jobs = [];
    while (stmt.step()) {
      jobs.push(JSON.parse(stmt.getAsObject().data));
    }
    stmt.free();
    return jobs;
  }

  countByStatus() {
    const stmt = this.db.prepare("SELECT status, COUNT(*) as cnt FROM jobs GROUP BY status");
    const counts = {};
    while (stmt.step()) {
      const row = stmt.getAsObject();
      counts[row.status] = row.cnt;
    }
    stmt.free();
    return counts;
  }

  cleanupOld(hours) {
    const cutoff = new Date(Date.now() - hours * 3600 * 1000).toISOString();
    const stmt = this.db.prepare(
      `DELETE FROM jobs WHERE created_at < ? AND status IN (?, ?, ?)`
    );
    stmt.run([cutoff, JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]);
    const changes = this.db.getRowsModified();
    stmt.free();
    this._persist();
    return changes;
  }
}
