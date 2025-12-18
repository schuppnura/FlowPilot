# FlowPilot AuthZ API - Core Logic
#
# Authorization service that acts as PDP façade + PIP (enrichment) + adapter to ***REMOVED***.
# This service enriches authorization requests with profile attributes and orchestrates
# authorization checks via ***REMOVED***. It does NOT make authorization decisions itself.
#
# POLICY ARCHITECTURE (for security auditors):
# 
# 1. ReBAC - Relationship-Based Access Control (***REMOVED*** Directory)
#    - Function: evaluate_rebac() → check_***REMOVED***_permission()
#    - Policy Location: infra/***REMOVED***/cfg/flowpilot-manifest.yaml
#    - Evaluates: Workflow-ownership (anti-spoofing)
#                 and Agent delegation via authorization graph traversal
#    - Decision Authority: ***REMOVED*** Directory
#
# 2. ABAC - Attribute-Based Access Control (***REMOVED*** OPA)
#    - Function: evaluate_abac() → call_***REMOVED***_policy()
#    - Policy Location: infra/***REMOVED***/cfg/policies/auto_book.rego
#    - Evaluates: Booking constraints (consent, cost, dates, risk)
#    - Decision Authority: ***REMOVED*** Authorizer (OPA/Rego)
#
# 3. Progressive Profiling (AuthZ API - PIP Enrichment)
#    - Functions: evaluate_progressive_profiling()
#    - Purpose: Validates required identity fields are present
#    - Returns advisory information for UX - NOT an authorization decision
#
# Key responsibilities:
# - PDP façade: orchestrate ***REMOVED*** checks, assemble decision responses
# - PIP: enrich requests with profile attributes, return advisory information
# - Graph writer: maintain workflow ownership relations in ***REMOVED***
# - Profile store: in-memory non-PII policy parameters and identity presence flags
#
# No PII values are stored. Only:
# - presence flags for mandatory user profile attributes (boolean)
# - non-PII policy parameters (e.g. autobook thresholds, numeric limits)
# - pseudononymous workflow relations (UUID references)

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel

from utils import (
    build_timeouts,
    build_url,
    http_get_json,
    http_post_json,
    validate_non_empty_string,
)


class EvaluateResponseModel(BaseModel):
    decision: str
    decision_id: str
    reason_codes: List[str] = []
    advice: List[Dict[str, Any]] = []

    model_config = {"extra": "allow"}


@dataclass(frozen=True)
class Dependencies:
    workflow_base_url: str
    workflow_owner_path_template: str
    workflow_items_path_template: str
    workflow_item_id_property_names: List[str]

    ***REMOVED***_dir_base: str
    ***REMOVED***_check_path: str
    ***REMOVED***_timeouts_connect_read: Tuple[float, float]
    ***REMOVED***_enable_trace_default: bool

    action_relation_map: Dict[str, str]

    required_identity_fields_default: List[str]
    required_identity_fields_by_item_kind: Dict[str, List[str]]

    request_timeout_seconds: int


