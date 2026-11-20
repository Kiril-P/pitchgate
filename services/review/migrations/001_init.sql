-- revision_id and idea_id belong to the ideas service, so they are plain IDs here with no foreign key.

CREATE TABLE verdicts (
    id INT IDENTITY(1, 1) PRIMARY KEY,
    revision_id INT NOT NULL UNIQUE,
    market_need FLOAT NULL,
    feasibility FLOAT NULL,
    differentiation FLOAT NULL,
    safety_risk FLOAT NULL,
    confidence FLOAT NULL,
    evidence FLOAT NULL,
    answered FLOAT NULL,
    label NVARCHAR(16) NOT NULL CHECK (label IN ('UNPROVEN', 'PARTIAL', 'PROVEN', 'PENDING')),
    [rule] NVARCHAR(64) NOT NULL,
    created_at NVARCHAR(32) NOT NULL
);

CREATE TABLE jev_calls (
    id INT IDENTITY(1, 1) PRIMARY KEY,
    idea_id INT NOT NULL,
    revision_id INT NOT NULL,
    purpose NVARCHAR(16) NOT NULL CHECK (purpose IN ('verdict', 'gate')),
    ok BIT NOT NULL,
    created_at NVARCHAR(32) NOT NULL
);

CREATE TABLE gates (
    id INT IDENTITY(1, 1) PRIMARY KEY,
    idea_id INT NOT NULL,
    session INT NOT NULL,
    last_evidence_id INT NOT NULL,
    evidence_strength FLOAT NULL,
    pain_frequency FLOAT NULL,
    willingness_to_pay FLOAT NULL,
    safety_risk FLOAT NULL,
    label NVARCHAR(16) NOT NULL CHECK (label IN ('PASSED', 'SENT_BACK', 'PENDING')),
    [rule] NVARCHAR(64) NOT NULL,
    created_at NVARCHAR(32) NOT NULL
);

CREATE TABLE chef_messages (
    id INT IDENTITY(1, 1) PRIMARY KEY,
    revision_id INT NOT NULL,
    kind NVARCHAR(16) NOT NULL
        CHECK (kind IN ('turn', 'polished', 'homework', 'next_steps', 'starter_pack')),
    body NVARCHAR(MAX) NOT NULL,
    question NVARCHAR(MAX) NOT NULL DEFAULT '',
    created_at NVARCHAR(32) NOT NULL,
    CONSTRAINT chef_messages_revision_kind UNIQUE (revision_id, kind)
);

CREATE INDEX jev_calls_idea ON jev_calls(idea_id);
CREATE INDEX jev_calls_revision ON jev_calls(revision_id);
CREATE INDEX gates_idea ON gates(idea_id);
