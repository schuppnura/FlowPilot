package flowpilot.auto_book

# Auto-Book Policy for FlowPilot
# 
# This policy implements ABAC (Attribute-Based Access Control) conditions
# for autonomous booking by AI agents. It evaluates four conditions:
# 1. User consent for auto-booking
# 2. Total trip cost within limit
# 3. Sufficient advance notice for departure
# 4. Airline risk score within threshold
#
# Input structure:
# {
#   "user": {
#     "auto_book_consent": bool,
#     "auto_book_max_cost_eur": number,
#     "auto_book_min_days_advance": number,
#     "auto_book_max_airline_risk": number
#   },
#   "resource": {
#     "planned_price": number,      # total trip cost in EUR
#     "departure_date": string,     # ISO date format YYYY-MM-DD
#     "airline_risk_score": number  # 0-10 scale
#   }
# }

import future.keywords.if
import future.keywords.in

# Default deny
default allow := false
default reason := "auto_book.unknown_error"

# Main allow rule - all conditions must be true
allow if {
    has_consent
    within_cost_limit
    sufficient_advance
    acceptable_risk
}

# Condition 1: User consent
has_consent if {
    input.user.auto_book_consent == true
}

# Condition 2: Cost limit
within_cost_limit if {
    input.user.auto_book_max_cost_eur > 0
    input.resource.planned_price <= input.user.auto_book_max_cost_eur
}

# Condition 3: Departure advance (days)
sufficient_advance if {
    input.user.auto_book_min_days_advance >= 0
    days_until_departure >= input.user.auto_book_min_days_advance
}

# Condition 4: Airline risk score
acceptable_risk if {
    # Check if airline_risk_score exists
    input.resource.airline_risk_score != null
    input.resource.airline_risk_score < input.user.auto_book_max_airline_risk
}

# Helper: Calculate days until departure
days_until_departure := days if {
    # Parse departure date
    departure_ns := time.parse_rfc3339_ns(sprintf("%sT00:00:00Z", [input.resource.departure_date]))
    now_ns := time.now_ns()
    
    # Calculate difference in days
    diff_ns := departure_ns - now_ns
    days := diff_ns / (24 * 60 * 60 * 1000000000)
}

# Reason code determination
reason := "auto_book.consent_missing" if {
    not has_consent
}

reason := "auto_book.cost_exceeds_limit" if {
    has_consent
    not within_cost_limit
}

reason := "auto_book.insufficient_advance" if {
    has_consent
    within_cost_limit
    not sufficient_advance
}

reason := "auto_book.airline_risk_too_high" if {
    has_consent
    within_cost_limit
    sufficient_advance
    not acceptable_risk
}

# If no airline_risk_score provided, skip that check
acceptable_risk if {
    not input.resource.airline_risk_score
}
