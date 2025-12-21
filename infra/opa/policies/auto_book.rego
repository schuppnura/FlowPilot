package auto_book

# Auto-Book Policy for FlowPilot
#
# This policy implements ABAC (Attribute-Based Access Control) conditions
# for autonomous booking by AI agents. It evaluates four conditions:
# 1. User consent for auto-booking
# 2. Total trip cost within limit
# 3. Sufficient advance notice for departure
# 4. Airline risk score within threshold


default allow := false

# Main allow rule: all gates must pass
allow if {
  has_consent
  within_cost_limit
  sufficient_advance
  acceptable_risk
}

# Reason codes returned as a set
reasons[code] if {
  code := "auto_book.no_consent"
  not has_consent
}

reasons[code] if {
  code := "auto_book.cost_limit_exceeded"
  has_consent
  not within_cost_limit
}

reasons[code] if {
  code := "auto_book.insufficient_advance_notice"
  has_consent
  within_cost_limit
  not sufficient_advance
}

reasons[code] if {
  code := "auto_book.airline_risk_too_high"
  has_consent
  within_cost_limit
  sufficient_advance
  not acceptable_risk
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