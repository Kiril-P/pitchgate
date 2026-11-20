CREATE TABLE ideas (
    id INT IDENTITY(1, 1) PRIMARY KEY,
    display_name NVARCHAR(200) NOT NULL,
    status NVARCHAR(16) NOT NULL DEFAULT 'cooking'
        CHECK (status IN ('cooking', 'parked', 'served', 'binned')),
    station NVARCHAR(16) NOT NULL DEFAULT 'grill'
        CHECK (station IN ('prep', 'grill', 'tasting', 'plating', 'recipe', 'mise', 'takeaway')),
    token NVARCHAR(64) NOT NULL,
    tone NVARCHAR(16) NOT NULL DEFAULT 'tough' CHECK (tone IN ('supportive', 'tough', 'ramsay')),
    level NVARCHAR(16) NOT NULL DEFAULT 'idea' CHECK (level IN ('new', 'idea', 'tested')),
    pivot_of INT NULL,
    shared BIT NOT NULL DEFAULT 0,
    consent_at NVARCHAR(32) NULL,
    created_at NVARCHAR(32) NOT NULL,
    CONSTRAINT ideas_token UNIQUE (token)
);

CREATE TABLE revisions (
    id INT IDENTITY(1, 1) PRIMARY KEY,
    idea_id INT NOT NULL REFERENCES ideas(id),
    parent_id INT NULL REFERENCES revisions(id),
    kind NVARCHAR(8) NOT NULL CHECK (kind IN ('pitch', 'answer')),
    one_liner NVARCHAR(MAX) NULL,
    story NVARCHAR(MAX) NULL,
    answer NVARCHAR(MAX) NULL,
    created_at NVARCHAR(32) NOT NULL,
    CHECK (
        (kind = 'pitch' AND parent_id IS NULL AND one_liner IS NOT NULL
            AND story IS NOT NULL AND answer IS NULL)
        OR
        (kind = 'answer' AND parent_id IS NOT NULL AND answer IS NOT NULL
            AND one_liner IS NULL AND story IS NULL)
    )
);

CREATE TABLE evidence (
    id INT IDENTITY(1, 1) PRIMARY KEY,
    idea_id INT NOT NULL REFERENCES ideas(id),
    session INT NOT NULL,
    kind NVARCHAR(16) NOT NULL DEFAULT 'conversation' CHECK (kind IN ('conversation', 'fact')),
    who NVARCHAR(400) NOT NULL,
    role NVARCHAR(400) NOT NULL DEFAULT '',
    spoken_on NVARCHAR(32) NOT NULL,
    today_they NVARCHAR(MAX) NOT NULL DEFAULT '',
    paid NVARCHAR(MAX) NOT NULL DEFAULT '',
    quote NVARCHAR(MAX) NOT NULL,
    source NVARCHAR(2000) NOT NULL DEFAULT '',
    created_at NVARCHAR(32) NOT NULL
);

CREATE INDEX revisions_idea ON revisions(idea_id);
CREATE INDEX evidence_idea ON evidence(idea_id);
