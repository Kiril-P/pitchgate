-- When the founder last wrote anything on an idea, so boards can list the most recently active ideas first.
-- Existing rows keep every value and get the time of their newest pitch, answer or log.

ALTER TABLE ideas ADD updated_at NVARCHAR(32) NULL;
GO

UPDATE ideas SET updated_at = (
    SELECT MAX(activity.stamp)
    FROM (
        SELECT ideas.created_at AS stamp
        UNION ALL SELECT revisions.created_at FROM revisions WHERE revisions.idea_id = ideas.id
        UNION ALL SELECT evidence.created_at FROM evidence WHERE evidence.idea_id = ideas.id
    ) AS activity
);

ALTER TABLE ideas ALTER COLUMN updated_at NVARCHAR(32) NOT NULL;
