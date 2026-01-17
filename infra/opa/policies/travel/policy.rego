package auto_book

# Travel Booking Policy for FlowPilot
#
# This policy implements ABAC (Attribute-Based Access Control) conditions
# for autonomous booking by AI agents and read-only access for invited users.
#
# Policy-specific attributes (from persona via manifest):
# - consent: General authorization consent (applies across use cases)
# - autobook_price: Maximum trip cost for autonomous booking
# - autobook_leadtime: Minimum days before departure for autonomous booking
# - autobook_risklevel: Maximum airline risk score for autonomous booking
#
# Supported actions:
# - "execute": Execute workflow items (requires delegation, consent, cost/lead time checks)
# - "read": View workflows (requires delegation and matching persona)
#
# Execute conditions:
# 1. Anti-spoofing check (principal_id matches owner_id OR delegation is valid)
# 2. Valid delegation (if principal_id != owner_id)
# 3. Persona check (delegated users must have "travel-agent", owners must match owner persona)
# 4. User consent for autonomous operations
# 5. Airline risk score within threshold
# 6. Total trip cost within limit
# 7. Sufficient advance notice for departure
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
  appropriate_persona  # Persona check (delegated users must be travel-agent, owners must match)
  valid_persona  # Persona must be active and within valid time range
  has_consent
  acceptable_risk
  within_cost_limit
  sufficient_advance
}

reasons[code] if {
  input.action.name == "execute"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  # No delegation exists at all
  not input.context.delegation.valid
  code := "auto_book.principal_spoofing"
}

reasons[code] if {
  input.action.name == "execute"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  # Delegation exists but doesn't have execute permission
  input.context.delegation.valid == true
  not input.action.name in input.context.delegation.delegated_actions
  code := "auto_book.insufficient_delegation_permissions"
}

reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.persona_mismatch"
  authorized_principal
  not appropriate_persona
}

reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.persona_invalid"
  authorized_principal
  appropriate_persona
  not valid_persona
}

reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.no_consent"
  authorized_principal
  not has_consent
}

reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.airline_risk_too_high"
  authorized_principal
  has_consent
  not acceptable_risk
}

reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.cost_limit_exceeded"
  authorized_principal
  has_consent
  acceptable_risk
  not within_cost_limit
}

reasons[code] if {
  input.action.name == "execute"
  code := "auto_book.insufficient_advance_notice"
  authorized_principal
  has_consent
  acceptable_risk
  within_cost_limit
  not sufficient_advance
}

reasons[code] if {
  input.action.name == "read"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  input.subject.persona != "ai-agent"
  not input.context.delegation.valid
  code := "read.no_delegation"
}

reasons[code] if {
  input.action.name == "read"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  # Delegation exists but doesn't have read permission
  input.context.delegation.valid == true
  not input.action.name in input.context.delegation.delegated_actions
  code := "read.insufficient_delegation_permissions"
}

reasons[code] if {
  input.action.name == "read"
  not allow_read
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  input.context.delegation.valid
  input.action.name in input.context.delegation.delegated_actions
  not read_persona_valid
  code := "read.persona_mismatch"
}

# Anti-spoofing and delegation check
# The principal must be authorized to perform the action:
# 1. Regular user is the owner themselves, OR
# 2. Agent-runner activated by owner, OR
# 3. Agent-runner in autonomous mode (autobook_consent + no delegation), OR
# 4. Valid delegation with required action permissions

# Owner directly accessing their own resource (regular user, not agent-runner)
authorized_principal if {
  input.subject.persona != "ai-agent"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
}

# Agent-runner activated by the owner (owner using agent to execute)
authorized_principal if {
  input.subject.persona == "ai-agent"
  principal_id := input.context.principal.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
}

# Agent-runner in autonomous mode: consent=true, no delegation chain
# This is pure autobook: owner has opted in and agent acts autonomously
authorized_principal if {
  input.subject.persona == "ai-agent"
  input.resource.properties.owner.consent == true
  not input.context.delegation.valid
}

# Valid delegation: any subject (regular user or agent-runner) with delegation
authorized_principal if {
  has_valid_delegation_for_action
}

# Helper: Check if delegation exists with required action
# OPA makes the policy decision by checking if the requested action
# is present in the delegated_actions returned by delegation-api
has_valid_delegation_for_action if {
  input.context.delegation.valid == true
  input.action.name in input.context.delegation.delegated_actions
}

