package nursing_workflow

# Nursing Workflow Policy for FlowPilot (Daily Care + Discharge)
#
# This policy mirrors the travel auto-book policy structure and extends it for:
# - nursing daily care workflows
# - discharge workflows (admin-heavy, coordination-friendly)
# - family caregiver delegation
#
# Design goals:
# - Keep OPA purely declarative (no data fetching)
# - Enforce clear anti-spoofing + delegation semantics
# - Allow bounded autonomy for ai-agent-like execution
# - Support patient involvement and family caregiver administration

default allow := false

# Route by action
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

# Execute action: all gates must pass
allow_execute if {
  authorized_principal
  appropriate_persona
  valid_persona
  has_consent
  within_effort_limit
  sufficient_leadtime
  acceptable_risk
}

# Read action
allow_read if {
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
}

# Service accounts (ai-agent, domain-services) need to read workflows to decide which items to execute
allow_read if {
  service_personas := {"ai-agent", "domain-services"}
  input.subject.persona in service_personas
}

allow_read if {
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  input.context.delegation.valid == true
  input.action.name in input.context.delegation.delegated_actions
  read_persona_valid
}

# Update action: conservative
# - Owner can update their own workflow
# - Delegated users can update if delegation includes update and persona is valid
allow_update if {
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
}

allow_update if {
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  input.context.delegation.valid == true
  input.action.name in input.context.delegation.delegated_actions
  update_persona_valid
}

# Reasons (selected, mirroring travel policy style)
reasons[code] if {
  input.action.name == "execute"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  not input.context.delegation.valid
  code := "nursing.principal_spoofing"
}

reasons[code] if {
  input.action.name == "execute"
  input.context.delegation.valid == true
  not input.action.name in input.context.delegation.delegated_actions
  code := "nursing.insufficient_delegation_permissions"
}

reasons[code] if {
  input.action.name == "execute"
  authorized_principal
  not appropriate_persona
  code := "nursing.persona_mismatch"
}

reasons[code] if {
  input.action.name == "execute"
  authorized_principal
  appropriate_persona
  not valid_persona
  code := "nursing.persona_invalid"
}

reasons[code] if {
  input.action.name == "execute"
  authorized_principal
  not has_consent
  code := "nursing.no_consent"
}

reasons[code] if {
  input.action.name == "execute"
  authorized_principal
  has_consent
  not within_effort_limit
  code := "nursing.effort_limit_exceeded"
}

reasons[code] if {
  input.action.name == "execute"
  authorized_principal
  has_consent
  within_effort_limit
  not sufficient_leadtime
  code := "nursing.insufficient_leadtime"
}

reasons[code] if {
  input.action.name == "execute"
  authorized_principal
  has_consent
  within_effort_limit
  sufficient_leadtime
  not acceptable_risk
  code := "nursing.risk_too_high"
}

# Anti-spoofing and delegation check
# 1. Owner directly (non-service-persona)
# 2. Service persona (ai-agent, domain-services) activated by owner (context.principal == owner)
# 3. Service persona in autonomous mode (consent + no delegation)
# 4. Valid delegation with required action

service_personas := {"ai-agent", "domain-services"}

authorized_principal if {
  not input.subject.persona in service_personas
  input.subject.id == input.resource.properties.owner.id
}

authorized_principal if {
  input.subject.persona in service_personas
  input.context.principal.id == input.resource.properties.owner.id
}

authorized_principal if {
  input.subject.persona in service_personas
  input.resource.properties.owner.consent == true
  not input.context.delegation.valid
}

authorized_principal if {
  has_valid_delegation_for_action
}

has_valid_delegation_for_action if {
  input.context.delegation.valid == true
  input.action.name in input.context.delegation.delegated_actions
}

# Persona configuration
import data.nursing.persona_config

valid_agent_personas := agent_personas_with_ai_agent

agent_personas_with_ai_agent contains persona if {
  persona := persona_config.delegation_personas.execute[_]
}

# Add service personas as valid agent personas (treated equivalently)
agent_personas_with_ai_agent contains "ai-agent"

agent_personas_with_ai_agent contains "domain-services"

# Build set of valid invitation personas for read action
valid_invitation_personas contains persona if {
  persona := persona_config.invitation_personas.read[_]
}

# Appropriate persona checks
# - Delegated execution: actor must have a delegation-capable persona
# - Owner execution: persona must match owner persona
# - Service persona activation: check principal persona semantics

appropriate_persona if {
  input.subject.persona in service_personas
  principal_id := input.context.principal.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  principal_persona := input.context.principal.persona
  principal_persona != ""
  valid_agent_personas[principal_persona]
}

appropriate_persona if {
  input.subject.persona in service_personas
  principal_id := input.context.principal.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
  input.context.principal.persona == input.resource.properties.owner.persona
  input.context.principal.persona != ""
}

appropriate_persona if {
  not input.subject.persona in service_personas
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  input.subject.persona != ""
  valid_agent_personas[input.subject.persona]
}

appropriate_persona if {
  not input.subject.persona in service_personas
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
  input.subject.persona == input.resource.properties.owner.persona
  input.subject.persona != ""
}

# Read persona validation: delegation personas OR invitation personas OR matching owner persona
read_persona_valid if {
  # Delegation personas can always read (if they have delegation)
  input.subject.persona != ""
  valid_agent_personas[input.subject.persona]
}

read_persona_valid if {
  # Invitation personas can read (if they have invitation/delegation)
  input.subject.persona != ""
  valid_invitation_personas[input.subject.persona]
}

read_persona_valid if {
  input.subject.persona == input.resource.properties.owner.persona
  input.subject.persona != ""
}

# Update persona validation
# - Family caregiver can update admin-heavy workflows (not clinical decisions)
# - Nurses and care coordinators can update when delegated
update_persona_valid if {
  input.subject.persona != ""
  valid_agent_personas[input.subject.persona]
}

update_persona_valid if {
  input.subject.persona == input.resource.properties.owner.persona
  input.subject.persona != ""
}

# Consent gate
has_consent if {
  input.resource.properties.owner.consent == true
}

# Effort gate
within_effort_limit if {
  planned_effort := input.resource.properties.planned_effort_minutes
  max_effort := input.resource.properties.owner.auto_execute_effort
  planned_effort <= max_effort
}

# Lead time gate (hours)
sufficient_leadtime if {
  due_str := input.resource.properties.due_datetime
  due := time.parse_rfc3339_ns(due_str)
  now := time.now_ns()
  min_hours := input.resource.properties.owner.auto_execute_leadtime_hours
  delta_hours := (due - now) / 1000000000 / 60 / 60
  delta_hours >= min_hours
}

# Risk gate (skip if absent)
acceptable_risk if {
  not "care_risk_score" in object.keys(input.resource.properties)
}

acceptable_risk if {
  "care_risk_score" in object.keys(input.resource.properties)
  risk := input.resource.properties.care_risk_score
  max_risk := input.resource.properties.owner.auto_execute_risklevel
  risk <= max_risk
}

# Persona validity check
valid_persona if {
  input.resource.properties.owner.persona_status == "active"
  valid_from := time.parse_rfc3339_ns(input.resource.properties.owner.persona_valid_from)
  valid_till := time.parse_rfc3339_ns(input.resource.properties.owner.persona_valid_till)
  now := time.now_ns()
  now >= valid_from
  now <= valid_till
}
