import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import fs from "node:fs/promises";
import path from "node:path";
import {
  fileExists,
  getCitCPathHash,
  STATE_DIR,
  OPENCLAW_JSON_PATH,
} from "../src/utils.js";

describe("cxasgemmaclaw CLI Utilities", () => {
  it("fileExists returns true for existing files", async () => {
    const existing = await fileExists(process.cwd());
    expect(existing).toBe(true);
  });

  it("fileExists returns false for missing files", async () => {
    const missing = await fileExists(path.join(process.cwd(), "missing-file-xyz.json"));
    expect(missing).toBe(false);
  });

  it("getCitCPathHash generates stable 10-char hash", () => {
    const testPath = "/google/src/cloud/user/workspace/google3/project";
    const hash1 = getCitCPathHash(testPath);
    const hash2 = getCitCPathHash(testPath);

    expect(hash1).toHaveLength(10);
    expect(hash1).toBe(hash2);
  });

  it("STATE_DIR resolves correctly under user home directory", () => {
    expect(STATE_DIR).toContain(".gemmaclaw");
  });

  it("OPENCLAW_JSON_PATH resolves openclaw.json config location", () => {
    expect(OPENCLAW_JSON_PATH).toContain("openclaw.json");
  });
});

import { injectRegistryTemplates } from "../src/utils.js";

describe("cxasgemmaclaw Integration & Guardrails E2E", () => {
  const mockWorkspaceDir = path.join(process.cwd(), "tests", "mock-workspace");

  beforeEach(async () => {
    // Ensure clean mock workspace directory state
    await fs.mkdir(mockWorkspaceDir, { recursive: true });
  });

  afterEach(async () => {
    // Cleanup mock workspace directory
    await fs.rm(mockWorkspaceDir, { recursive: true, force: true });
  });

  it("injectRegistryTemplates stages Albertsons prompts and registers custom skills E2E", async () => {
    // Inject templates E2E
    await injectRegistryTemplates("babsit", mockWorkspaceDir);

    // 1. Verify prompt files were created successfully
    const soulExists = await fileExists(path.join(mockWorkspaceDir, "SOUL.md"));
    const agentsExists = await fileExists(path.join(mockWorkspaceDir, "AGENTS.md"));
    expect(soulExists).toBe(true);
    expect(agentsExists).toBe(true);

    // 2. Verify Albertsons prompts staging headers are present
    const soulContent = await fs.readFile(path.join(mockWorkspaceDir, "SOUL.md"), "utf-8");
    expect(soulContent).toContain("# Albertsons FDE Onboarding");

    // 3. Verify skills directory and scrapi skill packaging is staged E2E
    const skillExists = await fileExists(path.join(mockWorkspaceDir, ".openclaw", "skills", "scrapi-ccas", "SKILL.md"));
    expect(skillExists).toBe(true);
  });

  it("injectRegistryTemplates duplicate-guard blocks redundant appends to prevent prompts bloat overflows", async () => {
    // Run turn 1 (Initial injection)
    await injectRegistryTemplates("babsit", mockWorkspaceDir);
    const size1 = (await fs.stat(path.join(mockWorkspaceDir, "SOUL.md"))).size;

    // Run turn 2 (Duplicate injection sweep)
    await injectRegistryTemplates("babsit", mockWorkspaceDir);
    const size2 = (await fs.stat(path.join(mockWorkspaceDir, "SOUL.md"))).size;

    // Verify duplicate check triggered successfully and file size remained 100% identical!
    expect(size1).toBeGreaterThan(0);
    expect(size2).toBe(size1);
  });
});
