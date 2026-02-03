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
# - "update": Update workflow items (same requirements as execute)
# - "delete": Delete workflow items (same requirements as execute)
# - "read": View workflows (requires delegation and matching persona)
# - "validate_persona": Validate persona status and validity (no workflow required)
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
# First check: persona must have the requested action in their allowed-actions
allow if {
  input.action.name == "create"
  allow_create
}

allow if {
  input.action.name == "execute"
  allow_execute
}

allow if {
  input.action.name == "read"
  allow_read
}

allow if {
  input.action.name == "update"
  allow_update
}

allow if {
  input.action.name == "delete"
  allow_delete
}

allow if {
  input.action.name == "validate_persona"
  allow_validate_persona
}

# Create action: check allowed-actions, authorization, and persona validity
allow_create if {
  action_allowed_for_persona  # Persona must have 'create' in allowed-actions
  authorized_principal  # Must be owner (no delegation for create)
  appropriate_persona_for_action  # Must use correct persona
  valid_persona  # Persona must be active and within valid time range
}

# Execute action: all gates must pass
allow_execute if {
  action_allowed_for_persona  # Persona must have 'execute' in allowed-actions
  authorized_principal  # Has delegation chain with execute action OR is owner
  appropriate_persona_for_action  # Uses appropriate persona for the action type
  valid_persona  # Persona must be active and within valid time range
  has_consent
  acceptable_risk
  within_cost_limit
  sufficient_advance
}

# Update action: same rules as execute
allow_update if {
  action_allowed_for_persona
  authorized_principal
  appropriate_persona_for_action
  valid_persona
  has_consent
  acceptable_risk
  within_cost_limit
  sufficient_advance
}

# Delete action: same rules as execute
allow_delete if {
  action_allowed_for_persona
  authorized_principal
  appropriate_persona_for_action
  valid_persona
  has_consent
  acceptable_risk
  within_cost_limit
  sufficient_advance
}

# Validate persona action: check if persona is valid (status=active, within time range)
# This is used by the web-app to warn users about invalid personas
# No workflow/resource required - only validates persona attributes in context.principal
allow_validate_persona if {
  # Persona must be active and within valid time range
  # Note: authz-api guarantees persona_title is non-empty
  valid_persona
}

# Reason codes for create, execute, update, and delete
reasons[code] if {
  input.action.name in ["create", "execute", "update", "delete"]
  not action_allowed_for_persona
  code := "auto_book.action_not_allowed_for_persona"
}

reasons[code] if {
  input.action.name in ["create", "execute", "update", "delete"]
  action_allowed_for_persona
  not authorized_principal
  code := "auto_book.unauthorized_principal"
}

reasons[code] if {
  input.action.name in ["create", "execute", "update", "delete"]
  code := "auto_book.persona_mismatch"
  action_allowed_for_persona
  authorized_principal
  not appropriate_persona_for_action
}

reasons[code] if {
  input.action.name in ["create", "execute", "update", "delete"]
  code := "auto_book.persona_invalid"
  action_allowed_for_persona
  authorized_principal
  appropriate_persona_for_action
  not valid_persona
}

reasons[code] if {
  input.action.name in ["execute", "update", "delete"]
  code := "auto_book.no_consent"
  authorized_principal
  not has_consent
}

reasons[code] if {
  input.action.name in ["execute", "update", "delete"]
  code := "auto_book.airline_risk_too_high"
  authorized_principal
  has_consent
  not acceptable_risk
}

reasons[code] if {
  input.action.name in ["execute", "update", "delete"]
  code := "auto_book.cost_limit_exceeded"
  authorized_principal
  has_consent
  acceptable_risk
  not within_cost_limit
}

reasons[code] if {
  input.action.name in ["execute", "update", "delete"]
  code := "auto_book.insufficient_advance_notice"
  authorized_principal
  has_consent
  acceptable_risk
  within_cost_limit
  not sufficient_advance
}

reasons[code] if {
  input.action.name == "read"
  input.context.principal.id != input.resource.properties.owner.id
  not input.action.name in input.context.delegation.delegated_actions
  code := "read.no_read_delegation"
}

reasons[code] if {
  input.action.name == "validate_persona"
  not valid_persona
  code := "validate_persona.persona_invalid"
}


# Anti-spoofing and delegation check
# The principal must be authorized to perform the action:
# 1. Principal is the owner (covers both direct access and owner using agent), OR
# 2. Valid delegation with required action permissions
# 3. For create actions, any authenticated principal is authorized (no delegation needed)

