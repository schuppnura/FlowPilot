package auto_book

# Auto-Book Policy for FlowPilot
#
# This policy implements ABAC (Attribute-Based Access Control) conditions
# for autonomous booking by AI agents and read-only access for invited users.
#
# Supported actions:
# - "execute": Execute workflow items (requires delegation, consent, cost/lead time checks)
# - "read": View workflows (requires delegation and matching persona)
#
# Execute conditions:
# 1. Anti-spoofing check (principal_id matches owner_id OR delegation is valid)
# 2. Valid delegation (if principal_id != owner_id)
# 3. Persona check (delegated users must have "travel-agent", owners must match owner persona)
# 4. User consent for auto-booking
# 5. Total trip cost within limit
# 6. Sufficient advance notice for departure
# 7. Airline risk score within threshold
#
# Read conditions:
# 1. Owner can always read
# 2. Delegated users must have valid delegation
# 3. Delegated users must have matching persona

default allow := false

# Main allow rule: route by action
allow if {
  input.action.name == "execute"
  allow_execute
}

allow if {
  input.action.name == "read"
  allow_read
}

# Execute action: all gates must pass
allow_execute if {
  authorized_principal  # Anti-spoofing and delegation check
  persona_valid  # Persona check (delegated users must be travel-agent, owners must match)
  has_consent
  within_cost_limit
  sufficient_advance
  acceptable_risk
}

# Reason codes returned as a set
# Execute action reason codes
# Distinguish between no delegation and insufficient permissions
reasons[code] if {
  input.action.name == "execute"
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  # No delegation exists at all
  not input.delegation.valid
  code := "auto_book.principal_spoofing"
}

reasons[code] if {
  input.action.name == "execute"
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  # Delegation exists but doesn't have execute permission
  input.delegation.valid == true
  not input.delegation.has_action
  code := "auto_book.insufficient_delegation_permissions"
}

reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.persona_mismatch"
  authorized_principal
  not persona_valid
}

reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.no_consent"
  authorized_principal
  not has_consent
}

reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.cost_limit_exceeded"
  authorized_principal
  has_consent
  not within_cost_limit
}

reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.insufficient_advance_notice"
  authorized_principal
  has_consent
  within_cost_limit
  not sufficient_advance
}

reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.airline_risk_too_high"
  authorized_principal
  has_consent
  within_cost_limit
  sufficient_advance
  not acceptable_risk
}

# Read action reason codes
reasons[code] if {
  input.action.name == "read"
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  # No delegation exists at all
  not input.delegation.valid
  code := "read.no_delegation"
}

reasons[code] if {
  input.action.name == "read"
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  # Delegation exists but doesn't have read permission
  input.delegation.valid == true
  not input.delegation.has_action
  code := "read.insufficient_delegation_permissions"
}

reasons[code] if {
  input.action.name == "read"
  not allow_read
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  input.delegation.valid
  input.delegation.has_action
  not read_persona_valid
  code := "read.persona_mismatch"
}

# Anti-spoofing and delegation check
# The principal (subject making the request) must either:
# 1. Be the owner of the resource, OR
# 2. Have a valid delegation from the owner (computed by authz-api via delegation-api)
# 3. Have sufficient permissions for the requested action
authorized_principal if {
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id == owner_id
}

authorized_principal if {
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  # Check computed delegation result (delegation chain already traversed)
  has_valid_delegation_for_action
}

# Helper: Check if delegation exists with required action
has_valid_delegation_for_action if {
  input.delegation.valid == true
  input.delegation.has_action == true
}

# Persona validation
# When a user is delegated to execute a workflow (principal != owner):
#   - The principal must have one of the authorized agent personas: "travel-agent", "ai-agent", "secretary"
# When a user executes their own workflow (principal == owner):
#   - The principal must have selected the same persona as the owner's persona
#
# Configuration Note:
# The valid agent personas are currently hardcoded here but should match the
# DELEGATION_PERSONAS environment variable in the service configuration.
# Future enhancement: Pass personas via input.config.delegation_personas

# Valid agent personas that can be delegated to execute workflows
# These should match DELEGATION_PERSONAS env var: "ai-agent,travel-agent,secretary"
valid_agent_personas := {"travel-agent", "ai-agent", "secretary"}

persona_valid if {
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  # Delegated case: must be one of the valid agent personas
  input.subject.persona != ""
  valid_agent_personas[input.subject.persona]
}

persona_valid if {
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id == owner_id
  # Owner case: must match owner persona
  owner_persona := input.resource.properties.owner.persona
  input.subject.persona == owner_persona
  owner_persona != ""  # Owner persona must be set
  input.subject.persona != ""  # Subject persona must be set
}

# ============================================================================
# Read Action Rules
# ============================================================================

# Allow read if user is the owner
allow_read if {
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id == owner_id
}

# Allow read if user has valid delegation (with read action) and matching persona
allow_read if {
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  input.delegation.valid == true
  input.delegation.has_action == true  # Delegation chain permits read action
  read_persona_valid
}

# Persona validation for read: agent personas OR matching owner persona
read_persona_valid if {
  # Agent personas can always read (if they have delegation)
  input.subject.persona != ""
  valid_agent_personas[input.subject.persona]
}

read_persona_valid if {
  # User with matching owner persona can read
  owner_persona := input.resource.properties.owner.persona
  input.subject.persona == owner_persona
  owner_persona != ""
  input.subject.persona != ""
}

# Consent check - autobook settings belong to the resource owner (in resource.properties.owner)
has_consent if {
  input.resource.properties.owner.autobook_consent == true
}

# Cost gate - autobook settings belong to the resource owner (in resource.properties.owner)
within_cost_limit if {
  planned_price := to_number(input.resource.planned_price)
  max_cost := to_number(input.resource.properties.owner.autobook_price)
  planned_price <= max_cost
}

# Advance notice gate (checks if departure is at least autobook_leadtime days in the future)
sufficient_advance if {
  departure_date_str := sprintf("%v", [input.resource.departure_date])
  # Normalize departure date to RFC3339 format
  normalized_departure := normalize_departure_date(departure_date_str)
  departure := time.parse_rfc3339_ns(normalized_departure)
  now := time.now_ns()
  min_days := to_number(input.resource.properties.owner.autobook_leadtime)
  # Calculate days until departure
  delta_days := (departure - now) / 1000000000 / 60 / 60 / 24
  # Departure must be at least min_days in the future
  delta_days >= min_days
}

# Helper function to normalize date strings to RFC3339 format
normalize_departure_date(date_str) := rfc3339_str if {
  # If it's already RFC3339 format (contains "T"), use as-is
  contains(date_str, "T")
  rfc3339_str := date_str
}

normalize_departure_date(date_str) := rfc3339_str if {
  # If it's date-only format (YYYY-MM-DD), convert to RFC3339 at midnight UTC
  not contains(date_str, "T")
  date_parts := split(date_str, "-")
  count(date_parts) == 3
  year := to_number(date_parts[0])
  month := to_number(date_parts[1])
  day := to_number(date_parts[2])
  rfc3339_str := sprintf("%04d-%02d-%02dT00:00:00Z", [year, month, day])
}

# Airline risk gate; if no score provided, skip the check
acceptable_risk if {
  not input.resource.airline_risk_score
}

acceptable_risk if {
  risk := to_number(input.resource.airline_risk_score)
  max_risk := to_number(input.resource.properties.owner.autobook_risklevel)
  risk <= max_risk
}