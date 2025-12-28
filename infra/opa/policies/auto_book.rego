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
reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.principal_spoofing"
  not authorized_principal
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
  code := "read.no_delegation"
  not allow_read
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  not delegation_exists(owner_id, principal_id)
}

reasons[code] if {
  input.action.name == "read"
  code := "read.persona_mismatch"
  not allow_read
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  delegation_exists(owner_id, principal_id)
  not read_persona_valid
}

# Anti-spoofing and delegation check
# The principal (subject making the request) must either:
# 1. Be the owner of the resource, OR
# 2. Have a valid delegation from the owner
authorized_principal if {
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id == owner_id
}

authorized_principal if {
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  # Check if there's a delegation path from owner to principal
  delegation_exists(owner_id, principal_id)
}

# Persona validation
# When a user is delegated to execute a workflow (principal != owner):
#   - The principal must have selected the persona "travel-agent"
# When a user executes their own workflow (principal == owner):
#   - The principal must have selected the same persona as the owner's persona
persona_valid if {
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  # Delegated case: must be travel-agent
  input.subject.persona == "travel-agent"
  input.subject.persona != ""  # Subject persona must be set
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

# Check if a delegation exists from owner to principal
# This checks for a direct delegation in the input.delegations list
delegation_exists(owner_id, principal_id) if {
  # Look for a delegation where owner delegates to principal (direct match)
  some delegation in input.delegations
  delegation.principal_id == owner_id
  delegation.delegate_id == principal_id
  # Check if delegation is for the current workflow or is a general delegation
  workflow_matches(delegation, input.resource.workflow_id)
}

# Helper: Check if delegation applies to the current workflow
workflow_matches(delegation, workflow_id) if {
  # Delegation is workflow-specific and matches
  delegation.workflow_id == workflow_id
}

workflow_matches(delegation, workflow_id) if {
  # Delegation is general (no workflow_id specified)
  not delegation.workflow_id
}

workflow_matches(delegation, workflow_id) if {
  # Delegation workflow_id is null
  delegation.workflow_id == null
}

workflow_matches(delegation, workflow_id) if {
# Delegation workflow_id is empty string
  delegation.workflow_id == ""
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

# Allow read if user has valid delegation and matching persona
allow_read if {
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  principal_id != owner_id
  delegation_exists(owner_id, principal_id)
  read_persona_valid
}

# Persona validation for read: user persona must match owner persona
read_persona_valid if {
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