authorized_principal if {
  # For create actions, there's no existing resource/owner
  # Any authenticated principal (user with valid token) can attempt to create
  # Note: authz-api guarantees principal.id is non-empty
  input.action.name == "create"
}

authorized_principal if {
  # Owner accessing their own resource (directly or via agent)
  input.context.principal.id == input.resource.properties.owner.id
}

authorized_principal if {
  # Valid delegation: any subject (regular user or agent-runner) with delegation
  # If the action is in delegated_actions, a delegation path must exist
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
# Note: OPA loads persona_config.json fields into data.travel namespace directly
import data.travel.delegation_personas
import data.travel.persona_titles

# Check appropriateness of the persona selected by the principal

valid_delegation_personas_for_action contains persona if {
  # Delegation personas can execute/update/delete on behalf of owner
  action := input.action.name
  action in ["execute", "update", "delete"]
  persona := delegation_personas[action][_]
}

valid_delegation_personas_for_action contains persona if {
  # Service personas are always valid for execute/update/delete actions
  # Both 'ai-agent' and 'domain-services' are treated as equivalent service personas
  action := input.action.name
  action in ["execute", "update", "delete"]
  persona := {"ai-agent", "domain-services"}[_]
}

appropriate_persona_for_action if {
  # For create actions, there's no existing resource/owner to compare against
  # Note: authz-api guarantees persona_title is non-empty
  input.action.name == "create"
}

appropriate_persona_for_action if {
  # If acting on behalf of someone else (via delegation), must use a delegation persona
  input.context.principal.id != input.resource.properties.owner.id
  valid_delegation_personas_for_action[input.context.principal.persona_title]
}

appropriate_persona_for_action if {
  # If acting as owner, must use the same persona (title + circle)
  input.context.principal.id == input.resource.properties.owner.id
  input.context.principal.persona_title == input.resource.properties.owner.persona_title
  input.context.principal.persona_circle == input.resource.properties.owner.persona_circle
}

# Read access: check allowed-actions and delegation
allow_read if {
  action_allowed_for_persona  # Persona must have 'read' in allowed-actions
  # Owner can always read their own workflows
  input.context.principal.id == input.resource.properties.owner.id
}

allow_read if {
  action_allowed_for_persona  # Persona must have 'read' in allowed-actions
  # Anyone with a delegation chain containing 'read' action can read
  input.context.principal.id != input.resource.properties.owner.id
  input.action.name in input.context.delegation.delegated_actions
}

# Consent check - consent attribute from resource owner persona
has_consent if {
  input.resource.properties.owner.consent == true
}

# Cost gate - autobook settings belong to the resource owner (in resource.properties.owner)
# If planned_price is missing (workflow-level check), skip this gate (pass)
within_cost_limit if {
  # If no planned_price exists, skip check (workflow-level authorization)
  not "planned_price" in object.keys(input.resource.properties)
}

within_cost_limit if {
  # If planned_price exists (item-level authorization), check it's within limits
  "planned_price" in object.keys(input.resource.properties)
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
  # If no airline_risk_score exists, ignore this check
  not "airline_risk_score" in object.keys(input.resource.properties)
}

acceptable_risk if {
  # If airline_risk_score exists (including 0), check it's within limits
  "airline_risk_score" in object.keys(input.resource.properties)
  risk := input.resource.properties.airline_risk_score
  max_risk := input.resource.properties.owner.autobook_risklevel
  risk <= max_risk
}

# Allowed-actions check - ensures the requested action is in the persona's allowed-actions
# This is the CRUDX enforcement mechanism based on persona_config in manifest.yaml
action_allowed_for_persona if {
  # Find the persona configuration by title
  some persona in persona_titles
  persona.title == input.context.principal.persona_title
  
  # Check if requested action is in the persona's allowed-actions
  input.action.name in persona["allowed-actions"]
}

# Persona validity check - ensures the acting principal's persona is active and within valid time range
# Principal persona metadata is ALWAYS in context.principal (for both owner and delegate scenarios)
# Trust source system: persona-api ensures attributes are present, authz-api coerces types
valid_persona if {
  # Principal's persona status must be "active"
  input.context.principal.persona_status == "active"
  
  # Parse principal's persona validity timestamps (trust they are valid ISO 8601)
  valid_from := time.parse_rfc3339_ns(input.context.principal.persona_valid_from)
  valid_till := time.parse_rfc3339_ns(input.context.principal.persona_valid_till)
  now := time.now_ns()
  
  # Current time must be within valid range
  now >= valid_from
  now <= valid_till
}
