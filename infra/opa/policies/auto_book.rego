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
reasons[code] if {
  code := "auto_book.principal_spoofing"
  not authorized_principal
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
  input.delegation.valid == true
  # Ensure the delegation chain connects owner to principal
  delegation_chain_valid
}

# Validate that the delegation chain connects owner to principal
delegation_chain_valid if {
  principal_id := input.subject.id
  owner_id := input.resource.owner_id
  chain := input.delegation.delegation_chain
  # Chain must start with owner and end with principal
  chain[0] == owner_id
  chain[count(chain) - 1] == principal_id
}

# Consent check - autobook settings belong to the resource owner (in context.owner)
has_consent if {
  input.context.owner.autobook_consent == true
}

# Cost gate - autobook settings belong to the resource owner (in context.owner)
within_cost_limit if {
  planned_price := to_number(input.resource.planned_price)
  max_cost := to_number(input.context.owner.autobook_price)
  planned_price <= max_cost
}

# Advance notice gate (checks if departure is at least autobook_leadtime days in the future)
sufficient_advance if {
  departure_date_str := sprintf("%v", [input.resource.departure_date])
  # Normalize departure date to RFC3339 format
  normalized_departure := normalize_departure_date(departure_date_str)
  departure := time.parse_rfc3339_ns(normalized_departure)
  now := time.now_ns()
  min_days := to_number(input.context.owner.autobook_leadtime)
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
  max_risk := to_number(input.context.owner.autobook_risklevel)
  risk <= max_risk
}