PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS run_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competition_run_id INTEGER REFERENCES competition_runs(id) ON DELETE CASCADE,
    challenge_run_id INTEGER REFERENCES challenge_runs(id) ON DELETE CASCADE,
    level TEXT NOT NULL DEFAULT 'info',
    message TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_profiles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    rate_key TEXT NOT NULL,
    color TEXT NOT NULL DEFAULT '#0f172a',
    reasoning_effort TEXT NOT NULL DEFAULT 'high',
    temperature REAL NOT NULL DEFAULT 0.2,
    skill_profile REAL NOT NULL DEFAULT 0.5,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ctf_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    ctfd_url TEXT NOT NULL,
    ctfd_token TEXT NOT NULL DEFAULT '',
    ctfd_auth_type TEXT NOT NULL DEFAULT 'token',
    sandbox_digest TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    budget_wall_seconds INTEGER NOT NULL,
    budget_input_tokens INTEGER NOT NULL,
    budget_output_tokens INTEGER NOT NULL,
    budget_usd REAL NOT NULL,
    budget_flag_attempts INTEGER NOT NULL,
    flag_regex TEXT NOT NULL DEFAULT 'flag\\{.*?\\}',
    mode TEXT NOT NULL DEFAULT 'competition',
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    ended_at TEXT
);

CREATE TABLE IF NOT EXISTS ctf_accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ctf_event_id INTEGER NOT NULL REFERENCES ctf_events(id) ON DELETE CASCADE,
    model_id INTEGER NOT NULL REFERENCES model_profiles(id) ON DELETE CASCADE,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    team_name TEXT NOT NULL DEFAULT '',
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(ctf_event_id, model_id)
);

CREATE TABLE IF NOT EXISTS challenges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ctf_event_id INTEGER NOT NULL REFERENCES ctf_events(id) ON DELETE CASCADE,
    remote_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL DEFAULT 'misc',
    points INTEGER NOT NULL DEFAULT 100,
    difficulty TEXT NOT NULL DEFAULT 'medium',
    description TEXT NOT NULL DEFAULT '',
    solves INTEGER NOT NULL DEFAULT 0,
    connection_info TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(ctf_event_id, remote_id)
);

CREATE TABLE IF NOT EXISTS competition_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ctf_event_id INTEGER NOT NULL REFERENCES ctf_events(id) ON DELETE CASCADE,
    model_id INTEGER NOT NULL REFERENCES model_profiles(id) ON DELETE CASCADE,
    mode TEXT NOT NULL DEFAULT 'competition',
    tool TEXT NOT NULL,
    model TEXT NOT NULL,
    model_version TEXT NOT NULL DEFAULT '',
    sandbox_digest TEXT NOT NULL,
    flagfarm_commit TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    budget_wall_seconds INTEGER NOT NULL,
    budget_input_tokens INTEGER NOT NULL,
    budget_output_tokens INTEGER NOT NULL,
    budget_usd REAL NOT NULL,
    budget_flag_attempts INTEGER NOT NULL,
    total_input_tokens INTEGER NOT NULL DEFAULT 0,
    total_output_tokens INTEGER NOT NULL DEFAULT 0,
    total_reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    total_cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    total_cost_usd REAL NOT NULL DEFAULT 0,
    total_flag_attempts INTEGER NOT NULL DEFAULT 0,
    total_turns INTEGER NOT NULL DEFAULT 0,
    summary_json TEXT NOT NULL DEFAULT '{}',
    started_at TEXT,
    ended_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(ctf_event_id, model_id, mode)
);

CREATE TABLE IF NOT EXISTS challenge_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    competition_run_id INTEGER NOT NULL REFERENCES competition_runs(id) ON DELETE CASCADE,
    challenge_id INTEGER NOT NULL REFERENCES challenges(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'queued',
    attempt_index INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    ended_at TEXT,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    reasoning_tokens INTEGER NOT NULL DEFAULT 0,
    cached_input_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    flag_attempts INTEGER NOT NULL DEFAULT 0,
    turns INTEGER NOT NULL DEFAULT 0,
    solve_time_seconds REAL,
    transcript_excerpt TEXT NOT NULL DEFAULT '',
    error_message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(competition_run_id, challenge_id)
);

DROP VIEW IF EXISTS v_competition_scores;
CREATE VIEW v_competition_scores AS
SELECT
    cr.id AS competition_run_id,
    cr.ctf_event_id,
    cr.model_id,
    cr.mode,
    cr.status,
    cr.tool,
    cr.model,
    COUNT(chr.id) AS attempted,
    SUM(CASE WHEN chr.status = 'solved' THEN 1 ELSE 0 END) AS solves,
    SUM(CASE WHEN chr.status = 'solved' THEN ch.points ELSE 0 END) AS raw_points,
    SUM(chr.cost_usd) AS total_usd,
    SUM(CASE WHEN chr.status = 'budget_exhausted' THEN 1 ELSE 0 END) AS budget_exhausted,
    SUM(CASE WHEN chr.status = 'failed' THEN 1 ELSE 0 END) AS failed,
    SUM(CASE WHEN chr.status = 'timed_out' THEN 1 ELSE 0 END) AS timed_out,
    SUM(CASE WHEN chr.status = 'crashed' THEN 1 ELSE 0 END) AS crashed,
    cr.budget_usd AS budget_usd
FROM competition_runs cr
LEFT JOIN challenge_runs chr ON chr.competition_run_id = cr.id
LEFT JOIN challenges ch ON ch.id = chr.challenge_id
GROUP BY
    cr.id,
    cr.ctf_event_id,
    cr.model_id,
    cr.mode,
    cr.status,
    cr.tool,
    cr.model,
    cr.budget_usd;
