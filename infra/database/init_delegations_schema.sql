-- FlowPilot Delegation Database Schema for PostgreSQL
-- Migration from SQLite to PostgreSQL

CREATE TABLE IF NOT EXISTS delegations (
    id SERIAL PRIMARY KEY,
    principal_id TEXT NOT NULL,
    delegate_id TEXT NOT NULL,
    workflow_id TEXT,
    scope TEXT NOT NULL DEFAULT '["execute"]',
    expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    revoked_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(principal_id, delegate_id, workflow_id)
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_principal_id ON delegations(principal_id);
CREATE INDEX IF NOT EXISTS idx_delegate_id ON delegations(delegate_id);
CREATE INDEX IF NOT EXISTS idx_workflow_id ON delegations(workflow_id);
CREATE INDEX IF NOT EXISTS idx_expires_at ON delegations(expires_at);
CREATE INDEX IF NOT EXISTS idx_revoked_at ON delegations(revoked_at);

-- Optional: Add comments for documentation
COMMENT ON TABLE delegations IS 'Delegation relationships between principals and delegates with expiration and scoping';
COMMENT ON COLUMN delegations.principal_id IS 'ID of the principal delegating authority (resource owner)';
COMMENT ON COLUMN delegations.delegate_id IS 'ID of the delegate receiving authority';
COMMENT ON COLUMN delegations.workflow_id IS 'Optional workflow ID to scope the delegation';
COMMENT ON COLUMN delegations.scope IS 'JSON array of allowed actions (e.g., ["read", "execute"])';
COMMENT ON COLUMN delegations.expires_at IS 'Timestamp when delegation expires (UTC)';
COMMENT ON COLUMN delegations.created_at IS 'Timestamp when delegation was created (UTC)';
COMMENT ON COLUMN delegations.revoked_at IS 'Timestamp when delegation was revoked (NULL if active)';
