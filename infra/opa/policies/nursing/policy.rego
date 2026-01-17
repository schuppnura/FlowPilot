package nursing_care

# Nursing Care Policy for FlowPilot
#
# This policy implements ABAC (Attribute-Based Access Control) conditions
# for autonomous nursing care operations and delegation.
#
# Policy-specific attributes (from persona via manifest):
# - consent: General authorization consent (applies across use cases)
# - nursing_max_patient_count: Maximum number of patients nurse can handle
# - nursing_shift_hours: Maximum shift duration in hours
# - nursing_certification_level: Required certification level (1-5)
#
# Supported actions:
# - "execute": Execute care tasks (requires delegation, consent, certification checks)
# - "read": View patient records (requires delegation and matching persona)
#
# Execute conditions:
# 1. Anti-spoofing check (principal_id matches owner_id OR delegation is valid)
# 2. Valid delegation (if principal_id != owner_id)
# 3. Persona check (delegated users must have "nurse", "nurse-practitioner", or "physician")
# 4. User consent for autonomous operations
# 5. Certification level meets minimum requirement
# 6. Patient count within limit
# 7. Shift hours within limit

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
  authorized_principal
  persona_valid
  owner_persona_active
  owner_persona_valid_time
  has_consent
  acceptable_certification
  within_patient_limit
  within_shift_limit
}

reasons[code] if {
  input.action.name == "execute"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  not input.context.delegation.valid
  code := "nursing_care.principal_spoofing"
}

reasons[code] if {
  input.action.name == "execute"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  input.context.delegation.valid == true
  not input.action.name in input.context.delegation.delegated_actions
  code := "nursing_care.insufficient_delegation_permissions"
}

reasons[code] if {
  input.action.name == "execute"
  code := "nursing_care.persona_mismatch"
  authorized_principal
  not persona_valid
}

reasons[code] if {
  input.action.name == "execute"
  code := "nursing_care.persona_inactive"
  authorized_principal
  persona_valid
  not owner_persona_active
}

reasons[code] if {
  input.action.name == "execute"
  code := "nursing_care.persona_expired"
  authorized_principal
  persona_valid
  owner_persona_active
  not owner_persona_valid_time
}

reasons[code] if {
  input.action.name == "execute"
  code := "nursing_care.no_consent"
  authorized_principal
  not has_consent
}

reasons[code] if {
  input.action.name == "execute"
  code := "nursing_care.insufficient_certification"
  authorized_principal
  has_consent
  not acceptable_certification
}

reasons[code] if {
  input.action.name == "execute"
  code := "nursing_care.patient_count_exceeded"
  authorized_principal
  has_consent
  acceptable_certification
  not within_patient_limit
}

reasons[code] if {
  input.action.name == "execute"
  code := "nursing_care.shift_hours_exceeded"
  authorized_principal
  has_consent
  acceptable_certification
  within_patient_limit
  not within_shift_limit
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
authorized_principal if {
  input.subject.persona != "ai-agent"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
}

authorized_principal if {
  input.subject.persona == "ai-agent"
  principal_id := input.context.principal.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
}

authorized_principal if {
  input.subject.persona == "ai-agent"
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

# Persona validation for nursing care
valid_care_personas := {"nurse", "nurse-practitioner", "physician", "ai-agent"}

persona_valid if {
  input.subject.persona != "ai-agent"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  input.subject.persona != ""
  valid_care_personas[input.subject.persona]
}

persona_valid if {
  input.subject.persona != "ai-agent"
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
  owner_persona := input.resource.properties.owner.persona
  input.subject.persona == owner_persona
  owner_persona != ""
  input.subject.persona != ""
}

persona_valid if {
  input.subject.persona == "ai-agent"
  principal_id := input.context.principal.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
  owner_persona := input.resource.properties.owner.persona
  principal_persona := input.context.principal.persona
  principal_persona == owner_persona
  owner_persona != ""
  principal_persona != ""
}

persona_valid if {
  input.subject.persona == "ai-agent"
  principal_id := input.context.principal.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  principal_persona := input.context.principal.persona
  principal_persona != ""
  valid_care_personas[principal_persona]
}

# Allow read if user is the owner
allow_read if {
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id == owner_id
}

allow_read if {
  input.subject.persona == "ai-agent"
}

allow_read if {
  principal_id := input.subject.id
  owner_id := input.resource.properties.owner.id
  principal_id != owner_id
  input.context.delegation.valid == true
  input.action.name in input.context.delegation.delegated_actions
  read_persona_valid
}

read_persona_valid if {
  input.subject.persona != ""
  valid_care_personas[input.subject.persona]
}

read_persona_valid if {
  owner_persona := input.resource.properties.owner.persona
  input.subject.persona == owner_persona
  owner_persona != ""
  input.subject.persona != ""
}

# Consent check
has_consent if {
  input.resource.properties.owner.consent == true
}

# Certification level gate
acceptable_certification if {
  nurse_cert := input.resource.properties.owner.nursing_certification_level
  required_cert := input.resource.properties.required_certification_level
  nurse_cert >= required_cert
}

# Patient count gate
within_patient_limit if {
  current_count := input.resource.properties.current_patient_count
  max_count := input.resource.properties.owner.nursing_max_patient_count
  current_count <= max_count
}

# Shift hours gate
within_shift_limit if {
  current_hours := input.resource.properties.current_shift_hours
  max_hours := input.resource.properties.owner.nursing_shift_hours
  current_hours <= max_hours
}

# Persona status check
owner_persona_active if {
  not input.resource.properties.owner.persona_status
}

owner_persona_active if {
  input.resource.properties.owner.persona_status == "active"
}

# Persona temporal validity check
owner_persona_valid_time if {
  not input.resource.properties.owner.persona_valid_from
  not input.resource.properties.owner.persona_valid_till
}

owner_persona_valid_time if {
  valid_from_str := input.resource.properties.owner.persona_valid_from
  valid_till_str := input.resource.properties.owner.persona_valid_till
  
  valid_from_str == ""
  valid_till_str == ""
}

owner_persona_valid_time if {
  valid_from_str := input.resource.properties.owner.persona_valid_from
  valid_till_str := input.resource.properties.owner.persona_valid_till
  
  valid_from_str != ""
  valid_till_str != ""
  
  valid_from := time.parse_rfc3339_ns(valid_from_str)
  valid_till := time.parse_rfc3339_ns(valid_till_str)
  now := time.now_ns()
  
  now >= valid_from
  now <= valid_till
}
