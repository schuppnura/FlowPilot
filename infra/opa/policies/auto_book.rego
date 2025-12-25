package auto_book

# Auto-Book Policy for FlowPilot
#
# This policy implements ABAC (Attribute-Based Access Control) conditions
# for autonomous booking by AI agents. It evaluates the following conditions:
# 1. Anti-spoofing check (principal_id matches owner_id OR delegation is valid)
# 2. Valid delegation (if principal_id != owner_id)
# 3. User consent for auto-booking
# 4. Total trip cost within limit
# 5. Sufficient advance notice for departure
# 6. Airline risk score within threshold


default allow := false

# Main allow rule: all gates must pass
allow if {
  authorized_principal  # Anti-spoofing and delegation check
  has_consent
  within_cost_limit
  sufficient_advance
  acceptable_risk
}

# Reason codes returned as a set
# Principal spoofing: when principal != owner AND no valid delegation exists
# This is distinct from "not authorized" - spoofing specifically means an unauthorized principal
reasons[code] if {
  code := "auto_book.principal_spoofing"
  principal_id := input.user.sub
  owner_id := input.resource.owner_id
  owner_id != null  # Only check spoofing if there's an owner to compare against
  principal_id != owner_id
  not valid_delegation_path(owner_id, principal_id)
}

reasons[code] if {
  code := "auto_book.no_consent"
  authorized_principal
  not has_consent
}

reasons[code] if {
  code := "auto_book.cost_limit_exceeded"
  authorized_principal
  has_consent
  not within_cost_limit
}

reasons[code] if {
  code := "auto_book.insufficient_advance_notice"
  authorized_principal
  has_consent
  within_cost_limit
  not sufficient_advance
}

reasons[code] if {
  code := "auto_book.airline_risk_too_high"
  authorized_principal
  has_consent
  within_cost_limit
  sufficient_advance
  not acceptable_risk
}

# Anti-spoofing and delegation check
# The principal (user making the request) must either:
# 1. Be the owner of the resource, OR
# 2. Have a valid delegation chain from the owner

authorized_principal if {
  principal_id := input.user.sub
  owner_id := input.resource.owner_id
  principal_id == owner_id
}

authorized_principal if {
  principal_id := input.user.sub
  owner_id := input.resource.owner_id
  principal_id != owner_id
  # Find a valid delegation chain from owner to principal (supports up to 2-hop chains)
  valid_delegation_path(owner_id, principal_id)
}

# Check for valid delegation paths (supports direct and 2-hop chains)
# Direct delegation: owner -> principal
valid_delegation_path(start_id, end_id) if {
  delegation := input.delegations[_]
  delegation.principal_id == start_id
  delegation.delegate_id == end_id
  delegation.revoked_at == null
  not expired(delegation.expires_at)
  workflow_scoped_match(delegation.workflow_id)
}

# 2-hop delegation: owner -> intermediate -> principal
valid_delegation_path(start_id, end_id) if {
  # First hop: owner -> intermediate
  delegation1 := input.delegations[_]
  delegation1.principal_id == start_id
  intermediate := delegation1.delegate_id
  delegation1.revoked_at == null
  not expired(delegation1.expires_at)
  workflow_scoped_match(delegation1.workflow_id)
  
  # Second hop: intermediate -> principal
  delegation2 := input.delegations[_]
  delegation2.principal_id == intermediate
  delegation2.delegate_id == end_id
  delegation2.revoked_at == null
  not expired(delegation2.expires_at)
  workflow_scoped_match(delegation2.workflow_id)
}

# Check if delegation is expired
expired(expires_at_str) if {
  now := time.now_ns()
  expires_at := time.parse_rfc3339_ns(expires_at_str)
  expires_at < now
}

# Check if delegation workflow_id matches the resource workflow_id (or is null for general delegation)
# A null workflow_id in delegation means it applies to all workflows (general delegation)
workflow_scoped_match(delegation_workflow_id) if {
  delegation_workflow_id == null
}

workflow_scoped_match(delegation_workflow_id) if {
  delegation_workflow_id != null
  resource_workflow_id := input.resource.workflow_id
  resource_workflow_id != null
  delegation_workflow_id == resource_workflow_id
}

# Also match if delegation has workflow_id but resource doesn't (edge case)
workflow_scoped_match(delegation_workflow_id) if {
  delegation_workflow_id != null
  not input.resource.workflow_id
}

# Consent can be derived from:
# - normalized boolean provided by API: input.user.autobook_consent
# - or from Keycloak claim in input.user.claims.autobook_consent (string like "Yes")

has_consent if {
  input.user.autobook_consent == true
}

has_consent if {
  not input.user.autobook_consent
  consent_from_claims == true
}

consent_from_claims := true if {
  consent_str := sprintf("%v", [input.user.claims.autobook_consent])
  lower(trim(consent_str, " ")) == "yes"
}

consent_from_claims := true if {
  consent_str := sprintf("%v", [input.user.claims.autobook_consent])
  lower(trim(consent_str, " ")) == "true"
}

consent_from_claims := true if {
  sprintf("%v", [input.user.claims.autobook_consent]) == "1"
}

# Default to false if claim exists but doesn't match any true condition
# (no need to explicitly set false - it defaults to undefined/false)

# Cost gate
within_cost_limit if {
  planned_price := to_number(input.resource.planned_price)
  max_cost := to_number(input.user.autobook_price)
  planned_price <= max_cost
}

# Advance notice gate (checks if departure is at least autobook_leadtime days in the future)
sufficient_advance if {
  departure_date_str := sprintf("%v", [input.resource.departure_date])
  # Normalize departure date to RFC3339 format
  normalized_departure := normalize_departure_date(departure_date_str)
  departure := time.parse_rfc3339_ns(normalized_departure)
  now := time.now_ns()
  min_days := to_number(input.user.autobook_leadtime)
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
  max_risk := to_number(input.user.autobook_risklevel)
  risk <= max_risk
}