# Persona validation
# When a user is delegated to execute a workflow (principal != owner):
#   - The principal must have one of the authorized agent personas from persona_config
# When a user executes their own workflow (principal == owner):
#   - The principal must have selected the same persona as the owner's persona
# Configuration Note:
#   - Persona configuration is loaded from persona_config.json data file

# Import persona configuration from data file
import data.travel.persona_config

# Build set of valid agent personas for execute action (includes ai-agent)
valid_agent_personas := agent_personas_with_ai_agent

agent_personas_with_ai_agent contains persona if {
  persona := persona_config.delegation_personas.execute[_]
}

agent_personas_with_ai_agent contains "ai-agent"

# AI-agent activated by delegated user: check context.principal has agent persona
appropriate_persona if {
  input.subject.persona == "ai-agent"
  principal_id := input.context.principal.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  principal_persona := input.context.principal.persona
  principal_persona != ""
  valid_agent_personas[principal_persona]
}

# AI-agent activated by owner: check context.principal matches owner persona
appropriate_persona if {
  input.subject.persona == "ai-agent"
  principal_id := input.context.principal.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
  owner_persona := input.resource.properties.owner.persona
  principal_persona := input.context.principal.persona
  principal_persona == owner_persona
  # Trust source: owner_persona from persona-api is always valid
  principal_persona != ""  # Principal persona from request must be set
}

# Human user with delegation: check subject persona
appropriate_persona if {
  input.subject.persona != "ai-agent"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  input.subject.persona != ""
  valid_agent_personas[input.subject.persona]
}

# Owner executing their own workflow directly: must match owner persona
appropriate_persona if {
  input.subject.persona != "ai-agent"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
  owner_persona := input.resource.properties.owner.persona
  input.subject.persona == owner_persona
  # Trust source: owner_persona from persona-api is always valid
  input.subject.persona != ""  # Subject persona from request must be set
}

# Allow read if user is the owner
allow_read if {
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
}

# AI-Agent needs to read workflows to determine which items can be executed
allow_read if {
  input.subject.persona == "ai-agent"
}

# Allow read if user has valid delegation (with read action) and matching persona
allow_read if {
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  input.context.delegation.valid == true
  input.action.name in input.context.delegation.delegated_actions  # Delegation permits read
  read_persona_valid
}

# Persona validation for read: agent personas OR matching owner persona
read_persona_valid if {
  # Agent personas can always read (if they have delegation)
  input.subject.persona != ""
  valid_agent_personas[input.subject.persona]
}

# User with matching owner persona can read
read_persona_valid if {
  owner_persona := input.resource.properties.owner.persona
  input.subject.persona == owner_persona
  # Trust source: owner_persona from persona-api is always valid
  input.subject.persona != ""  # Subject persona from request must be set
}

# Consent check - consent attribute from resource owner persona
has_consent if {
  input.resource.properties.owner.consent == true
}

# Cost gate - autobook settings belong to the resource owner (in resource.properties.owner)
within_cost_limit if {
  planned_price := input.resource.properties.planned_price
  max_cost := input.resource.properties.owner.autobook_price
  planned_price <= max_cost
}

# Advance notice gate (checks if departure is at least autobook_leadtime days in the future)
sufficient_advance if {
  departure_date_str := input.resource.properties.departure_date
  departure := time.parse_rfc3339_ns(departure_date_str)
  now := time.now_ns()
  min_days := input.resource.properties.owner.autobook_leadtime
  delta_days := (departure - now) / 1000000000 / 60 / 60 / 24
  delta_days >= min_days
}

# Airline risk gate; if no score provided (field doesn't exist), skip the check
acceptable_risk if {
  not "airline_risk_score" in object.keys(input.resource.properties)
}

# If airline_risk_score exists (including 0), check it's within limits
acceptable_risk if {
  "airline_risk_score" in object.keys(input.resource.properties)
  risk := input.resource.properties.airline_risk_score
  max_risk := input.resource.properties.owner.autobook_risklevel
  risk <= max_risk
}

# Persona validity check - owner's persona must be active and within valid time range
# This combines status check (must be "active") and temporal check (valid_from/valid_till)
# Trust source system: persona-api ensures attributes are present, authz-api coerces types
valid_persona if {
  # Persona status must be "active"
  input.resource.properties.owner.persona_status == "active"
  
  # Parse persona validity timestamps (trust they are valid ISO 8601)
  valid_from := time.parse_rfc3339_ns(input.resource.properties.owner.persona_valid_from)
  valid_till := time.parse_rfc3339_ns(input.resource.properties.owner.persona_valid_till)
  now := time.now_ns()
  
  # Current time must be within valid range
  now >= valid_from
  now <= valid_till
}