class InMemoryProfileStore:
    def __init__(self, default_policy_parameters: Optional[Dict[str, Any]] = None) -> None:
        # Store profiles in-memory for the demo
        # why: avoid extra services while keeping progressive profiling
        # side effect: memory use.
        self._lock = threading.Lock()
        self._profiles: Dict[str, Dict[str, Any]] = {}
        self._default_policy_parameters = default_policy_parameters if isinstance(default_policy_parameters, dict) else {}

    def get_profile_count(self) -> int:
        # Return count of profiles stored
        # why: health/debug
        # side effect: none.
        with self._lock:
            return len(self._profiles)

    def get_or_create_profile(self, principal_sub: str) -> Dict[str, Any]:
        # Return profile dict for principal_sub, creating if absent
        # side effect: may create new in-memory record.
        principal_sub = validate_non_empty_string(principal_sub, "principal_sub")
        with self._lock:
            existing = self._profiles.get(principal_sub)
            if isinstance(existing, dict):
                return existing
            profile = {"principal_sub": principal_sub, "parameters": dict(self._default_policy_parameters), "presence": {}}
            self._profiles[principal_sub] = profile
            return profile

    def get_policy_parameters(self, principal_sub: str) -> Dict[str, Any]:
        # Return non-PII policy parameters (preferences)
        # why: policy context
        # side effect: none.
        profile = self.get_or_create_profile(principal_sub)
        parameters = profile.get("parameters", {})
        if not isinstance(parameters, dict):
            return {}
        return dict(parameters)

    def patch_policy_parameters(self, principal_sub: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        # Patch policy parameters by shallow merge
        # why: keep updates simple and predictable
        # side effect: in-memory mutation.
        principal_sub = validate_non_empty_string(principal_sub, "principal_sub")
        if not isinstance(patch, dict):
            raise ValueError("parameters patch must be an object")
        with self._lock:
            profile = self.get_or_create_profile(principal_sub)
            existing = profile.get("parameters", {})
            if not isinstance(existing, dict):
                existing = {}
            merged = dict(existing)
            for key, value in patch.items():
                if isinstance(key, str) and key.strip():
                    merged[key.strip()] = value
            profile["parameters"] = merged
            return dict(merged)

    def get_identity_presence(self, principal_sub: str) -> Dict[str, bool]:
        # Return identity presence flags (no PII values)
        # why: progressive profiling
        # side effect: none.
        profile = self.get_or_create_profile(principal_sub)
        presence = profile.get("presence", {})
        if not isinstance(presence, dict):
            return {}
        normalized: Dict[str, bool] = {}
        for key, value in presence.items():
            if isinstance(key, str) and isinstance(value, bool):
                normalized[key] = value
        return normalized

    def patch_identity_presence(self, principal_sub: str, patch: Dict[str, bool]) -> Dict[str, bool]:
        # Patch identity presence flags
        # why: demo/profile enrichment
        # side effect: in-memory mutation.
        principal_sub = validate_non_empty_string(principal_sub, "principal_sub")
        if not isinstance(patch, dict):
            raise ValueError("presence patch must be an object")
        with self._lock:
            profile = self.get_or_create_profile(principal_sub)
            existing = profile.get("presence", {})
            if not isinstance(existing, dict):
                existing = {}
            merged: Dict[str, bool] = {}
            for key, value in existing.items():
                if isinstance(key, str) and isinstance(value, bool):
                    merged[key] = value
            for key, value in patch.items():
                if isinstance(key, str) and isinstance(value, bool):
                    merged[key] = value
            profile["presence"] = merged
            return dict(merged)

    def get_profile_view(self, principal_sub: str) -> Dict[str, Any]:
        # Return combined profile view
        # why: convenience for demo clients
        # side effect: none.
        principal_sub = validate_non_empty_string(principal_sub, "principal_sub")
        parameters = self.get_policy_parameters(principal_sub)
        presence = self.get_identity_presence(principal_sub)
        return {"principal_sub": principal_sub, "parameters": parameters, "presence": presence}


class AuthzService:
    def __init__(self, config: Dict[str, Any]) -> None:
        # Initialize dependencies and in-memory profile store
        # why: keep web layer thin
        # side effect: none.
        self._config = dict(config)
        self._dependencies = self._create_dependencies(config=self._config)
        
        # Extract default policy parameters from config (e.g., auto-book defaults)
        default_params = {
            "auto_book_consent": config.get("auto_book_consent", False),
            "auto_book_max_cost_eur": config.get("auto_book_max_cost_eur", 1500),
            "auto_book_min_days_advance": config.get("auto_book_min_days_advance", 7),
            "auto_book_max_airline_risk": config.get("auto_book_max_airline_risk", 5),
        }
        self._profiles = InMemoryProfileStore(default_policy_parameters=default_params)

    def get_profile_count(self) -> int:
        # Return number of profiles in-memory
        # why: health/debug
        # side effect: none.
        return self._profiles.get_profile_count()

    def get_policy_parameters(self, principal_sub: str) -> Dict[str, Any]:
        # Get policy parameters for a principal
        # why: used by clients and evaluation
        # side effect: none.
        return self._profiles.get_policy_parameters(principal_sub=principal_sub)

    def patch_policy_parameters(self, principal_sub: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        # Patch policy parameters
        # why: enrich preferences over time
        # side effect: in-memory mutation.
        return self._profiles.patch_policy_parameters(principal_sub=principal_sub, patch=patch)

    def get_identity_presence(self, principal_sub: str) -> Dict[str, bool]:
        # Get identity presence flags
        # why: progressive profiling
        # side effect: none.
        return self._profiles.get_identity_presence(principal_sub=principal_sub)

    def patch_identity_presence(self, principal_sub: str, patch: Dict[str, bool]) -> Dict[str, bool]:
        # Patch identity presence flags
        # why: enrich profile completeness state
        # side effect: in-memory mutation.
        return self._profiles.patch_identity_presence(principal_sub=principal_sub, patch=patch)

    def get_profile(self, principal_sub: str) -> Dict[str, Any]:
        # Return combined profile
        # why: convenience for demo clients
        # side effect: none.
        return self._profiles.get_profile_view(principal_sub=principal_sub)

    def evaluate_request(self, request_model: BaseModel) -> Dict[str, Any]:
        # Evaluate an AuthZEN-like request by applying guardrails, ***REMOVED*** checks, and progressive profiling advice.
        request_body = request_model.model_dump()
        return evaluate_request(
            dependencies=self._dependencies,
            profile_store=self._profiles,
            request_body=request_body,
        )

    def create_workflow_graph(self, workflow_id: str, owner_sub: str, display_name: str, properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Create workflow object and owner relation in ***REMOVED*** authorization graph
        # why: establish workflow ownership for ReBAC authorization checks
        # when: called by domain services when workflows are created (e.g., trip creation)
        # graph structure: workflow --owner--> user
        # assumptions: user object must already exist in ***REMOVED*** (created during provisioning)
        # side effect: creates workflow object and owner relation in ***REMOVED***
        # returns: dict with workflow_id, owner_sub, and status="created"
        workflow_id = validate_non_empty_string(workflow_id, "workflow_id")
        owner_sub = validate_non_empty_string(owner_sub, "owner_sub")
        
        # Create workflow object
        create_***REMOVED***_object(
            dependencies=self._dependencies,
            object_type="workflow",
            object_id=workflow_id,
            display_name=display_name or workflow_id,
            properties=properties,
        )
        
        # Create owner relation: workflow --owner--> user
        create_***REMOVED***_relation(
            dependencies=self._dependencies,
            object_type="workflow",
            object_id=workflow_id,
            relation="owner",
            subject_type="user",
            subject_id=owner_sub,
        )
        
        return {"workflow_id": workflow_id, "owner_sub": owner_sub, "status": "created"}

    def create_workflow_item_graph(self, workflow_item_id: str, workflow_id: str, display_name: str, properties: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        # Create workflow_item object and workflow relation in ***REMOVED*** authorization graph
        # why: link items to workflows for permission inheritance via ReBAC
        # when: called by domain services for each workflow item during workflow creation
        # graph structure: workflow_item --workflow--> workflow
        # assumptions: workflow object must already exist in ***REMOVED***
        # permission chain: workflow_item.can_execute delegates to workflow.can_execute via this relation
        # side effect: creates workflow_item object and workflow relation in ***REMOVED***
        # returns: dict with workflow_item_id, workflow_id, and status="created"
        workflow_item_id = validate_non_empty_string(workflow_item_id, "workflow_item_id")
        workflow_id = validate_non_empty_string(workflow_id, "workflow_id")
        
        # Create workflow_item object
        create_***REMOVED***_object(
            dependencies=self._dependencies,
            object_type="workflow_item",
            object_id=workflow_item_id,
            display_name=display_name or workflow_item_id,
            properties=properties,
        )
        
        # Create workflow relation: workflow_item --workflow--> workflow
        create_***REMOVED***_relation(
            dependencies=self._dependencies,
            object_type="workflow_item",
            object_id=workflow_item_id,
            relation="workflow",
            subject_type="workflow",
            subject_id=workflow_id,
        )
        
        return {"workflow_item_id": workflow_item_id, "workflow_id": workflow_id, "status": "created"}

    def _create_dependencies(self, config: Dict[str, Any]) -> Dependencies:
        # Create a frozen dependency bag
        # why: avoid passing many parameters through layers
        # side effect: none.
        connect_seconds = float(config.get("***REMOVED***_timeout_connect_seconds", 2.0))
        read_seconds = float(config.get("***REMOVED***_timeout_read_seconds", 8.0))

        workflow_item_names = list(config.get("workflow_item_id_property_names", []))
        normalized_item_names: List[str] = []
        for name in workflow_item_names:
            if isinstance(name, str) and name.strip():
                normalized_item_names.append(name.strip())

        action_relation_map = config.get("action_relation_map", {})
        if not isinstance(action_relation_map, dict):
            action_relation_map = {}
        normalized_action_map: Dict[str, str] = {}
        for key, value in action_relation_map.items():
            if isinstance(key, str) and isinstance(value, str) and key.strip() and value.strip():
                normalized_action_map[key.strip()] = value.strip()

        required_default = config.get("required_identity_fields_default", [])
        required_by_kind = config.get("required_identity_fields_by_item_kind", {})
        if not isinstance(required_default, list):
            required_default = []
        if not isinstance(required_by_kind, dict):
            required_by_kind = {}

        normalized_required_default: List[str] = []
        for field in required_default:
            if isinstance(field, str) and field.strip():
                normalized_required_default.append(field.strip())

        normalized_required_by_kind: Dict[str, List[str]] = {}
        for kind, fields in required_by_kind.items():
            if not isinstance(kind, str) or not kind.strip():
                continue
            if not isinstance(fields, list):
                continue
            normalized_fields: List[str] = []
            for field in fields:
                if isinstance(field, str) and field.strip():
                    normalized_fields.append(field.strip())
            normalized_required_by_kind[kind.strip()] = normalized_fields

        return Dependencies(
            workflow_base_url=validate_non_empty_string(config.get("workflow_base_url"), "workflow_base_url"),
            workflow_owner_path_template=validate_non_empty_string(config.get("workflow_owner_path_template"), "workflow_owner_path_template"),
            workflow_items_path_template=validate_non_empty_string(config.get("workflow_items_path_template"), "workflow_items_path_template"),
            workflow_item_id_property_names=normalized_item_names,
            ***REMOVED***_dir_base=validate_non_empty_string(config.get("***REMOVED***_dir_base"), "***REMOVED***_dir_base"),
            ***REMOVED***_check_path=validate_non_empty_string(config.get("***REMOVED***_check_path"), "***REMOVED***_check_path"),
            ***REMOVED***_timeouts_connect_read=(connect_seconds, read_seconds),
            ***REMOVED***_enable_trace_default=bool(config.get("***REMOVED***_trace_default", False)),
            action_relation_map=normalized_action_map,
            required_identity_fields_default=normalized_required_default,
            required_identity_fields_by_item_kind=normalized_required_by_kind,
            request_timeout_seconds=int(config.get("request_timeout_seconds", 10)),
        )


def evaluate_request(
    dependencies: Dependencies,
    profile_store: InMemoryProfileStore,
    request_body: Dict[str, Any],
) -> Dict[str, Any]:
    # Orchestrate authorization evaluation through layered checks
    # Layer 1: Anti-spoofing (PEP guardrail)
    # Layer 2: ReBAC - ***REMOVED*** Directory (relationship-based)
    # Layer 3: ABAC - ***REMOVED*** OPA (attribute-based, if action=auto-book)
    # Layer 4: Progressive profiling (PIP enrichment)
    decision_id = str(uuid.uuid4())

    subject = request_body.get("subject", {})
    action = request_body.get("action", {})
    resource = request_body.get("resource", {})
    context = request_body.get("context", {})
    options = request_body.get("options", {})

    actor_type = validate_non_empty_string(subject.get("type"), "subject.type")
    actor_id = validate_non_empty_string(subject.get("id"), "subject.id")
    action_name = validate_non_empty_string(action.get("name"), "action.name")

    workflow_id = validate_non_empty_string(resource.get("id"), "resource.id")
    workflow_item_id = extract_workflow_item_id(resource, dependencies.workflow_item_id_property_names)
    workflow_item_kind = extract_workflow_item_kind(resource)

    principal_sub = extract_principal_sub(context)

    dry_run = bool(options.get("dry_run", True))
    explain = bool(options.get("explain", True))
    trace_option = options.get("trace")

    # Layer 1: Anti-spoofing guardrail (***REMOVED***-based ownership check)
    # Check that the principal actually owns the workflow
    ownership_result = evaluate_ownership(
        dependencies=dependencies,
        workflow_id=workflow_id,
        principal_sub=principal_sub,
        trace_option=trace_option,
        explain=explain,
        decision_id=decision_id,
    )
    if ownership_result is not None:
        return ownership_result

    # Layer 2: ReBAC check (***REMOVED*** Directory) - Agent delegation
    # Check that the agent is delegated by the workflow owner
    rebac_result = evaluate_rebac(
        dependencies=dependencies,
        actor_type=actor_type,
        actor_id=actor_id,
        action_name=action_name,
        workflow_item_id=workflow_item_id,
        trace_option=trace_option,
        explain=explain,
        decision_id=decision_id,
    )
    if rebac_result is not None:
        return rebac_result

    # Layer 3: ABAC check (***REMOVED*** OPA, only for auto-book)
    if action_name == "auto-book":
        abac_result = evaluate_abac(
            dependencies=dependencies,
            profile_store=profile_store,
            principal_sub=principal_sub,
            resource=resource,
            action_name=action_name,
            explain=explain,
            decision_id=decision_id,
        )
        if abac_result is not None:
            return abac_result

    # Layer 4: Progressive profiling enrichment
    return evaluate_progressive_profiling(
        dependencies=dependencies,
        profile_store=profile_store,
        principal_sub=principal_sub,
        workflow_id=workflow_id,
        workflow_item_id=workflow_item_id,
        workflow_item_kind=workflow_item_kind,
        dry_run=dry_run,
        explain=explain,
        decision_id=decision_id,
    )


def evaluate_ownership(
    dependencies: Dependencies,
    workflow_id: str,
    principal_sub: str,
    trace_option: Any,
    explain: bool,
    decision_id: str,
) -> Optional[Dict[str, Any]]:
    # LAYER 1: Anti-spoofing via ***REMOVED*** ownership check
    # 
    # SECURITY GUARDRAIL: Verify the principal owns the workflow using ***REMOVED*** graph.
    # This prevents principal spoofing attacks where an attacker supplies a different user's ID.
    # 
    # AUDIT NOTE: Authorization decision made by ***REMOVED*** Directory based on ownership relation.
    # No external API calls needed - ownership is already in the authorization graph.
    # 
    # Checks: workflow --owner--> user (where user.id == principal_sub)
    # 
    # Returns deny decision if principal doesn't own workflow, None if they do.
    
    # Check if this principal is the owner of the workflow
    is_owner = check_***REMOVED***_permission(
        dependencies=dependencies,
        subject_type="user",
        subject_id=principal_sub,
        object_type="workflow",
        object_id=workflow_id,
        relation="is_owner",
        trace=trace_option if isinstance(trace_option, bool) else None,
    )
    
    if not is_owner:
        advice: List[Dict[str, Any]] = [
            {
                "kind": "security",
                "code": "principal_spoof",
                "message": "Principal does not own the workflow. Rejecting request to prevent principal spoofing.",
            }
        ]
        if explain:
            advice.append(
                {
                    "kind": "debug",
                    "code": "***REMOVED***.ownership_check",
                    "message": "***REMOVED*** ownership check returned deny.",
                    "details": {
                        "subject_type": "user",
                        "subject_id": principal_sub,
                        "object_type": "workflow",
                        "object_id": workflow_id,
                        "relation": "is_owner",
                    },
                }
            )
        return {
            "decision": "deny",
            "decision_id": decision_id,
            "reason_codes": ["security.principal_spoof"],
            "advice": advice,
        }
    
    return None


def evaluate_rebac(
    dependencies: Dependencies,
    actor_type: str,
    actor_id: str,
    action_name: str,
    workflow_item_id: str,
    trace_option: Any,
    explain: bool,
    decision_id: str,
) -> Optional[Dict[str, Any]]:
    # LAYER 2: ReBAC check via ***REMOVED*** Directory
    # Returns deny decision if ***REMOVED*** denies, None if allowed
    relation = map_action_to_relation(dependencies=dependencies, action_name=action_name)
    allowed = check_***REMOVED***_permission(
        dependencies=dependencies,
        subject_type=actor_type,
        subject_id=actor_id,
        object_type="workflow_item",
        object_id=workflow_item_id,
        relation=relation,
        trace=trace_option if isinstance(trace_option, bool) else None,
    )

    if not allowed:
        advice: List[Dict[str, Any]] = []
        if explain:
            advice.append(
                {
                    "kind": "debug",
                    "code": "***REMOVED***.check",
                    "message": "***REMOVED*** directory check returned deny.",
                    "details": {
                        "subject_type": actor_type,
                        "subject_id": actor_id,
                        "object_type": "workflow_item",
                        "object_id": workflow_item_id,
                        "relation": relation,
                    },
                }
            )
        return {"decision": "deny", "decision_id": decision_id, "reason_codes": ["***REMOVED***.deny"], "advice": advice}
    
    return None


def evaluate_abac(
    dependencies: Dependencies,
    profile_store: InMemoryProfileStore,
    principal_sub: str,
    resource: Dict[str, Any],
    action_name: str,
    explain: bool,
    decision_id: str,
) -> Optional[Dict[str, Any]]:
    # LAYER 3: ABAC check via ***REMOVED*** OPA (for auto-book action)
    # Returns deny decision if policy denies, None if allowed
    policy_parameters = profile_store.get_policy_parameters(principal_sub=principal_sub)
    resource_properties = resource.get("properties", {})
    if not isinstance(resource_properties, dict):
        resource_properties = {}
    
    # Build policy input for ***REMOVED*** OPA evaluation
    policy_input = {
        "user": policy_parameters,
        "resource": resource_properties,
    }
    
    # Call ***REMOVED*** policy evaluation
    try:
        policy_result = call_***REMOVED***_policy(
            dependencies=dependencies,
            policy_path="flowpilot.auto_book",
            policy_input=policy_input,
        )
        
        if not policy_result.get("allow", False):
            auto_book_deny_reason = policy_result.get("reason", "auto_book.unknown_error")
            advice_list: List[Dict[str, Any]] = []
            if explain:
                advice_list.append(
                    {
                        "kind": "policy",
                        "code": auto_book_deny_reason,
                        "message": f"Auto-book policy condition not met: {auto_book_deny_reason}",
                        "details": {
                            "action": action_name,
                            "policy_parameters": policy_parameters,
                            "evaluated_by": "***REMOVED***_opa",
                        },
                    }
                )
            return {"decision": "deny", "decision_id": decision_id, "reason_codes": [auto_book_deny_reason], "advice": advice_list}
    except Exception as policy_error:
        # Fallback to deny on policy evaluation error
        advice_list_err: List[Dict[str, Any]] = []
        if explain:
            advice_list_err.append(
                {
                    "kind": "error",
                    "code": "policy.evaluation_error",
                    "message": f"Failed to evaluate auto-book policy: {str(policy_error)}",
                }
            )
        return {"decision": "deny", "decision_id": decision_id, "reason_codes": ["policy.evaluation_error"], "advice": advice_list_err}
    
    return None


def evaluate_progressive_profiling(
    dependencies: Dependencies,
    profile_store: InMemoryProfileStore,
    principal_sub: str,
    workflow_id: str,
    workflow_item_id: str,
    workflow_item_kind: str,
    dry_run: bool,
    explain: bool,
    decision_id: str,
) -> Dict[str, Any]:
    # LAYER 4: Progressive profiling enrichment (PIP)
    # Always returns a decision (allow or deny with advice)
    required_fields = select_required_identity_fields(
        dependencies=dependencies,
        workflow_item_kind=workflow_item_kind,
    )
    presence = profile_store.get_identity_presence(principal_sub=principal_sub)
    missing_fields = compute_missing_fields(required_fields=required_fields, presence=presence)

    advice = build_profile_advice(
        missing_fields=missing_fields,
        workflow_id=workflow_id,
        workflow_item_id=workflow_item_id,
        workflow_item_kind=workflow_item_kind,
    )

    if len(missing_fields) > 0 and not dry_run:
        return {"decision": "deny", "decision_id": decision_id, "reason_codes": ["profile.missing_required_fields"], "advice": advice}

    reason_codes: List[str] = []
    if len(missing_fields) > 0:
        reason_codes.append("profile.missing_required_fields")

    if explain:
        policy_parameters = profile_store.get_policy_parameters(principal_sub=principal_sub)
        advice = advice + build_debug_advice(policy_parameters=policy_parameters)

    return {"decision": "allow", "decision_id": decision_id, "reason_codes": reason_codes, "advice": advice}


def extract_principal_sub(context: Dict[str, Any]) -> str:
    # Extract principal sub from context
    # why: bind workflow ownership to authenticated user
    # side effect: none.
    principal = context.get("principal", {})
    if not isinstance(principal, dict):
        raise ValueError("context.principal must be an object")
    return validate_non_empty_string(principal.get("id"), "context.principal.id")


def extract_workflow_item_id(resource: Dict[str, Any], property_names: List[str]) -> str:
    # Extract workflow item id from resource properties
    # why: allow multiple naming conventions across verticals
    # side effect: none.
    properties = resource.get("properties", {})
    if not isinstance(properties, dict):
        raise ValueError("resource.properties must be an object")

    for name in property_names:
        value = properties.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()

    raise ValueError(f"resource.properties must include one of {property_names}")


def extract_workflow_item_kind(resource: Dict[str, Any]) -> str:
    # Extract workflow item kind
    # why: select progressive profiling requirements per kind
    # side effect: none.
    properties = resource.get("properties", {})
    if not isinstance(properties, dict):
        return "unknown"
    value = properties.get("workflow_item_kind")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "unknown"


def map_action_to_relation(dependencies: Dependencies, action_name: str) -> str:
    # Map action name to ***REMOVED*** relation
    # why: decouple API action labels from directory permission names
    # side effect: none.
    action_name = validate_non_empty_string(action_name, "action.name")
    mapped = dependencies.action_relation_map.get(action_name)
    if isinstance(mapped, str) and mapped.strip():
        return mapped.strip()
    return action_name


def select_required_identity_fields(dependencies: Dependencies, workflow_item_kind: str) -> List[str]:
    # PROGRESSIVE PROFILING: Select required identity fields based on item kind
    # 
    # AUDIT NOTE: This is NOT an authorization decision - it's PIP (Policy Information Point) enrichment.
    # Returns advisory information about missing profile fields for UX guidance.
    # 
    # Dry-run mode: Returns advice but allows execution
    # Production mode: Denies if fields missing, returns advice
    # 
    # why: progressive profiling without hard-coding in policies yet.
    kind = workflow_item_kind.strip().lower() if isinstance(workflow_item_kind, str) else "unknown"
    fields = dependencies.required_identity_fields_by_item_kind.get(kind)
    if isinstance(fields, list) and len(fields) > 0:
        return list(fields)
    return list(dependencies.required_identity_fields_default)


def compute_missing_fields(required_fields: List[str], presence: Dict[str, bool]) -> List[str]:
    # Compute missing required presence flags
    # why: return actionable advice
    # side effect: none.
    missing: List[str] = []
    for field in required_fields:
        if not isinstance(field, str) or not field.strip():
            continue
        value = presence.get(field.strip(), False)
        if value is not True:
            missing.append(field.strip())
    return missing


def build_profile_advice(missing_fields: List[str], workflow_id: str, workflow_item_id: str, workflow_item_kind: str) -> List[Dict[str, Any]]:
    # Build profile advice objects
    # why: allow client to drive progressive profiling UX
    # side effect: none.
    advice: List[Dict[str, Any]] = []
    if len(missing_fields) == 0:
        return advice

    advice.append(
        {
            "kind": "profile",
            "code": "missing_required_fields",
            "message": "Additional profile fields are required to complete this action.",
            "details": {
                "missing_fields": list(missing_fields),
                "workflow_id": workflow_id,
                "workflow_item_id": workflow_item_id,
                "workflow_item_kind": workflow_item_kind,
            },
        }
    )
    return advice


def build_debug_advice(policy_parameters: Dict[str, Any]) -> List[Dict[str, Any]]:
    # Build debug advice
    # why: help demos show the policy context being used without leaking identifiers
    # side effect: none.
    return [
        {
            "kind": "debug",
            "code": "policy_parameters",
            "message": "Non-PII policy parameters were included in evaluation context.",
            "details": {"policy_parameters": policy_parameters},
        }
    ]


def call_***REMOVED***_policy(
    dependencies: Dependencies,
    policy_path: str,
    policy_input: Dict[str, Any],
) -> Dict[str, Any]:
    # ABAC POLICY EVALUATION: Call ***REMOVED*** OPA/Rego for attribute-based authorization
    # 
    # AUDIT NOTE: Authorization decision made by ***REMOVED*** Authorizer (OPA), NOT by this service.
    # Policy defined in: infra/***REMOVED***/cfg/policies/{policy_path}.rego (Rego language)
    # 
    # This function only:
    # - Assembles policy input (user parameters + resource attributes)
    # - Calls ***REMOVED*** Authorizer API
    # - Returns the decision and reason code from ***REMOVED*** OPA
    # 
    # policy_path: e.g., "flowpilot.auto_book" maps to package flowpilot.auto_book in auto_book.rego
    # policy_input: JSON input for the policy (user preferences, resource attributes)
    # returns: policy evaluation result with 'allow' and 'reason' fields from OPA
    # side effect: network I/O to ***REMOVED***.
    
    # ***REMOVED*** Authorizer API endpoint for policy evaluation
    # Port 8383 is the Authorizer gateway (see config.yaml)
    authorizer_base = dependencies.***REMOVED***_dir_base.replace(":9393", ":8383")
    url = build_url(authorizer_base, f"/api/v2/authz/is")
    
    payload: Dict[str, Any] = {
        "identity_context": {
            "type": "IDENTITY_TYPE_NONE",
            "identity": "",
        },
        "policy_context": {
            "path": policy_path,
            "decisions": ["allow", "reason"],
        },
        "policy_instance": {
            "name": "flowpilot",
            "instance_label": "flowpilot",
        },
        "resource_context": policy_input,
    }
    
    connect_seconds, read_seconds = dependencies.***REMOVED***_timeouts_connect_read
    timeouts = build_timeouts(connect_seconds=connect_seconds, read_seconds=read_seconds)
    
    data = http_post_json(url, payload, timeouts=timeouts)
    
    # Extract decisions from response
    decisions = data.get("decisions", [])
    result = {"allow": False, "reason": "auto_book.unknown_error"}
    
    for decision in decisions:
        if decision.get("decision") == "allow":
            result["allow"] = decision.get("is", False)
        elif decision.get("decision") == "reason":
            result["reason"] = decision.get("is", "auto_book.unknown_error")
    
    return result


def check_***REMOVED***_permission(
    dependencies: Dependencies,
    subject_type: str,
    subject_id: str,
    object_type: str,
    object_id: str,
    relation: str,
    trace: Optional[bool],
) -> bool:
    # ReBAC POLICY EVALUATION: Call ***REMOVED*** Directory for relationship-based authorization
    # 
    # AUDIT NOTE: Authorization decision made by ***REMOVED*** Directory, NOT by this service.
    # Policy defined in: infra/***REMOVED***/cfg/flowpilot-manifest.yaml
    # 
    # This function only:
    # - Assembles the check request
    # - Calls ***REMOVED*** Directory API
    # - Returns the decision from ***REMOVED***
    # 
    # side effect: network I/O to ***REMOVED***.
    url = build_url(dependencies.***REMOVED***_dir_base, dependencies.***REMOVED***_check_path)

    trace_value = dependencies.***REMOVED***_enable_trace_default if trace is None else bool(trace)
    payload: Dict[str, Any] = {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "object_type": object_type,
        "object_id": object_id,
        "relation": relation,
        "trace": bool(trace_value),
    }

    connect_seconds, read_seconds = dependencies.***REMOVED***_timeouts_connect_read
    timeouts = build_timeouts(connect_seconds=connect_seconds, read_seconds=read_seconds)

    data = http_post_json(url, payload, timeouts=timeouts)
    return bool(data.get("check", False))


def create_***REMOVED***_object(
    dependencies: Dependencies,
    object_type: str,
    object_id: str,
    display_name: str,
    properties: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    # Create an object in ***REMOVED*** Directory
    # why: maintain authorization graph for ReBAC permission evaluation
    # assumptions: ***REMOVED*** Directory Writer API is available at configured endpoint
    # side effect: network I/O, creates persistent object in ***REMOVED***
    # returns: ***REMOVED*** API response (typically includes created_at, etag, etc.)
    # raises: RuntimeError if ***REMOVED*** returns non-2xx status
    url = build_url(dependencies.***REMOVED***_dir_base, "/api/v3/directory/object")
    
    payload: Dict[str, Any] = {
        "object": {
            "type": validate_non_empty_string(object_type, "object_type"),
            "id": validate_non_empty_string(object_id, "object_id"),
            "display_name": str(display_name) if display_name else object_id,
            "properties": properties if isinstance(properties, dict) else {},
        }
    }
    
    connect_seconds, read_seconds = dependencies.***REMOVED***_timeouts_connect_read
    timeouts = build_timeouts(connect_seconds=connect_seconds, read_seconds=read_seconds)
    
    return http_post_json(url, payload, timeouts=timeouts)


def create_***REMOVED***_relation(
    dependencies: Dependencies,
    object_type: str,
    object_id: str,
    relation: str,
    subject_type: str,
    subject_id: str,
) -> Dict[str, Any]:
    # Create a relation (edge) in ***REMOVED*** Directory authorization graph
    # why: establish relationships for ReBAC permission inheritance
    # examples: workflow --owner--> user, workflow_item --workflow--> workflow, user --delegate--> agent
    # assumptions: Both object and subject must exist in ***REMOVED*** before creating relation
    # side effect: network I/O, creates persistent relation in ***REMOVED***
    # returns: ***REMOVED*** API response (typically includes created_at, etag, etc.)
    # raises: RuntimeError if ***REMOVED*** returns non-2xx status
    url = build_url(dependencies.***REMOVED***_dir_base, "/api/v3/directory/relation")
    
    payload: Dict[str, Any] = {
        "relation": {
            "object_type": validate_non_empty_string(object_type, "object_type"),
            "object_id": validate_non_empty_string(object_id, "object_id"),
            "relation": validate_non_empty_string(relation, "relation"),
            "subject_type": validate_non_empty_string(subject_type, "subject_type"),
            "subject_id": validate_non_empty_string(subject_id, "subject_id"),
            "subject_relation": "",
        }
    }
    
    connect_seconds, read_seconds = dependencies.***REMOVED***_timeouts_connect_read
    timeouts = build_timeouts(connect_seconds=connect_seconds, read_seconds=read_seconds)
    
    return http_post_json(url, payload, timeouts=timeouts)
