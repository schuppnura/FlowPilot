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
# Not delegated: when a travel agent (with travel-agent persona) tries to access a trip without delegation
reasons[code] if {
  code := "auto_book.not_delegated"
  principal_id := input.user.sub
  owner_id := input.resource.owner_id
  owner_id != null
  principal_id != owner_id
  not valid_delegation_path(owner_id, principal_id)
  principal_persona := input.user.persona
  principal_persona == "travel-agent"
}

# Principal spoofing: when principal != owner AND no valid delegation exists AND principal is NOT a travel agent
# This is distinct from "not delegated" - spoofing specifically means an unauthorized non-travel-agent principal
reasons[code] if {
  code := "auto_book.principal_spoofing"
  principal_id := input.user.sub
  owner_id := input.resource.owner_id
  owner_id != null  # Only check spoofing if there's an owner to compare against
  principal_id != owner_id
  not valid_delegation_path(owner_id, principal_id)
  # Principal is not a travel agent (either persona is not set, empty, or something other than "travel-agent")
  principal_persona := input.user.persona
  principal_persona != "travel-agent"
}

# Also handle case where principal_persona is not set/undefined (backward compatibility)
reasons[code] if {
  code := "auto_book.principal_spoofing"
  principal_id := input.user.sub
  owner_id := input.resource.owner_id
  owner_id != null
  principal_id != owner_id
  not valid_delegation_path(owner_id, principal_id)
  not input.user.persona  # Persona is not set/undefined
}

reasons[code] if {
  code := "auto_book.persona_mismatch"
  principal_id := input.user.sub
  owner_id := input.resource.owner_id
  principal_id == owner_id  # Owner initiated execution
  not personas_match(principal_id, owner_id)
}

reasons[code] if {
  code := "auto_book.delegation_requires_travel_agent_persona"
  principal_id := input.user.sub
  owner_id := input.resource.owner_id
  principal_id != owner_id  # Delegated execution
  valid_delegation_path(owner_id, principal_id)  # Delegation exists
  principal_persona := input.user.persona
  principal_persona != "travel-agent"  # But persona is not travel-agent
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
# 1. Be the owner of the resource AND have matching persona (if owner initiated execution), OR
# 2. Have a valid delegation chain from the owner AND have persona "travel-agent" (delegated execution)

authorized_principal if {
  principal_id := input.user.sub
  owner_id := input.resource.owner_id
  principal_id == owner_id
  # If owner initiated execution (not delegated), personas must match
  personas_match(principal_id, owner_id)
}

authorized_principal if {
  principal_id := input.user.sub
  owner_id := input.resource.owner_id
  principal_id != owner_id
  # Find a valid delegation chain from owner to principal (supports up to 2-hop chains)
  valid_delegation_path(owner_id, principal_id)
  # When executing via delegation, principal's selected persona must be "travel-agent"
  principal_persona := input.user.persona
  principal_persona == "travel-agent"
}

# Check if personas match when principal == owner
# If owner initiated execution (not delegated), the selected persona must match the owner's persona
personas_match(principal_id, owner_id) if {
  principal_id == owner_id
  principal_persona := input.user.persona
  owner_persona := input.resource.owner_persona
  # If both personas are set and non-empty, they must match
  principal_persona != ""
  owner_persona != ""
  principal_persona == owner_persona
}

# Allow if owner persona is not set or empty (backward compatibility)
personas_match(principal_id, owner_id) if {
  principal_id == owner_id
  owner_persona := input.resource.owner_persona
  owner_persona == ""
}

# Allow if principal persona is not set or empty (backward compatibility)
personas_match(principal_id, owner_id) if {
  principal_id == owner_id
  principal_persona := input.user.persona
  principal_persona == ""
}

# Allow if both personas are not set (backward compatibility)
personas_match(principal_id, owner_id) if {
  principal_id == owner_id
  not input.user.persona
  not input.resource.owner_persona
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

# Consent check - assumes input.user.autobook_consent is already coerced to boolean
has_consent if {
  input.user.autobook_consent == true
}

# Cost gate
within_cost_limit if {
  planned_price := to_number(input.resource.planned_price)
  max_cost := to_number(input.user.autobook_price)
  planned_price <= max_cost
}

# Advance notice gate (checks if departure is at least autobook_leadtime days in the future)
# Assumes input.resource.departure_date is already coerced to RFC3339 format
sufficient_advance if {
  departure_date_str := sprintf("%v", [input.resource.departure_date])
  departure := time.parse_rfc3339_ns(departure_date_str)
  now := time.now_ns()
  min_days := to_number(input.user.autobook_leadtime)
  # Calculate days until departure
  delta_days := (departure - now) / 1000000000 / 60 / 60 / 24
  # Departure must be at least min_days in the future
  delta_days >= min_days
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