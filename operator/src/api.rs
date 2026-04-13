//! API endpoints for the Beeper UI
//!
//! Provides REST API endpoints for the UI to fetch source status,
//! health information, and ingestion statistics.

use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use kube::{api::ListParams, Api, Client};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use tracing::{debug, warn};

use crate::crds::{
    Investigation, InvestigationPhase, NotificationChannel, NotificationChannelCondition,
    ServiceLevel, ServiceLevelCondition, Severity, SliType, Source, WorkflowState,
};
use crate::detection::DetectionStats;
use crate::ingestion::IngestionBuffer;
use crate::llm::LlmManager;
use crate::notifications::outbox::OutboxEntry;
use crate::notifications::OutboxWorker;
use crate::slo::budget::BudgetPolicyState;
use crate::slo::SloCache;

/// Shared state for API endpoints
#[derive(Clone)]
pub struct ApiState {
    pub client: Arc<Client>,
    pub buffer: Arc<IngestionBuffer>,
    pub llm_manager: Option<Arc<LlmManager>>,
    pub detection_stats: Option<Arc<DetectionStats>>,
    pub slo_cache: Option<SloCache>,
    pub budget_policy_state: Option<BudgetPolicyState>,
    pub qdrant_endpoint: Option<String>,
}

/// Create the API router
pub fn api_router(client: Arc<Client>, buffer: Arc<IngestionBuffer>) -> Router {
    api_router_with_detection(client, buffer, None, None)
}

/// Create the API router with optional LLM manager
pub fn api_router_with_llm(
    client: Arc<Client>,
    buffer: Arc<IngestionBuffer>,
    llm_manager: Option<Arc<LlmManager>>,
) -> Router {
    api_router_with_detection(client, buffer, llm_manager, None)
}

/// Create the API router with optional LLM manager and detection stats
pub fn api_router_with_detection(
    client: Arc<Client>,
    buffer: Arc<IngestionBuffer>,
    llm_manager: Option<Arc<LlmManager>>,
    detection_stats: Option<Arc<DetectionStats>>,
) -> Router {
    api_router_full(
        client,
        buffer,
        llm_manager,
        detection_stats,
        None,
        None,
        None,
    )
}

/// Create the API router with all optional components including SLO cache
pub fn api_router_full(
    client: Arc<Client>,
    buffer: Arc<IngestionBuffer>,
    llm_manager: Option<Arc<LlmManager>>,
    detection_stats: Option<Arc<DetectionStats>>,
    slo_cache: Option<SloCache>,
    budget_policy_state: Option<BudgetPolicyState>,
    qdrant_endpoint: Option<String>,
) -> Router {
    let state = ApiState {
        client,
        buffer,
        llm_manager,
        detection_stats,
        slo_cache,
        budget_policy_state,
        qdrant_endpoint,
    };

    Router::new()
        .route("/api/v1/sources", get(list_sources))
        .route("/api/v1/investigations", get(list_investigations))
        .route("/api/v1/investigations/:id", get(get_investigation))
        .route(
            "/api/v1/investigations/:id/confirm",
            post(confirm_investigation),
        )
        .route(
            "/api/v1/investigations/:id/reject",
            post(reject_investigation),
        )
        .route(
            "/api/v1/investigations/:id/resolve",
            post(resolve_investigation),
        )
        .route(
            "/api/v1/investigations/:id/verify",
            post(verify_investigation),
        )
        .route("/api/v1/slo/services", get(list_servicelevels))
        .route("/api/v1/slo/services/:name", get(get_servicelevel))
        .route(
            "/api/v1/slo/services/:name/budget",
            get(get_servicelevel_budget),
        )
        .route(
            "/api/v1/notifications/channels",
            get(list_notification_channels),
        )
        .route(
            "/api/v1/notifications/outbox",
            post(write_notification_outbox),
        )
        .route("/api/v1/health/components", get(health_components))
        .route("/api/v1/ingestion/stats", get(ingestion_stats))
        .route("/api/v1/detection/stats", get(detection_stats_handler))
        .with_state(state)
}

// ----- Source API -----

/// Response for a single source
#[derive(Debug, Serialize)]
pub struct SourceResponse {
    pub name: String,
    #[serde(rename = "type")]
    pub source_type: String,
    pub endpoint: String,
    pub status: String,
    pub last_check: Option<String>,
    pub error: Option<SourceErrorResponse>,
}

/// Error details for a source
#[derive(Debug, Serialize)]
pub struct SourceErrorResponse {
    #[serde(rename = "type")]
    pub error_type: String,
    pub message: String,
    pub details: Option<String>,
}

/// Response for listing all sources
#[derive(Debug, Serialize)]
pub struct SourceListResponse {
    pub sources: Vec<SourceResponse>,
}

/// List all configured sources with their status
async fn list_sources(State(state): State<ApiState>) -> impl IntoResponse {
    // Try to list Source CRDs from the cluster
    let sources_api: Api<Source> = Api::all((*state.client).clone());

    match sources_api.list(&ListParams::default()).await {
        Ok(source_list) => {
            let sources: Vec<SourceResponse> = source_list
                .items
                .into_iter()
                .map(|source| {
                    let name = source.metadata.name.unwrap_or_default();
                    let spec = source.spec;
                    let status = source.status.unwrap_or_default();

                    // Convert SourceType enum to string
                    let source_type = format!("{:?}", spec.source_type).to_lowercase();

                    // Determine connection status from the status fields
                    let (connection_status, error) = match (status.connected, &status.error) {
                        (Some(true), _) => ("connected".to_string(), None),
                        (Some(false), Some(err_msg)) => {
                            let error = SourceErrorResponse {
                                error_type: "connection_error".to_string(),
                                message: err_msg.clone(),
                                details: None,
                            };
                            ("error".to_string(), Some(error))
                        }
                        (Some(false), None) => ("error".to_string(), None),
                        (None, _) => ("unknown".to_string(), None),
                    };

                    SourceResponse {
                        name,
                        source_type,
                        endpoint: spec.endpoint,
                        status: connection_status,
                        last_check: status.last_checked,
                        error,
                    }
                })
                .collect();

            debug!(count = sources.len(), "Listed sources");
            (StatusCode::OK, Json(SourceListResponse { sources })).into_response()
        }
        Err(e) => {
            warn!(error = %e, "Failed to list sources");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/source-list-failed".to_string(),
                    title: "Failed to list sources".to_string(),
                    status: 500,
                    detail: format!("Could not retrieve source list: {}", e),
                }),
            )
                .into_response()
        }
    }
}

// ----- Investigation API -----

/// Query parameters for filtering investigations
#[derive(Debug, Deserialize)]
pub struct InvestigationQuery {
    pub status: Option<String>,
    pub service: Option<String>,
    pub severity: Option<String>,
}

/// Response for a single investigation (list view)
#[derive(Debug, Serialize)]
pub struct InvestigationResponse {
    pub id: String,
    pub status: String,
    pub service: String,
    pub severity: String,
    pub condition: String,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub triggered_at: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub impact_score: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub workflow_state: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub workflow_state_changed_at: Option<String>,
}

/// Response for a single investigation detail (extends list response)
#[derive(Debug, Serialize)]
pub struct InvestigationDetailResponse {
    pub id: String,
    pub status: String,
    pub service: String,
    pub severity: String,
    pub condition: String,
    pub started_at: Option<String>,
    pub completed_at: Option<String>,
    pub triggered_at: Option<String>,
    pub message: Option<String>,
    pub error: Option<String>,
    pub job_name: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub impact_score: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub workflow_state: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub workflow_state_changed_at: Option<String>,
}

/// Map InvestigationPhase to UI-friendly status string
fn phase_to_status(phase: &Option<InvestigationPhase>) -> String {
    match phase {
        Some(InvestigationPhase::Pending) | Some(InvestigationPhase::Running) => {
            "investigating".to_string()
        }
        Some(InvestigationPhase::AwaitingConfirmation) => "awaiting_confirmation".to_string(),
        Some(InvestigationPhase::Completed) => "completed".to_string(),
        Some(InvestigationPhase::Failed) => "failed".to_string(),
        None => "investigating".to_string(),
    }
}

/// Map WorkflowState to string for API responses
fn workflow_state_to_string(state: &Option<WorkflowState>) -> Option<String> {
    state.as_ref().map(|s| match s {
        WorkflowState::Detected => "detected".to_string(),
        WorkflowState::Investigating => "investigating".to_string(),
        WorkflowState::Resolved => "resolved".to_string(),
        WorkflowState::Verified => "verified".to_string(),
        WorkflowState::Failed => "failed".to_string(),
    })
}

/// Map Severity to lowercase string
fn severity_to_string(severity: &Severity) -> String {
    match severity {
        Severity::Low => "low".to_string(),
        Severity::Medium => "medium".to_string(),
        Severity::High => "high".to_string(),
        Severity::Critical => "critical".to_string(),
    }
}

/// Status sort priority (lower = higher priority)
fn status_sort_order(status: &str) -> u8 {
    match status {
        "awaiting_confirmation" => 0,
        "investigating" => 1,
        "failed" => 2,
        "completed" => 3,
        _ => 4,
    }
}

/// List all investigations with optional filtering
async fn list_investigations(
    State(state): State<ApiState>,
    Query(params): Query<InvestigationQuery>,
) -> impl IntoResponse {
    let investigations_api: Api<Investigation> = Api::all((*state.client).clone());

    match investigations_api.list(&ListParams::default()).await {
        Ok(investigation_list) => {
            let mut investigations: Vec<InvestigationResponse> = investigation_list
                .items
                .into_iter()
                .map(|inv| {
                    let id = inv.metadata.name.unwrap_or_default();
                    let spec = inv.spec;
                    let status = inv.status.unwrap_or_default();

                    let ui_status = phase_to_status(&status.phase);
                    let severity = severity_to_string(&spec.severity);

                    InvestigationResponse {
                        id,
                        status: ui_status,
                        service: spec.service,
                        severity,
                        condition: spec.condition,
                        started_at: status.started_at,
                        completed_at: status.completed_at,
                        triggered_at: spec.triggered_at,
                        impact_score: spec.impact_score,
                        workflow_state: workflow_state_to_string(&status.workflow_state),
                        workflow_state_changed_at: status.workflow_state_changed_at,
                    }
                })
                .collect();

            // Apply filters
            if let Some(ref status_filter) = params.status {
                investigations.retain(|inv| inv.status == *status_filter);
            }
            if let Some(ref service_filter) = params.service {
                investigations.retain(|inv| inv.service == *service_filter);
            }
            if let Some(ref severity_filter) = params.severity {
                investigations.retain(|inv| inv.severity == *severity_filter);
            }

            // Sort: status priority → impact_score descending → started_at descending
            investigations.sort_by(|a, b| {
                let order_cmp = status_sort_order(&a.status).cmp(&status_sort_order(&b.status));
                if order_cmp != std::cmp::Ordering::Equal {
                    return order_cmp;
                }
                // Within same status, sort by impact_score descending (highest first, None last)
                let impact_cmp = match (a.impact_score, b.impact_score) {
                    (Some(a_score), Some(b_score)) => b_score
                        .partial_cmp(&a_score)
                        .unwrap_or(std::cmp::Ordering::Equal),
                    (Some(_), None) => std::cmp::Ordering::Less, // a (Some) before b (None)
                    (None, Some(_)) => std::cmp::Ordering::Greater, // a (None) after b (Some)
                    (None, None) => std::cmp::Ordering::Equal,
                };
                if impact_cmp != std::cmp::Ordering::Equal {
                    return impact_cmp;
                }
                // Tertiary: by started_at descending (most recent first)
                b.started_at
                    .as_deref()
                    .unwrap_or("")
                    .cmp(a.started_at.as_deref().unwrap_or(""))
            });

            debug!(count = investigations.len(), "Listed investigations");
            (StatusCode::OK, Json(investigations)).into_response()
        }
        Err(e) => {
            warn!(error = %e, "Failed to list investigations");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/investigation-list-failed".to_string(),
                    title: "Failed to list investigations".to_string(),
                    status: 500,
                    detail: format!("Could not retrieve investigation list: {}", e),
                }),
            )
                .into_response()
        }
    }
}

/// Get a single investigation by ID
async fn get_investigation(
    State(state): State<ApiState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    let investigations_api: Api<Investigation> = Api::all((*state.client).clone());

    match investigations_api.get(&id).await {
        Ok(inv) => {
            let spec = inv.spec;
            let status = inv.status.unwrap_or_default();

            let ui_status = phase_to_status(&status.phase);
            let severity = severity_to_string(&spec.severity);

            let response = InvestigationDetailResponse {
                id: inv.metadata.name.unwrap_or_default(),
                status: ui_status,
                service: spec.service,
                severity,
                condition: spec.condition,
                started_at: status.started_at,
                completed_at: status.completed_at,
                triggered_at: spec.triggered_at,
                message: status.message,
                error: status.error,
                job_name: status.job_name,
                impact_score: spec.impact_score,
                workflow_state: workflow_state_to_string(&status.workflow_state),
                workflow_state_changed_at: status.workflow_state_changed_at,
            };

            debug!(investigation_id = %response.id, "Got investigation detail");
            (StatusCode::OK, Json(response)).into_response()
        }
        Err(kube::Error::Api(err)) if err.code == 404 => {
            warn!(investigation_id = %id, "Investigation not found");
            (
                StatusCode::NOT_FOUND,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/investigation-not-found".to_string(),
                    title: "Investigation not found".to_string(),
                    status: 404,
                    detail: format!("No investigation found with ID: {}", id),
                }),
            )
                .into_response()
        }
        Err(e) => {
            warn!(error = %e, investigation_id = %id, "Failed to get investigation");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/investigation-get-failed".to_string(),
                    title: "Failed to get investigation".to_string(),
                    status: 500,
                    detail: format!("Could not retrieve investigation: {}", e),
                }),
            )
                .into_response()
        }
    }
}

// ----- Resolution Confirmation API -----

/// Request body for confirming an investigation's resolution
#[derive(Debug, Deserialize, Serialize)]
pub struct ResolutionConfirmRequest {
    pub comment: Option<String>,
}

/// Request body for rejecting an investigation's resolution
#[derive(Debug, Deserialize, Serialize)]
pub struct ResolutionRejectRequest {
    pub reason: String,
    pub reason_details: Option<String>,
    pub correction: Option<String>,
}

/// Response for confirm/reject actions
#[derive(Debug, Serialize)]
pub struct ResolutionActionResponse {
    pub status: String,
    pub message: String,
}

/// Confirm an investigation's resolution recommendation
async fn confirm_investigation(
    State(state): State<ApiState>,
    Path(id): Path<String>,
    Json(body): Json<ResolutionConfirmRequest>,
) -> impl IntoResponse {
    let investigations_api: Api<Investigation> = Api::all((*state.client).clone());

    match investigations_api.get(&id).await {
        Ok(_inv) => {
            // Patch the CRD status to mark as confirmed
            let patch = serde_json::json!({
                "status": {
                    "phase": "completed",
                    "message": "Resolution confirmed by SRE"
                }
            });

            match investigations_api
                .patch_status(
                    &id,
                    &kube::api::PatchParams::apply("beeper-ui"),
                    &kube::api::Patch::Merge(patch),
                )
                .await
            {
                Ok(_) => {
                    let comment_msg = body.comment.as_deref().unwrap_or("No comment provided");
                    debug!(
                        investigation_id = %id,
                        comment = %comment_msg,
                        "Investigation resolution confirmed"
                    );
                    (
                        StatusCode::OK,
                        Json(ResolutionActionResponse {
                            status: "confirmed".to_string(),
                            message: format!("Investigation {} resolution confirmed", id),
                        }),
                    )
                        .into_response()
                }
                Err(e) => {
                    warn!(error = %e, investigation_id = %id, "Failed to patch investigation status");
                    (
                        StatusCode::INTERNAL_SERVER_ERROR,
                        Json(ProblemDetails {
                            error_type: "https://beeper.io/errors/investigation-confirm-failed"
                                .to_string(),
                            title: "Failed to confirm investigation".to_string(),
                            status: 500,
                            detail: format!("Could not update investigation status: {}", e),
                        }),
                    )
                        .into_response()
                }
            }
        }
        Err(kube::Error::Api(err)) if err.code == 404 => {
            warn!(investigation_id = %id, "Investigation not found for confirmation");
            (
                StatusCode::NOT_FOUND,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/investigation-not-found".to_string(),
                    title: "Investigation not found".to_string(),
                    status: 404,
                    detail: format!("No investigation found with ID: {}", id),
                }),
            )
                .into_response()
        }
        Err(e) => {
            warn!(error = %e, investigation_id = %id, "Failed to get investigation for confirmation");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/investigation-confirm-failed".to_string(),
                    title: "Failed to confirm investigation".to_string(),
                    status: 500,
                    detail: format!("Could not retrieve investigation: {}", e),
                }),
            )
                .into_response()
        }
    }
}

/// Reject an investigation's resolution recommendation
async fn reject_investigation(
    State(state): State<ApiState>,
    Path(id): Path<String>,
    Json(body): Json<ResolutionRejectRequest>,
) -> impl IntoResponse {
    let investigations_api: Api<Investigation> = Api::all((*state.client).clone());

    match investigations_api.get(&id).await {
        Ok(_inv) => {
            // Patch the CRD status — keep phase as awaiting_confirmation, update message
            let reject_message = format!("Resolution rejected: {}", body.reason);
            let patch = serde_json::json!({
                "status": {
                    "message": reject_message
                }
            });

            match investigations_api
                .patch_status(
                    &id,
                    &kube::api::PatchParams::apply("beeper-ui"),
                    &kube::api::Patch::Merge(patch),
                )
                .await
            {
                Ok(_) => {
                    debug!(
                        investigation_id = %id,
                        reason = %body.reason,
                        "Investigation resolution rejected"
                    );
                    (
                        StatusCode::OK,
                        Json(ResolutionActionResponse {
                            status: "rejected".to_string(),
                            message: format!("Investigation {} resolution rejected", id),
                        }),
                    )
                        .into_response()
                }
                Err(e) => {
                    warn!(error = %e, investigation_id = %id, "Failed to patch investigation status for rejection");
                    (
                        StatusCode::INTERNAL_SERVER_ERROR,
                        Json(ProblemDetails {
                            error_type: "https://beeper.io/errors/investigation-reject-failed"
                                .to_string(),
                            title: "Failed to reject investigation".to_string(),
                            status: 500,
                            detail: format!("Could not update investigation status: {}", e),
                        }),
                    )
                        .into_response()
                }
            }
        }
        Err(kube::Error::Api(err)) if err.code == 404 => {
            warn!(investigation_id = %id, "Investigation not found for rejection");
            (
                StatusCode::NOT_FOUND,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/investigation-not-found".to_string(),
                    title: "Investigation not found".to_string(),
                    status: 404,
                    detail: format!("No investigation found with ID: {}", id),
                }),
            )
                .into_response()
        }
        Err(e) => {
            warn!(error = %e, investigation_id = %id, "Failed to get investigation for rejection");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/investigation-reject-failed".to_string(),
                    title: "Failed to reject investigation".to_string(),
                    status: 500,
                    detail: format!("Could not retrieve investigation: {}", e),
                }),
            )
                .into_response()
        }
    }
}

/// Request body for resolving an investigation with outcome
#[derive(Debug, Deserialize, Serialize)]
pub struct ResolutionResolveRequest {
    pub outcome: String,
    pub accuracy_rating: Option<String>,
    pub resolution_notes: Option<String>,
    pub escalation_target: Option<String>,
    pub not_an_issue_reason: Option<String>,
}

/// Resolve an investigation with a final outcome
async fn resolve_investigation(
    State(state): State<ApiState>,
    Path(id): Path<String>,
    Json(body): Json<ResolutionResolveRequest>,
) -> impl IntoResponse {
    let investigations_api: Api<Investigation> = Api::all((*state.client).clone());

    match investigations_api.get(&id).await {
        Ok(_inv) => {
            // Build patch based on outcome
            let message = match body.outcome.as_str() {
                "resolved" => {
                    let notes = body
                        .resolution_notes
                        .as_deref()
                        .unwrap_or("No details provided");
                    format!("Investigation resolved: {}", notes)
                }
                "not_an_issue" => {
                    let reason = body.not_an_issue_reason.as_deref().unwrap_or("unspecified");
                    format!("Not an issue: {}", reason)
                }
                "escalated" => {
                    let target = body.escalation_target.as_deref().unwrap_or("unspecified");
                    format!("Escalated to: {}", target)
                }
                "unresolved" => "Investigation closed as unresolved".to_string(),
                _ => format!("Investigation resolved with outcome: {}", body.outcome),
            };

            // For escalated: don't change phase or set completed_at
            // For all others: set phase to completed and completed_at
            let patch = if body.outcome == "escalated" {
                serde_json::json!({
                    "status": {
                        "message": message
                    }
                })
            } else {
                let completed_at = chrono::Utc::now().to_rfc3339();
                serde_json::json!({
                    "status": {
                        "phase": "completed",
                        "completed_at": completed_at,
                        "message": message
                    }
                })
            };

            match investigations_api
                .patch_status(
                    &id,
                    &kube::api::PatchParams::apply("beeper-ui"),
                    &kube::api::Patch::Merge(patch),
                )
                .await
            {
                Ok(_) => {
                    debug!(
                        investigation_id = %id,
                        outcome = %body.outcome,
                        "Investigation resolved"
                    );
                    (
                        StatusCode::OK,
                        Json(ResolutionActionResponse {
                            status: body.outcome.clone(),
                            message: format!("Investigation {} resolved as {}", id, body.outcome),
                        }),
                    )
                        .into_response()
                }
                Err(e) => {
                    warn!(error = %e, investigation_id = %id, "Failed to patch investigation status for resolution");
                    (
                        StatusCode::INTERNAL_SERVER_ERROR,
                        Json(ProblemDetails {
                            error_type: "https://beeper.io/errors/investigation-resolve-failed"
                                .to_string(),
                            title: "Failed to resolve investigation".to_string(),
                            status: 500,
                            detail: format!("Could not update investigation status: {}", e),
                        }),
                    )
                        .into_response()
                }
            }
        }
        Err(kube::Error::Api(err)) if err.code == 404 => {
            warn!(investigation_id = %id, "Investigation not found for resolution");
            (
                StatusCode::NOT_FOUND,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/investigation-not-found".to_string(),
                    title: "Investigation not found".to_string(),
                    status: 404,
                    detail: format!("No investigation found with ID: {}", id),
                }),
            )
                .into_response()
        }
        Err(e) => {
            warn!(error = %e, investigation_id = %id, "Failed to get investigation for resolution");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/investigation-resolve-failed".to_string(),
                    title: "Failed to resolve investigation".to_string(),
                    status: 500,
                    detail: format!("Could not retrieve investigation: {}", e),
                }),
            )
                .into_response()
        }
    }
}

/// Verify an investigation (transition from Resolved to Verified)
async fn verify_investigation(
    State(state): State<ApiState>,
    Path(id): Path<String>,
) -> impl IntoResponse {
    let investigations_api: Api<Investigation> = Api::all((*state.client).clone());

    match investigations_api.get(&id).await {
        Ok(inv) => {
            let current_workflow_state = inv.status.as_ref().and_then(|s| s.workflow_state.clone());

            // Validate transition: only Resolved → Verified is allowed
            match current_workflow_state {
                Some(WorkflowState::Resolved) => {
                    let now = chrono::Utc::now().format("%Y-%m-%dT%H:%M:%SZ").to_string();
                    let patch = serde_json::json!({
                        "status": {
                            "workflow_state": "verified",
                            "workflow_state_changed_at": now,
                            "message": "Investigation verified — fix confirmed"
                        }
                    });

                    match investigations_api
                        .patch_status(
                            &id,
                            &kube::api::PatchParams::apply("beeper-ui"),
                            &kube::api::Patch::Merge(patch),
                        )
                        .await
                    {
                        Ok(_) => {
                            debug!(
                                investigation_id = %id,
                                "Investigation verified"
                            );
                            (
                                StatusCode::OK,
                                Json(ResolutionActionResponse {
                                    status: "verified".to_string(),
                                    message: format!("Investigation {} verified", id),
                                }),
                            )
                                .into_response()
                        }
                        Err(e) => {
                            warn!(error = %e, investigation_id = %id, "Failed to patch investigation for verification");
                            (
                                StatusCode::INTERNAL_SERVER_ERROR,
                                Json(ProblemDetails {
                                    error_type:
                                        "https://beeper.io/errors/investigation-verify-failed"
                                            .to_string(),
                                    title: "Failed to verify investigation".to_string(),
                                    status: 500,
                                    detail: format!("Could not update investigation status: {}", e),
                                }),
                            )
                                .into_response()
                        }
                    }
                }
                _ => {
                    let current_str = current_workflow_state
                        .map(|s| format!("{:?}", s).to_lowercase())
                        .unwrap_or_else(|| "none".to_string());
                    warn!(
                        investigation_id = %id,
                        current_state = %current_str,
                        "Cannot verify investigation — not in resolved state"
                    );
                    (
                        StatusCode::CONFLICT,
                        Json(ProblemDetails {
                            error_type: "https://beeper.io/errors/invalid-state-transition"
                                .to_string(),
                            title: "Invalid state transition".to_string(),
                            status: 409,
                            detail: format!(
                                "Cannot verify investigation in '{}' state. Only 'resolved' investigations can be verified.",
                                current_str
                            ),
                        }),
                    )
                        .into_response()
                }
            }
        }
        Err(kube::Error::Api(err)) if err.code == 404 => {
            warn!(investigation_id = %id, "Investigation not found for verification");
            (
                StatusCode::NOT_FOUND,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/investigation-not-found".to_string(),
                    title: "Investigation not found".to_string(),
                    status: 404,
                    detail: format!("No investigation found with ID: {}", id),
                }),
            )
                .into_response()
        }
        Err(e) => {
            warn!(error = %e, investigation_id = %id, "Failed to get investigation for verification");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/investigation-verify-failed".to_string(),
                    title: "Failed to verify investigation".to_string(),
                    status: 500,
                    detail: format!("Could not retrieve investigation: {}", e),
                }),
            )
                .into_response()
        }
    }
}

// ----- Health Components API -----

/// Response for a single component
#[derive(Debug, Serialize)]
pub struct ComponentStatusResponse {
    pub status: String,
    pub message: String,
}

/// Response for health components
#[derive(Debug, Serialize)]
pub struct HealthComponentsResponse {
    pub components: std::collections::HashMap<String, ComponentStatusResponse>,
    pub overall: String,
}

/// Get detailed health status of all components
async fn health_components(State(state): State<ApiState>) -> impl IntoResponse {
    let mut components = std::collections::HashMap::new();
    let mut overall_healthy = true;

    // Check operator (always healthy if we're responding)
    components.insert(
        "operator".to_string(),
        ComponentStatusResponse {
            status: "healthy".to_string(),
            message: "Running".to_string(),
        },
    );

    // Check Kubernetes API connectivity
    match state.client.apiserver_version().await {
        Ok(_) => {
            components.insert(
                "kubernetes".to_string(),
                ComponentStatusResponse {
                    status: "healthy".to_string(),
                    message: "Connected to API server".to_string(),
                },
            );
        }
        Err(e) => {
            overall_healthy = false;
            components.insert(
                "kubernetes".to_string(),
                ComponentStatusResponse {
                    status: "unhealthy".to_string(),
                    message: format!("Cannot reach API server: {}", e),
                },
            );
        }
    }

    // Check ingestion buffer status
    let buffer_count = state.buffer.buffered_count();
    let buffer_capacity = state.buffer.capacity();
    let is_full = state.buffer.is_full();

    let ingestion_status = if is_full { "warning" } else { "healthy" };
    components.insert(
        "ingestion".to_string(),
        ComponentStatusResponse {
            status: ingestion_status.to_string(),
            message: format!("Buffer: {}/{}", buffer_count, buffer_capacity),
        },
    );

    // Check LLM connectivity if configured
    if let Some(ref llm_manager) = state.llm_manager {
        let llm_health = llm_manager.check_health().await;
        let (status, message) = match llm_health.status.as_str() {
            "healthy" => ("healthy", llm_health.message),
            "unconfigured" => ("warning", llm_health.message),
            _ => {
                overall_healthy = false;
                ("unhealthy", llm_health.message)
            }
        };
        components.insert(
            "llm".to_string(),
            ComponentStatusResponse {
                status: status.to_string(),
                message,
            },
        );
    } else {
        // LLM not configured
        components.insert(
            "llm".to_string(),
            ComponentStatusResponse {
                status: "unconfigured".to_string(),
                message: "LLM provider not configured".to_string(),
            },
        );
    }

    let overall = if overall_healthy {
        "healthy"
    } else {
        "unhealthy"
    };

    (
        StatusCode::OK,
        Json(HealthComponentsResponse {
            components,
            overall: overall.to_string(),
        }),
    )
}

// ----- Ingestion Stats API -----

/// Per-source health response (FR4)
#[derive(Debug, Serialize)]
pub struct SourceHealthResponse {
    pub bytes_received: u64,
    pub parse_errors: u64,
    pub last_received_ns: i64,
}

impl From<crate::ingestion::SourceHealthSnapshot> for SourceHealthResponse {
    fn from(s: crate::ingestion::SourceHealthSnapshot) -> Self {
        Self {
            bytes_received: s.bytes_received,
            parse_errors: s.parse_errors,
            last_received_ns: s.last_received_ns,
        }
    }
}

/// Response for ingestion statistics
#[derive(Debug, Serialize)]
pub struct IngestionStatsResponse {
    pub buffer_size: usize,
    pub buffered_count: u64,
    pub dropped_count: u64,
    pub is_full: bool,
    pub metrics_received: u64,
    pub logs_received: u64,
    pub sources: std::collections::HashMap<String, SourceHealthResponse>,
}

/// Get ingestion buffer statistics
async fn ingestion_stats(State(state): State<ApiState>) -> impl IntoResponse {
    let mut sources = std::collections::HashMap::new();
    sources.insert(
        "prometheus".to_string(),
        SourceHealthResponse::from(state.buffer.prometheus_health().snapshot()),
    );
    sources.insert(
        "loki".to_string(),
        SourceHealthResponse::from(state.buffer.loki_health().snapshot()),
    );
    sources.insert(
        "otlp".to_string(),
        SourceHealthResponse::from(state.buffer.otlp_health().snapshot()),
    );

    let stats = IngestionStatsResponse {
        buffer_size: state.buffer.capacity(),
        buffered_count: state.buffer.buffered_count(),
        dropped_count: state.buffer.dropped_count(),
        is_full: state.buffer.is_full(),
        metrics_received: state.buffer.metrics_received(),
        logs_received: state.buffer.logs_received(),
        sources,
    };

    debug!(
        buffer_size = stats.buffer_size,
        buffered = stats.buffered_count,
        dropped = stats.dropped_count,
        metrics = stats.metrics_received,
        logs = stats.logs_received,
        "Ingestion stats requested"
    );

    (StatusCode::OK, Json(stats))
}

// ----- Detection Stats API -----

/// Response for detection statistics
#[derive(Debug, Serialize)]
pub struct DetectionStatsResponse {
    pub metrics_tracked: u64,
    pub services_tracked: u64,
    pub anomalies_detected: u64,
    pub cooldown_entries: u64,
}

/// Get detection engine statistics
async fn detection_stats_handler(State(state): State<ApiState>) -> impl IntoResponse {
    match &state.detection_stats {
        Some(stats) => {
            use std::sync::atomic::Ordering;
            let response = DetectionStatsResponse {
                metrics_tracked: stats.metrics_tracked.load(Ordering::Relaxed),
                services_tracked: stats.services_tracked.load(Ordering::Relaxed),
                anomalies_detected: stats.anomalies_detected.load(Ordering::Relaxed),
                cooldown_entries: stats.cooldown_entries.load(Ordering::Relaxed),
            };

            debug!(
                metrics_tracked = response.metrics_tracked,
                services_tracked = response.services_tracked,
                anomalies_detected = response.anomalies_detected,
                "Detection stats requested"
            );

            (StatusCode::OK, Json(response)).into_response()
        }
        None => (
            StatusCode::OK,
            Json(DetectionStatsResponse {
                metrics_tracked: 0,
                services_tracked: 0,
                anomalies_detected: 0,
                cooldown_entries: 0,
            }),
        )
            .into_response(),
    }
}

// ----- RFC 7807 Problem Details -----

// ----- ServiceLevel (SLO) API -----

/// Response for a single ServiceLevel in list view
#[derive(Debug, Serialize)]
pub struct ServiceLevelResponse {
    pub name: String,
    pub service: String,
    pub sli_type: String,
    pub target: f64,
    pub window: String,
    pub condition: String,
    pub alerts_registered: Option<u32>,
    pub last_evaluated: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub compliance: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub burn_rate: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_budget_remaining: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub is_frozen: Option<bool>,
}

/// Response for ServiceLevel detail view
#[derive(Debug, Serialize)]
pub struct ServiceLevelDetailResponse {
    pub name: String,
    pub service: String,
    pub sli: SliDetailResponse,
    pub objective: ObjectiveDetailResponse,
    pub burn_rate_alerts: Vec<BurnRateAlertResponse>,
    pub condition: String,
    pub alerts_registered: Option<u32>,
    pub last_evaluated: Option<String>,
    pub error: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub compliance: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub burn_rate: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error_budget_remaining: Option<f64>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub is_frozen: Option<bool>,
}

/// SLI detail for ServiceLevel response
#[derive(Debug, Serialize)]
pub struct SliDetailResponse {
    #[serde(rename = "type")]
    pub sli_type: String,
    pub metric: String,
    pub good_selector: String,
    pub total_selector: String,
}

/// Objective detail for ServiceLevel response
#[derive(Debug, Serialize)]
pub struct ObjectiveDetailResponse {
    pub target: f64,
    pub window: String,
}

/// Burn rate alert detail for ServiceLevel response
#[derive(Debug, Serialize)]
pub struct BurnRateAlertResponse {
    pub severity: String,
    pub short_window: String,
    pub long_window: String,
    pub factor: f64,
}

/// Response for listing all ServiceLevels
#[derive(Debug, Serialize)]
pub struct ServiceLevelListResponse {
    pub service_levels: Vec<ServiceLevelResponse>,
}

/// Map SliType to its canonical string representation (matches serde snake_case)
pub fn sli_type_to_string(sli_type: &SliType) -> String {
    match sli_type {
        SliType::Availability => "availability".to_string(),
        SliType::Latency => "latency".to_string(),
        SliType::ErrorRate => "error_rate".to_string(),
    }
}

/// Map ServiceLevelCondition to string
fn condition_to_string(condition: &Option<ServiceLevelCondition>) -> String {
    match condition {
        Some(ServiceLevelCondition::Healthy) => "healthy".to_string(),
        Some(ServiceLevelCondition::Warning) => "warning".to_string(),
        Some(ServiceLevelCondition::Critical) => "critical".to_string(),
        None => "unknown".to_string(),
    }
}

/// List all ServiceLevel CRDs with their status
async fn list_servicelevels(State(state): State<ApiState>) -> impl IntoResponse {
    let servicelevels_api: Api<ServiceLevel> = Api::all((*state.client).clone());

    // Load SLO cache snapshot for burn rate data
    let slo_data = if let Some(ref cache) = state.slo_cache {
        let guard = cache.read().await;
        Some(guard.clone())
    } else {
        None
    };

    // Load budget policy state snapshot
    let budget_data = if let Some(ref bps) = state.budget_policy_state {
        let guard = bps.read().await;
        Some(guard.clone())
    } else {
        None
    };

    match servicelevels_api.list(&ListParams::default()).await {
        Ok(sl_list) => {
            let service_levels: Vec<ServiceLevelResponse> = sl_list
                .items
                .into_iter()
                .map(|sl| {
                    let name = sl.metadata.name.unwrap_or_default();
                    let spec = sl.spec;
                    let status = sl.status.unwrap_or_default();

                    let sli_type = sli_type_to_string(&spec.sli.sli_type);

                    // Look up latest burn rate data from SLO cache
                    let (compliance, burn_rate, error_budget_remaining) =
                        if let Some(ref data) = slo_data {
                            if let Some(calc) = data.get(&name) {
                                (
                                    Some(calc.compliance),
                                    Some(calc.burn_rate),
                                    Some(calc.error_budget_remaining),
                                )
                            } else {
                                (None, None, None)
                            }
                        } else {
                            (None, None, None)
                        };

                    // Look up freeze status from budget policy state
                    let is_frozen = budget_data
                        .as_ref()
                        .and_then(|data| data.get(&name))
                        .map(|s| s.is_frozen);

                    ServiceLevelResponse {
                        name,
                        service: spec.service,
                        sli_type,
                        target: spec.objective.target,
                        window: spec.objective.window,
                        condition: condition_to_string(&status.condition),
                        alerts_registered: status.alerts_registered,
                        last_evaluated: status.last_evaluated,
                        compliance,
                        burn_rate,
                        error_budget_remaining,
                        is_frozen,
                    }
                })
                .collect();

            debug!(count = service_levels.len(), "Listed ServiceLevels");
            (
                StatusCode::OK,
                Json(ServiceLevelListResponse { service_levels }),
            )
                .into_response()
        }
        Err(e) => {
            warn!(error = %e, "Failed to list ServiceLevels");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/servicelevel-list-failed".to_string(),
                    title: "Failed to list ServiceLevels".to_string(),
                    status: 500,
                    detail: format!("Could not retrieve ServiceLevel list: {}", e),
                }),
            )
                .into_response()
        }
    }
}

/// Get a single ServiceLevel by name
async fn get_servicelevel(
    State(state): State<ApiState>,
    Path(name): Path<String>,
) -> impl IntoResponse {
    let servicelevels_api: Api<ServiceLevel> = Api::all((*state.client).clone());

    match servicelevels_api.get(&name).await {
        Ok(sl) => {
            let sl_name = sl.metadata.name.clone().unwrap_or_default();
            let spec = sl.spec;
            let status = sl.status.unwrap_or_default();

            let sli_type = sli_type_to_string(&spec.sli.sli_type);

            let burn_rate_alerts = spec
                .burn_rate_alerts
                .unwrap_or_default()
                .into_iter()
                .map(|a| BurnRateAlertResponse {
                    severity: a.severity,
                    short_window: a.short_window,
                    long_window: a.long_window,
                    factor: a.factor,
                })
                .collect();

            // Look up latest burn rate data from SLO cache
            let (compliance, burn_rate, error_budget_remaining) =
                if let Some(ref cache) = state.slo_cache {
                    let guard = cache.read().await;
                    if let Some(calc) = guard.get(&sl_name) {
                        (
                            Some(calc.compliance),
                            Some(calc.burn_rate),
                            Some(calc.error_budget_remaining),
                        )
                    } else {
                        (None, None, None)
                    }
                } else {
                    (None, None, None)
                };

            // Look up freeze status from budget policy state
            let is_frozen = if let Some(ref bps) = state.budget_policy_state {
                let guard = bps.read().await;
                guard.get(&sl_name).map(|s| s.is_frozen)
            } else {
                None
            };

            let response = ServiceLevelDetailResponse {
                name: sl_name,
                service: spec.service,
                sli: SliDetailResponse {
                    sli_type,
                    metric: spec.sli.metric,
                    good_selector: spec.sli.good_selector,
                    total_selector: spec.sli.total_selector,
                },
                objective: ObjectiveDetailResponse {
                    target: spec.objective.target,
                    window: spec.objective.window,
                },
                burn_rate_alerts,
                condition: condition_to_string(&status.condition),
                alerts_registered: status.alerts_registered,
                last_evaluated: status.last_evaluated,
                error: status.error,
                compliance,
                burn_rate,
                error_budget_remaining,
                is_frozen,
            };

            debug!(servicelevel_name = %response.name, "Got ServiceLevel detail");
            (StatusCode::OK, Json(response)).into_response()
        }
        Err(kube::Error::Api(err)) if err.code == 404 => {
            warn!(servicelevel_name = %name, "ServiceLevel not found");
            (
                StatusCode::NOT_FOUND,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/servicelevel-not-found".to_string(),
                    title: "ServiceLevel not found".to_string(),
                    status: 404,
                    detail: format!("No ServiceLevel found with name: {}", name),
                }),
            )
                .into_response()
        }
        Err(e) => {
            warn!(error = %e, servicelevel_name = %name, "Failed to get ServiceLevel");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/servicelevel-get-failed".to_string(),
                    title: "Failed to get ServiceLevel".to_string(),
                    status: 500,
                    detail: format!("Could not retrieve ServiceLevel: {}", e),
                }),
            )
                .into_response()
        }
    }
}

/// Response for error budget status of a ServiceLevel
#[derive(Debug, Serialize)]
pub struct ErrorBudgetResponse {
    pub name: String,
    pub service: String,
    pub target: f64,
    pub error_budget_total: f64,
    pub error_budget_remaining: f64,
    pub error_budget_consumed: f64,
    pub burn_rate: f64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub projected_exhaustion_secs: Option<f64>,
    pub is_frozen: bool,
    pub triggered_policies: Vec<BudgetPolicyEventResponse>,
}

/// Response for a triggered budget policy event
#[derive(Debug, Serialize)]
pub struct BudgetPolicyEventResponse {
    pub threshold: f64,
    pub action: String,
    pub triggered_at: String,
    pub consumption_at_trigger: f64,
}

/// Get error budget status for a ServiceLevel
async fn get_servicelevel_budget(
    State(state): State<ApiState>,
    Path(name): Path<String>,
) -> impl IntoResponse {
    let servicelevels_api: Api<ServiceLevel> = Api::all((*state.client).clone());

    match servicelevels_api.get(&name).await {
        Ok(sl) => {
            let sl_name = sl.metadata.name.clone().unwrap_or_default();
            let spec = sl.spec;

            // Get live SLO data
            let (burn_rate, error_budget_remaining) = if let Some(ref cache) = state.slo_cache {
                let guard = cache.read().await;
                if let Some(calc) = guard.get(&sl_name) {
                    (calc.burn_rate, calc.error_budget_remaining)
                } else {
                    (0.0, 1.0) // Defaults when no data
                }
            } else {
                (0.0, 1.0)
            };

            let error_budget_total = 1.0 - spec.objective.target;
            let error_budget_consumed = 1.0 - error_budget_remaining;

            // Calculate projected exhaustion (reuse budget module function)
            let projected_exhaustion_secs = crate::slo::budget::projected_exhaustion_secs(
                error_budget_remaining,
                burn_rate,
                &spec.objective.window,
            );

            // Get budget policy state
            let (is_frozen, triggered_policies) = if let Some(ref bps) = state.budget_policy_state {
                let guard = bps.read().await;
                if let Some(status) = guard.get(&sl_name) {
                    let events: Vec<BudgetPolicyEventResponse> = status
                        .triggered_events
                        .iter()
                        .map(|e| BudgetPolicyEventResponse {
                            threshold: e.threshold,
                            action: e.action.clone(),
                            triggered_at: e.triggered_at.clone(),
                            consumption_at_trigger: e.current_consumption,
                        })
                        .collect();
                    (status.is_frozen, events)
                } else {
                    (false, vec![])
                }
            } else {
                (false, vec![])
            };

            let response = ErrorBudgetResponse {
                name: sl_name.clone(),
                service: spec.service,
                target: spec.objective.target,
                error_budget_total,
                error_budget_remaining,
                error_budget_consumed,
                burn_rate,
                projected_exhaustion_secs,
                is_frozen,
                triggered_policies,
            };

            debug!(servicelevel_name = %sl_name, "Got error budget status");
            (StatusCode::OK, Json(response)).into_response()
        }
        Err(kube::Error::Api(err)) if err.code == 404 => {
            warn!(servicelevel_name = %name, "ServiceLevel not found for budget query");
            (
                StatusCode::NOT_FOUND,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/servicelevel-not-found".to_string(),
                    title: "ServiceLevel not found".to_string(),
                    status: 404,
                    detail: format!("No ServiceLevel found with name: {}", name),
                }),
            )
                .into_response()
        }
        Err(e) => {
            warn!(error = %e, servicelevel_name = %name, "Failed to get ServiceLevel for budget query");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(ProblemDetails {
                    error_type: "https://beeper.io/errors/servicelevel-budget-failed".to_string(),
                    title: "Failed to get error budget status".to_string(),
                    status: 500,
                    detail: format!("Could not retrieve error budget status: {}", e),
                }),
            )
                .into_response()
        }
    }
}

/// RFC 7807 Problem Details response
#[derive(Debug, Serialize)]
pub struct ProblemDetails {
    #[serde(rename = "type")]
    pub error_type: String,
    pub title: String,
    pub status: u16,
    pub detail: String,
}

// ----- Notification Channel API -----

/// Response for a NotificationChannel in list view
#[derive(Debug, Serialize)]
pub struct NotificationChannelResponse {
    pub name: String,
    #[serde(rename = "type")]
    pub channel_type: String,
    pub credentials_secret: String,
    pub condition: String,
    pub last_validated: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,
}

/// List all NotificationChannel CRDs with their status
async fn list_notification_channels(
    State(state): State<ApiState>,
) -> Result<Json<Vec<NotificationChannelResponse>>, StatusCode> {
    let channels: Api<NotificationChannel> = Api::all((*state.client).clone());
    let channel_list = channels.list(&ListParams::default()).await.map_err(|e| {
        warn!(error = %e, "Failed to list NotificationChannels");
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    let responses: Vec<NotificationChannelResponse> = channel_list
        .items
        .iter()
        .map(|ch| {
            let name = ch
                .metadata
                .name
                .clone()
                .unwrap_or_else(|| "unknown".to_string());
            let channel_type = format!("{:?}", ch.spec.channel_type).to_lowercase();
            let condition = ch
                .status
                .as_ref()
                .and_then(|s| s.condition.as_ref())
                .map(|c| match c {
                    NotificationChannelCondition::Configured => "configured".to_string(),
                    NotificationChannelCondition::Error => "error".to_string(),
                })
                .unwrap_or_else(|| "unknown".to_string());
            let last_validated = ch.status.as_ref().and_then(|s| s.last_validated.clone());
            let error = ch.status.as_ref().and_then(|s| s.error.clone());

            NotificationChannelResponse {
                name,
                channel_type,
                credentials_secret: ch.spec.credentials_secret.clone(),
                condition,
                last_validated,
                error,
            }
        })
        .collect();

    debug!(count = responses.len(), "Listed NotificationChannels");
    Ok(Json(responses))
}

// ----- Notification Outbox API -----

/// Request to write a notification to the outbox
#[derive(Debug, Deserialize, Serialize)]
pub struct OutboxWriteRequest {
    pub investigation_id: String,
    pub event_type: String,
    pub severity: String,
    pub service: String,
    pub payload: serde_json::Value,
}

/// Response after writing a notification to the outbox
#[derive(Debug, Serialize)]
pub struct OutboxWriteResponse {
    pub status: String,
    pub message: String,
}

/// Write a notification event to the outbox collection
async fn write_notification_outbox(
    State(state): State<ApiState>,
    Json(req): Json<OutboxWriteRequest>,
) -> Result<Json<OutboxWriteResponse>, StatusCode> {
    let qdrant_endpoint = state.qdrant_endpoint.as_deref().ok_or_else(|| {
        warn!("Qdrant endpoint not configured for outbox writes");
        StatusCode::SERVICE_UNAVAILABLE
    })?;

    let now = chrono::Utc::now().to_rfc3339();
    let entry = OutboxEntry {
        investigation_id: req.investigation_id,
        event_type: req.event_type,
        severity: req.severity,
        service: req.service,
        payload: req.payload,
        status: "pending".to_string(),
        retry_count: 0,
        created_at: now.clone(),
        next_retry_at: now,
        last_error: None,
    };

    let worker = OutboxWorker::new(qdrant_endpoint.to_string());
    worker.write_notification(&entry).await.map_err(|e| {
        warn!(error = %e, "Failed to write notification to outbox");
        StatusCode::INTERNAL_SERVER_ERROR
    })?;

    debug!(
        investigation_id = %entry.investigation_id,
        "Notification queued in outbox"
    );

    Ok(Json(OutboxWriteResponse {
        status: "queued".to_string(),
        message: "Notification queued in outbox".to_string(),
    }))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_source_response_serialization() {
        let response = SourceResponse {
            name: "test".to_string(),
            source_type: "prometheus".to_string(),
            endpoint: "http://localhost:9090".to_string(),
            status: "connected".to_string(),
            last_check: Some("2026-02-10T12:00:00Z".to_string()),
            error: None,
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"type\":\"prometheus\""));
        assert!(json.contains("\"status\":\"connected\""));
    }

    #[test]
    fn test_source_response_with_error() {
        let response = SourceResponse {
            name: "loki-prod".to_string(),
            source_type: "loki".to_string(),
            endpoint: "http://loki:3100".to_string(),
            status: "error".to_string(),
            last_check: Some("2026-02-10T12:00:00Z".to_string()),
            error: Some(SourceErrorResponse {
                error_type: "connection_error".to_string(),
                message: "Connection refused".to_string(),
                details: Some("dial tcp: connection refused".to_string()),
            }),
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"status\":\"error\""));
        assert!(json.contains("\"message\":\"Connection refused\""));
    }

    #[test]
    fn test_source_error_serialization() {
        let error = SourceErrorResponse {
            error_type: "connection_refused".to_string(),
            message: "Connection refused".to_string(),
            details: Some("dial tcp: connection refused".to_string()),
        };

        let json = serde_json::to_string(&error).unwrap();
        assert!(json.contains("\"type\":\"connection_refused\""));
    }

    #[test]
    fn test_ingestion_stats_serialization() {
        let stats = IngestionStatsResponse {
            buffer_size: 10000,
            buffered_count: 150,
            dropped_count: 0,
            is_full: false,
            metrics_received: 100,
            logs_received: 50,
            sources: std::collections::HashMap::new(),
        };

        let json = serde_json::to_string(&stats).unwrap();
        assert!(json.contains("\"buffer_size\":10000"));
        assert!(json.contains("\"is_full\":false"));
        assert!(json.contains("\"metrics_received\":100"));
        assert!(json.contains("\"logs_received\":50"));
        assert!(json.contains("\"sources\""));
    }

    #[test]
    fn test_health_components_serialization() {
        let mut components = std::collections::HashMap::new();
        components.insert(
            "operator".to_string(),
            ComponentStatusResponse {
                status: "healthy".to_string(),
                message: "Running".to_string(),
            },
        );
        components.insert(
            "ingestion".to_string(),
            ComponentStatusResponse {
                status: "warning".to_string(),
                message: "Buffer: 10000/10000".to_string(),
            },
        );

        let response = HealthComponentsResponse {
            components,
            overall: "healthy".to_string(),
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"overall\":\"healthy\""));
        assert!(json.contains("\"operator\""));
        assert!(json.contains("\"ingestion\""));
    }

    #[test]
    fn test_health_components_with_llm_serialization() {
        let mut components = std::collections::HashMap::new();
        components.insert(
            "operator".to_string(),
            ComponentStatusResponse {
                status: "healthy".to_string(),
                message: "Running".to_string(),
            },
        );
        components.insert(
            "kubernetes".to_string(),
            ComponentStatusResponse {
                status: "healthy".to_string(),
                message: "Connected to API server".to_string(),
            },
        );
        components.insert(
            "ingestion".to_string(),
            ComponentStatusResponse {
                status: "healthy".to_string(),
                message: "Buffer: 50/10000".to_string(),
            },
        );
        components.insert(
            "llm".to_string(),
            ComponentStatusResponse {
                status: "healthy".to_string(),
                message: "Configured: anthropic/claude-sonnet-4".to_string(),
            },
        );

        let response = HealthComponentsResponse {
            components,
            overall: "healthy".to_string(),
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"overall\":\"healthy\""));
        assert!(json.contains("\"llm\""));
        assert!(json.contains("\"Configured: anthropic/claude-sonnet-4\""));
    }

    #[test]
    fn test_health_components_llm_unconfigured() {
        let mut components = std::collections::HashMap::new();
        components.insert(
            "llm".to_string(),
            ComponentStatusResponse {
                status: "unconfigured".to_string(),
                message: "LLM provider not configured".to_string(),
            },
        );

        let response = HealthComponentsResponse {
            components,
            overall: "healthy".to_string(),
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"status\":\"unconfigured\""));
        assert!(json.contains("\"LLM provider not configured\""));
    }

    #[test]
    fn test_detection_stats_serialization() {
        let stats = DetectionStatsResponse {
            metrics_tracked: 500,
            services_tracked: 50,
            anomalies_detected: 12,
            cooldown_entries: 3,
        };

        let json = serde_json::to_string(&stats).unwrap();
        assert!(json.contains("\"metrics_tracked\":500"));
        assert!(json.contains("\"services_tracked\":50"));
        assert!(json.contains("\"anomalies_detected\":12"));
        assert!(json.contains("\"cooldown_entries\":3"));
    }

    #[test]
    fn test_sli_type_to_string() {
        assert_eq!(sli_type_to_string(&SliType::Availability), "availability");
        assert_eq!(sli_type_to_string(&SliType::Latency), "latency");
        assert_eq!(sli_type_to_string(&SliType::ErrorRate), "error_rate");
    }

    #[test]
    fn test_condition_to_string() {
        assert_eq!(
            condition_to_string(&Some(ServiceLevelCondition::Healthy)),
            "healthy"
        );
        assert_eq!(
            condition_to_string(&Some(ServiceLevelCondition::Warning)),
            "warning"
        );
        assert_eq!(
            condition_to_string(&Some(ServiceLevelCondition::Critical)),
            "critical"
        );
        assert_eq!(condition_to_string(&None), "unknown");
    }

    #[test]
    fn test_servicelevel_response_serialization() {
        let response = ServiceLevelResponse {
            name: "payments-slo".to_string(),
            service: "payment-service".to_string(),
            sli_type: "error_rate".to_string(),
            target: 0.999,
            window: "30d".to_string(),
            condition: "healthy".to_string(),
            alerts_registered: Some(2),
            last_evaluated: Some("2026-03-14T12:00:00Z".to_string()),
            compliance: Some(0.9995),
            burn_rate: Some(0.5),
            error_budget_remaining: Some(0.5),
            is_frozen: None,
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"name\":\"payments-slo\""));
        assert!(json.contains("\"sli_type\":\"error_rate\""));
        assert!(json.contains("\"target\":0.999"));
        assert!(json.contains("\"condition\":\"healthy\""));
        assert!(json.contains("\"alerts_registered\":2"));
        assert!(json.contains("\"compliance\":0.9995"));
        assert!(json.contains("\"burn_rate\":0.5"));
        assert!(json.contains("\"error_budget_remaining\":0.5"));
        assert!(!json.contains("\"is_frozen\"")); // None should be skipped
    }

    #[test]
    fn test_servicelevel_response_no_burn_rate_data() {
        let response = ServiceLevelResponse {
            name: "auth-slo".to_string(),
            service: "auth-service".to_string(),
            sli_type: "availability".to_string(),
            target: 0.999,
            window: "30d".to_string(),
            condition: "healthy".to_string(),
            alerts_registered: Some(1),
            last_evaluated: None,
            compliance: None,
            burn_rate: None,
            error_budget_remaining: None,
            is_frozen: None,
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(!json.contains("\"compliance\""));
        assert!(!json.contains("\"burn_rate\""));
        assert!(!json.contains("\"error_budget_remaining\""));
        assert!(!json.contains("\"is_frozen\""));
    }

    #[test]
    fn test_servicelevel_detail_response_serialization() {
        let response = ServiceLevelDetailResponse {
            name: "payments-slo".to_string(),
            service: "payment-service".to_string(),
            sli: SliDetailResponse {
                sli_type: "error_rate".to_string(),
                metric: "http_requests_total".to_string(),
                good_selector: "{status=~\"2..\"}".to_string(),
                total_selector: "{}".to_string(),
            },
            objective: ObjectiveDetailResponse {
                target: 0.999,
                window: "30d".to_string(),
            },
            burn_rate_alerts: vec![BurnRateAlertResponse {
                severity: "critical".to_string(),
                short_window: "5m".to_string(),
                long_window: "6h".to_string(),
                factor: 6.0,
            }],
            condition: "healthy".to_string(),
            alerts_registered: Some(1),
            last_evaluated: Some("2026-03-14T12:00:00Z".to_string()),
            error: None,
            compliance: Some(0.998),
            burn_rate: Some(2.0),
            error_budget_remaining: Some(0.0),
            is_frozen: Some(true),
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"service\":\"payment-service\""));
        assert!(json.contains("\"type\":\"error_rate\""));
        assert!(json.contains("\"metric\":\"http_requests_total\""));
        assert!(json.contains("\"target\":0.999"));
        assert!(json.contains("\"factor\":6.0"));
        assert!(json.contains("\"condition\":\"healthy\""));
        assert!(json.contains("\"compliance\":0.998"));
        assert!(json.contains("\"burn_rate\":2.0"));
        assert!(json.contains("\"is_frozen\":true"));
    }

    #[test]
    fn test_servicelevel_list_response_serialization() {
        let response = ServiceLevelListResponse {
            service_levels: vec![ServiceLevelResponse {
                name: "auth-slo".to_string(),
                service: "auth-service".to_string(),
                sli_type: "availability".to_string(),
                target: 0.999,
                window: "7d".to_string(),
                condition: "warning".to_string(),
                alerts_registered: None,
                last_evaluated: None,
                compliance: None,
                burn_rate: None,
                error_budget_remaining: None,
                is_frozen: None,
            }],
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"service_levels\":["));
        assert!(json.contains("\"name\":\"auth-slo\""));
        assert!(json.contains("\"sli_type\":\"availability\""));
    }

    #[test]
    fn test_problem_details_serialization() {
        let problem = ProblemDetails {
            error_type: "https://beeper.io/errors/test".to_string(),
            title: "Test Error".to_string(),
            status: 500,
            detail: "Test error details".to_string(),
        };

        let json = serde_json::to_string(&problem).unwrap();
        assert!(json.contains("\"type\":\"https://beeper.io/errors/test\""));
        assert!(json.contains("\"status\":500"));
    }

    #[test]
    fn test_investigation_response_serialization() {
        let response = InvestigationResponse {
            id: "inv-abc123".to_string(),
            status: "investigating".to_string(),
            service: "payments".to_string(),
            severity: "high".to_string(),
            condition: "High error rate detected".to_string(),
            started_at: Some("2026-02-09T12:00:00Z".to_string()),
            completed_at: None,
            triggered_at: Some("2026-02-09T11:55:00Z".to_string()),
            impact_score: None,
            workflow_state: None,
            workflow_state_changed_at: None,
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"id\":\"inv-abc123\""));
        assert!(json.contains("\"status\":\"investigating\""));
        assert!(json.contains("\"service\":\"payments\""));
        assert!(json.contains("\"severity\":\"high\""));
        assert!(json.contains("\"condition\":\"High error rate detected\""));
        assert!(json.contains("\"started_at\":\"2026-02-09T12:00:00Z\""));
        assert!(json.contains("\"triggered_at\":\"2026-02-09T11:55:00Z\""));
        // completed_at should be null
        assert!(json.contains("\"completed_at\":null"));
        // impact_score is None, should be absent
        assert!(!json.contains("impact_score"));
    }

    #[test]
    fn test_investigation_response_completed() {
        let response = InvestigationResponse {
            id: "inv-xyz789".to_string(),
            status: "completed".to_string(),
            service: "api-gateway".to_string(),
            severity: "medium".to_string(),
            condition: "Latency spike".to_string(),
            started_at: Some("2026-02-09T10:00:00Z".to_string()),
            completed_at: Some("2026-02-09T10:15:00Z".to_string()),
            triggered_at: Some("2026-02-09T09:55:00Z".to_string()),
            impact_score: None,
            workflow_state: None,
            workflow_state_changed_at: None,
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"status\":\"completed\""));
        assert!(json.contains("\"completed_at\":\"2026-02-09T10:15:00Z\""));
    }

    #[test]
    fn test_investigation_response_with_impact_score() {
        let response = InvestigationResponse {
            id: "inv-impact-001".to_string(),
            status: "investigating".to_string(),
            service: "payment-service".to_string(),
            severity: "critical".to_string(),
            condition: "SLO burn rate alert".to_string(),
            started_at: Some("2026-03-14T12:00:00Z".to_string()),
            completed_at: None,
            triggered_at: Some("2026-03-14T11:55:00Z".to_string()),
            impact_score: Some(0.85),
            workflow_state: None,
            workflow_state_changed_at: None,
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"impact_score\":0.85"));
    }

    #[test]
    fn test_investigation_sort_by_impact_score() {
        let high_impact = InvestigationResponse {
            id: "inv-high".to_string(),
            status: "investigating".to_string(),
            service: "payments".to_string(),
            severity: "critical".to_string(),
            condition: "SLO alert".to_string(),
            started_at: Some("2026-03-14T12:00:00Z".to_string()),
            completed_at: None,
            triggered_at: None,
            impact_score: Some(0.85),
            workflow_state: None,
            workflow_state_changed_at: None,
        };
        let low_impact = InvestigationResponse {
            id: "inv-low".to_string(),
            status: "investigating".to_string(),
            service: "internal".to_string(),
            severity: "medium".to_string(),
            condition: "Latency".to_string(),
            started_at: Some("2026-03-14T12:01:00Z".to_string()),
            completed_at: None,
            triggered_at: None,
            impact_score: Some(0.34),
            workflow_state: None,
            workflow_state_changed_at: None,
        };
        let no_impact = InvestigationResponse {
            id: "inv-none".to_string(),
            status: "investigating".to_string(),
            service: "legacy".to_string(),
            severity: "low".to_string(),
            condition: "Spike".to_string(),
            started_at: Some("2026-03-14T12:02:00Z".to_string()),
            completed_at: None,
            triggered_at: None,
            impact_score: None,
            workflow_state: None,
            workflow_state_changed_at: None,
        };

        let mut investigations = vec![no_impact, low_impact, high_impact];

        // Apply the same sort logic as list_investigations
        investigations.sort_by(|a, b| {
            let order_cmp = status_sort_order(&a.status).cmp(&status_sort_order(&b.status));
            if order_cmp != std::cmp::Ordering::Equal {
                return order_cmp;
            }
            let impact_cmp = match (a.impact_score, b.impact_score) {
                (Some(a_s), Some(b_s)) => {
                    b_s.partial_cmp(&a_s).unwrap_or(std::cmp::Ordering::Equal)
                }
                (Some(_), None) => std::cmp::Ordering::Less,
                (None, Some(_)) => std::cmp::Ordering::Greater,
                (None, None) => std::cmp::Ordering::Equal,
            };
            if impact_cmp != std::cmp::Ordering::Equal {
                return impact_cmp;
            }
            b.started_at
                .as_deref()
                .unwrap_or("")
                .cmp(a.started_at.as_deref().unwrap_or(""))
        });

        assert_eq!(investigations[0].id, "inv-high"); // Highest impact first
        assert_eq!(investigations[1].id, "inv-low"); // Lower impact second
        assert_eq!(investigations[2].id, "inv-none"); // No impact last
    }

    #[test]
    fn test_phase_to_status_mapping() {
        assert_eq!(
            phase_to_status(&Some(InvestigationPhase::Pending)),
            "investigating"
        );
        assert_eq!(
            phase_to_status(&Some(InvestigationPhase::Running)),
            "investigating"
        );
        assert_eq!(
            phase_to_status(&Some(InvestigationPhase::Completed)),
            "completed"
        );
        assert_eq!(phase_to_status(&Some(InvestigationPhase::Failed)), "failed");
        assert_eq!(phase_to_status(&None), "investigating");
    }

    #[test]
    fn test_severity_to_string_mapping() {
        assert_eq!(severity_to_string(&Severity::Low), "low");
        assert_eq!(severity_to_string(&Severity::Medium), "medium");
        assert_eq!(severity_to_string(&Severity::High), "high");
        assert_eq!(severity_to_string(&Severity::Critical), "critical");
    }

    #[test]
    fn test_workflow_state_to_string_mapping() {
        assert_eq!(
            workflow_state_to_string(&Some(WorkflowState::Detected)),
            Some("detected".to_string())
        );
        assert_eq!(
            workflow_state_to_string(&Some(WorkflowState::Investigating)),
            Some("investigating".to_string())
        );
        assert_eq!(
            workflow_state_to_string(&Some(WorkflowState::Resolved)),
            Some("resolved".to_string())
        );
        assert_eq!(
            workflow_state_to_string(&Some(WorkflowState::Verified)),
            Some("verified".to_string())
        );
        assert_eq!(
            workflow_state_to_string(&Some(WorkflowState::Failed)),
            Some("failed".to_string())
        );
        assert_eq!(workflow_state_to_string(&None), None);
    }

    #[test]
    fn test_investigation_response_with_workflow_state() {
        let response = InvestigationResponse {
            id: "inv-ws-001".to_string(),
            status: "investigating".to_string(),
            service: "payments".to_string(),
            severity: "high".to_string(),
            condition: "High error rate".to_string(),
            started_at: Some("2026-03-18T10:00:00Z".to_string()),
            completed_at: None,
            triggered_at: None,
            impact_score: None,
            workflow_state: Some("investigating".to_string()),
            workflow_state_changed_at: Some("2026-03-18T10:00:00Z".to_string()),
        };
        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"workflow_state\":\"investigating\""));
        assert!(json.contains("\"workflow_state_changed_at\":\"2026-03-18T10:00:00Z\""));
    }

    #[test]
    fn test_status_sort_order() {
        assert!(status_sort_order("awaiting_confirmation") < status_sort_order("investigating"));
        assert!(status_sort_order("investigating") < status_sort_order("completed"));
        assert!(status_sort_order("failed") < status_sort_order("completed"));
    }

    #[test]
    fn test_investigation_query_deserialization() {
        let json = r#"{"status":"investigating","service":"payments","severity":"high"}"#;
        let query: InvestigationQuery = serde_json::from_str(json).unwrap();
        assert_eq!(query.status.as_deref(), Some("investigating"));
        assert_eq!(query.service.as_deref(), Some("payments"));
        assert_eq!(query.severity.as_deref(), Some("high"));
    }

    #[test]
    fn test_investigation_query_empty() {
        let json = r#"{}"#;
        let query: InvestigationQuery = serde_json::from_str(json).unwrap();
        assert!(query.status.is_none());
        assert!(query.service.is_none());
        assert!(query.severity.is_none());
    }

    #[test]
    fn test_investigation_detail_response_serialization() {
        let response = InvestigationDetailResponse {
            id: "inv-detail-001".to_string(),
            status: "investigating".to_string(),
            service: "payments".to_string(),
            severity: "high".to_string(),
            condition: "High error rate detected".to_string(),
            started_at: Some("2026-03-06T10:00:00Z".to_string()),
            completed_at: None,
            triggered_at: Some("2026-03-06T09:55:00Z".to_string()),
            message: Some("Correlating signals across architectural layers".to_string()),
            error: None,
            job_name: Some("inv-detail-001-job".to_string()),
            impact_score: None,
            workflow_state: None,
            workflow_state_changed_at: None,
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"id\":\"inv-detail-001\""));
        assert!(json.contains("\"status\":\"investigating\""));
        assert!(json.contains("\"message\":\"Correlating signals across architectural layers\""));
        assert!(json.contains("\"job_name\":\"inv-detail-001-job\""));
        assert!(json.contains("\"error\":null"));
        // Should include all base fields too
        assert!(json.contains("\"service\":\"payments\""));
        assert!(json.contains("\"severity\":\"high\""));
        assert!(json.contains("\"condition\":\"High error rate detected\""));
    }

    #[test]
    fn test_investigation_detail_response_with_error() {
        let response = InvestigationDetailResponse {
            id: "inv-fail-001".to_string(),
            status: "failed".to_string(),
            service: "api-gateway".to_string(),
            severity: "critical".to_string(),
            condition: "Service unreachable".to_string(),
            started_at: Some("2026-03-06T10:00:00Z".to_string()),
            completed_at: None,
            triggered_at: None,
            message: Some("Generating root cause hypothesis".to_string()),
            error: Some("LLM provider timeout".to_string()),
            job_name: None,
            impact_score: None,
            workflow_state: None,
            workflow_state_changed_at: None,
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"status\":\"failed\""));
        assert!(json.contains("\"error\":\"LLM provider timeout\""));
        assert!(json.contains("\"message\":\"Generating root cause hypothesis\""));
        assert!(json.contains("\"job_name\":null"));
    }

    #[test]
    fn test_investigation_detail_response_completed() {
        let response = InvestigationDetailResponse {
            id: "inv-done-001".to_string(),
            status: "completed".to_string(),
            service: "checkout".to_string(),
            severity: "medium".to_string(),
            condition: "Latency spike".to_string(),
            started_at: Some("2026-03-06T10:00:00Z".to_string()),
            completed_at: Some("2026-03-06T10:12:00Z".to_string()),
            triggered_at: Some("2026-03-06T09:58:00Z".to_string()),
            message: Some("Documenting investigation findings".to_string()),
            error: None,
            job_name: Some("inv-done-001-job".to_string()),
            impact_score: None,
            workflow_state: None,
            workflow_state_changed_at: None,
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"status\":\"completed\""));
        assert!(json.contains("\"completed_at\":\"2026-03-06T10:12:00Z\""));
        assert!(json.contains("\"message\":\"Documenting investigation findings\""));
    }

    #[test]
    fn test_investigation_sort_started_at_fallback() {
        // When status and impact_score are identical, sort by started_at descending
        let earlier = InvestigationResponse {
            id: "inv-earlier".to_string(),
            status: "investigating".to_string(),
            service: "svc-a".to_string(),
            severity: "high".to_string(),
            condition: "Alert".to_string(),
            started_at: Some("2026-03-14T10:00:00Z".to_string()),
            completed_at: None,
            triggered_at: None,
            impact_score: Some(0.5),
            workflow_state: None,
            workflow_state_changed_at: None,
        };
        let later = InvestigationResponse {
            id: "inv-later".to_string(),
            status: "investigating".to_string(),
            service: "svc-b".to_string(),
            severity: "high".to_string(),
            condition: "Alert".to_string(),
            started_at: Some("2026-03-14T12:00:00Z".to_string()),
            completed_at: None,
            triggered_at: None,
            impact_score: Some(0.5),
            workflow_state: None,
            workflow_state_changed_at: None,
        };

        let mut investigations = vec![earlier, later];

        investigations.sort_by(|a, b| {
            let order_cmp = status_sort_order(&a.status).cmp(&status_sort_order(&b.status));
            if order_cmp != std::cmp::Ordering::Equal {
                return order_cmp;
            }
            let impact_cmp = match (a.impact_score, b.impact_score) {
                (Some(a_s), Some(b_s)) => {
                    b_s.partial_cmp(&a_s).unwrap_or(std::cmp::Ordering::Equal)
                }
                (Some(_), None) => std::cmp::Ordering::Less,
                (None, Some(_)) => std::cmp::Ordering::Greater,
                (None, None) => std::cmp::Ordering::Equal,
            };
            if impact_cmp != std::cmp::Ordering::Equal {
                return impact_cmp;
            }
            b.started_at
                .as_deref()
                .unwrap_or("")
                .cmp(a.started_at.as_deref().unwrap_or(""))
        });

        // Later started_at should come first (descending)
        assert_eq!(investigations[0].id, "inv-later");
        assert_eq!(investigations[1].id, "inv-earlier");
    }

    #[test]
    fn test_investigation_detail_404_problem_details() {
        let problem = ProblemDetails {
            error_type: "https://beeper.io/errors/investigation-not-found".to_string(),
            title: "Investigation not found".to_string(),
            status: 404,
            detail: "No investigation found with ID: inv-nonexistent".to_string(),
        };

        let json = serde_json::to_string(&problem).unwrap();
        assert!(json.contains("\"status\":404"));
        assert!(json.contains("\"title\":\"Investigation not found\""));
        assert!(json.contains("inv-nonexistent"));
    }

    #[test]
    fn test_source_list_response_serialization() {
        let response = SourceListResponse {
            sources: vec![SourceResponse {
                name: "prometheus-main".to_string(),
                source_type: "prometheus".to_string(),
                endpoint: "http://prometheus:9090".to_string(),
                status: "connected".to_string(),
                last_check: Some("2026-02-10T12:00:00Z".to_string()),
                error: None,
            }],
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"sources\":["));
        assert!(json.contains("\"name\":\"prometheus-main\""));
    }

    #[test]
    fn test_resolution_confirm_request_with_comment() {
        let req = ResolutionConfirmRequest {
            comment: Some("Restarted service successfully".to_string()),
        };
        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("\"comment\":\"Restarted service successfully\""));
    }

    #[test]
    fn test_resolution_confirm_request_without_comment() {
        let req = ResolutionConfirmRequest { comment: None };
        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("\"comment\":null"));
    }

    #[test]
    fn test_resolution_reject_request_full() {
        let req = ResolutionRejectRequest {
            reason: "hypothesis_incorrect".to_string(),
            reason_details: Some("Root cause was in the cache layer".to_string()),
            correction: Some("Clear Redis cache and restart".to_string()),
        };
        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("\"reason\":\"hypothesis_incorrect\""));
        assert!(json.contains("\"reason_details\":\"Root cause was in the cache layer\""));
        assert!(json.contains("\"correction\":\"Clear Redis cache and restart\""));
    }

    #[test]
    fn test_resolution_reject_request_minimal() {
        let req = ResolutionRejectRequest {
            reason: "insufficient_evidence".to_string(),
            reason_details: None,
            correction: None,
        };
        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("\"reason\":\"insufficient_evidence\""));
        assert!(json.contains("\"reason_details\":null"));
        assert!(json.contains("\"correction\":null"));
    }

    #[test]
    fn test_phase_to_status_awaiting_confirmation() {
        assert_eq!(
            phase_to_status(&Some(InvestigationPhase::AwaitingConfirmation)),
            "awaiting_confirmation"
        );
    }

    #[test]
    fn test_resolution_action_response_serialization() {
        let resp = ResolutionActionResponse {
            status: "confirmed".to_string(),
            message: "Investigation inv-123 resolution confirmed".to_string(),
        };
        let json = serde_json::to_string(&resp).unwrap();
        assert!(json.contains("\"status\":\"confirmed\""));
        assert!(json.contains("inv-123"));
    }

    #[test]
    fn test_resolution_confirm_request_deserialization() {
        let json = r#"{"comment":"Looks good"}"#;
        let req: ResolutionConfirmRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.comment.as_deref(), Some("Looks good"));

        let json_empty = r#"{}"#;
        let req2: ResolutionConfirmRequest = serde_json::from_str(json_empty).unwrap();
        assert!(req2.comment.is_none());
    }

    #[test]
    fn test_resolution_reject_request_deserialization() {
        let json = r#"{"reason":"better_alternative","reason_details":"Use a different approach","correction":"Restart the pod"}"#;
        let req: ResolutionRejectRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.reason, "better_alternative");
        assert_eq!(
            req.reason_details.as_deref(),
            Some("Use a different approach")
        );
        assert_eq!(req.correction.as_deref(), Some("Restart the pod"));
    }

    #[test]
    fn test_resolution_resolve_request_all_fields() {
        let req = ResolutionResolveRequest {
            outcome: "resolved".to_string(),
            accuracy_rating: Some("correct".to_string()),
            resolution_notes: Some("Restarted payment service".to_string()),
            escalation_target: None,
            not_an_issue_reason: None,
        };
        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("\"outcome\":\"resolved\""));
        assert!(json.contains("\"accuracy_rating\":\"correct\""));
        assert!(json.contains("\"resolution_notes\":\"Restarted payment service\""));
    }

    #[test]
    fn test_resolution_resolve_request_minimal() {
        let req = ResolutionResolveRequest {
            outcome: "unresolved".to_string(),
            accuracy_rating: None,
            resolution_notes: None,
            escalation_target: None,
            not_an_issue_reason: None,
        };
        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("\"outcome\":\"unresolved\""));
        assert!(json.contains("\"accuracy_rating\":null"));
    }

    #[test]
    fn test_resolution_resolve_request_escalated() {
        let req = ResolutionResolveRequest {
            outcome: "escalated".to_string(),
            accuracy_rating: None,
            resolution_notes: Some("Needs platform team".to_string()),
            escalation_target: Some("platform-team".to_string()),
            not_an_issue_reason: None,
        };
        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("\"outcome\":\"escalated\""));
        assert!(json.contains("\"escalation_target\":\"platform-team\""));
    }

    #[test]
    fn test_resolution_resolve_request_not_an_issue() {
        let req = ResolutionResolveRequest {
            outcome: "not_an_issue".to_string(),
            accuracy_rating: None,
            resolution_notes: None,
            escalation_target: None,
            not_an_issue_reason: Some("false_positive".to_string()),
        };
        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("\"outcome\":\"not_an_issue\""));
        assert!(json.contains("\"not_an_issue_reason\":\"false_positive\""));
    }

    #[test]
    fn test_resolution_resolve_request_deserialization() {
        let json = r#"{"outcome":"resolved","accuracy_rating":"partially_correct","resolution_notes":"Fixed after retry"}"#;
        let req: ResolutionResolveRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.outcome, "resolved");
        assert_eq!(req.accuracy_rating.as_deref(), Some("partially_correct"));
        assert_eq!(req.resolution_notes.as_deref(), Some("Fixed after retry"));
        assert!(req.escalation_target.is_none());
        assert!(req.not_an_issue_reason.is_none());
    }

    #[test]
    fn test_resolution_resolve_request_deserialization_minimal() {
        let json = r#"{"outcome":"unresolved"}"#;
        let req: ResolutionResolveRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.outcome, "unresolved");
        assert!(req.accuracy_rating.is_none());
    }

    #[test]
    fn test_error_budget_response_serialization() {
        let response = ErrorBudgetResponse {
            name: "payments-slo".to_string(),
            service: "payment-service".to_string(),
            target: 0.999,
            error_budget_total: 0.001,
            error_budget_remaining: 0.00085,
            error_budget_consumed: 0.15,
            burn_rate: 1.5,
            projected_exhaustion_secs: Some(3600.0),
            is_frozen: false,
            triggered_policies: vec![],
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"name\":\"payments-slo\""));
        assert!(json.contains("\"service\":\"payment-service\""));
        assert!(json.contains("\"target\":0.999"));
        assert!(json.contains("\"error_budget_total\":0.001"));
        assert!(json.contains("\"burn_rate\":1.5"));
        assert!(json.contains("\"projected_exhaustion_secs\":3600.0"));
        assert!(json.contains("\"is_frozen\":false"));
        assert!(json.contains("\"triggered_policies\":[]"));
    }

    #[test]
    fn test_error_budget_response_with_triggered_policies() {
        let response = ErrorBudgetResponse {
            name: "auth-slo".to_string(),
            service: "auth-service".to_string(),
            target: 0.999,
            error_budget_total: 0.001,
            error_budget_remaining: 0.0002,
            error_budget_consumed: 0.80,
            burn_rate: 4.0,
            projected_exhaustion_secs: Some(900.0),
            is_frozen: true,
            triggered_policies: vec![
                BudgetPolicyEventResponse {
                    threshold: 0.5,
                    action: "notify".to_string(),
                    triggered_at: "2026-03-14T10:00:00Z".to_string(),
                    consumption_at_trigger: 0.5,
                },
                BudgetPolicyEventResponse {
                    threshold: 0.75,
                    action: "freeze".to_string(),
                    triggered_at: "2026-03-14T10:30:00Z".to_string(),
                    consumption_at_trigger: 0.76,
                },
            ],
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"is_frozen\":true"));
        assert!(json.contains("\"action\":\"notify\""));
        assert!(json.contains("\"action\":\"freeze\""));
        assert!(json.contains("\"threshold\":0.5"));
        assert!(json.contains("\"threshold\":0.75"));
        assert!(json.contains("\"consumption_at_trigger\":0.76"));
    }

    #[test]
    fn test_error_budget_response_no_projected_exhaustion() {
        let response = ErrorBudgetResponse {
            name: "gateway-slo".to_string(),
            service: "api-gateway".to_string(),
            target: 0.99,
            error_budget_total: 0.01,
            error_budget_remaining: 0.01,
            error_budget_consumed: 0.0,
            burn_rate: 0.0,
            projected_exhaustion_secs: None,
            is_frozen: false,
            triggered_policies: vec![],
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(!json.contains("\"projected_exhaustion_secs\"")); // None should be skipped
        assert!(json.contains("\"error_budget_consumed\":0.0"));
    }

    #[test]
    fn test_budget_policy_event_response_serialization() {
        let event = BudgetPolicyEventResponse {
            threshold: 0.8,
            action: "notify".to_string(),
            triggered_at: "2026-03-14T12:00:00Z".to_string(),
            consumption_at_trigger: 0.82,
        };

        let json = serde_json::to_string(&event).unwrap();
        assert!(json.contains("\"threshold\":0.8"));
        assert!(json.contains("\"action\":\"notify\""));
        assert!(json.contains("\"triggered_at\":\"2026-03-14T12:00:00Z\""));
        assert!(json.contains("\"consumption_at_trigger\":0.82"));
    }

    #[test]
    fn test_servicelevel_response_with_frozen() {
        let response = ServiceLevelResponse {
            name: "frozen-slo".to_string(),
            service: "payment-service".to_string(),
            sli_type: "availability".to_string(),
            target: 0.999,
            window: "30d".to_string(),
            condition: "critical".to_string(),
            alerts_registered: None,
            last_evaluated: None,
            compliance: Some(0.995),
            burn_rate: Some(5.0),
            error_budget_remaining: Some(0.1),
            is_frozen: Some(true),
        };

        let json = serde_json::to_string(&response).unwrap();
        assert!(json.contains("\"is_frozen\":true"));
        assert!(json.contains("\"name\":\"frozen-slo\""));
        assert!(json.contains("\"burn_rate\":5.0"));
    }

    // ----- Outbox Write API tests -----

    #[test]
    fn test_outbox_write_request_deserialization() {
        let json = r#"{
            "investigation_id": "inv-001",
            "event_type": "investigation_started",
            "severity": "high",
            "service": "payment-service",
            "payload": {"summary": "High error rate detected"}
        }"#;

        let req: OutboxWriteRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.investigation_id, "inv-001");
        assert_eq!(req.event_type, "investigation_started");
        assert_eq!(req.severity, "high");
        assert_eq!(req.service, "payment-service");
        assert_eq!(req.payload["summary"], "High error rate detected");
    }

    #[test]
    fn test_outbox_write_request_serialization() {
        let req = OutboxWriteRequest {
            investigation_id: "inv-002".to_string(),
            event_type: "investigation_completed".to_string(),
            severity: "medium".to_string(),
            service: "auth-service".to_string(),
            payload: serde_json::json!({"rca": "Memory leak in auth module"}),
        };

        let json = serde_json::to_string(&req).unwrap();
        assert!(json.contains("\"investigation_id\":\"inv-002\""));
        assert!(json.contains("\"event_type\":\"investigation_completed\""));
        assert!(json.contains("\"severity\":\"medium\""));
        assert!(json.contains("\"service\":\"auth-service\""));
    }

    #[test]
    fn test_outbox_write_request_fix_proposed() {
        let json = r#"{
            "investigation_id": "inv-003",
            "event_type": "fix_proposed",
            "severity": "critical",
            "service": "api-gateway",
            "payload": {"fix": "Restart pod", "confidence": 0.92}
        }"#;

        let req: OutboxWriteRequest = serde_json::from_str(json).unwrap();
        assert_eq!(req.event_type, "fix_proposed");
        assert_eq!(req.severity, "critical");
        assert_eq!(req.payload["confidence"], 0.92);
    }

    #[test]
    fn test_outbox_write_response_serialization() {
        let resp = OutboxWriteResponse {
            status: "queued".to_string(),
            message: "Notification queued in outbox".to_string(),
        };

        let json = serde_json::to_string(&resp).unwrap();
        assert!(json.contains("\"status\":\"queued\""));
        assert!(json.contains("\"message\":\"Notification queued in outbox\""));
    }

    #[test]
    fn test_notification_channel_response_serialization() {
        let resp = NotificationChannelResponse {
            name: "slack-sre".to_string(),
            channel_type: "slack".to_string(),
            credentials_secret: "slack-token".to_string(),
            condition: "configured".to_string(),
            last_validated: Some("2026-03-14T12:00:00Z".to_string()),
            error: None,
        };

        let json = serde_json::to_string(&resp).unwrap();
        assert!(json.contains("\"name\":\"slack-sre\""));
        assert!(json.contains("\"type\":\"slack\""));
        assert!(json.contains("\"condition\":\"configured\""));
        assert!(!json.contains("\"error\""));
    }

    #[test]
    fn test_notification_channel_response_with_error() {
        let resp = NotificationChannelResponse {
            name: "pd-oncall".to_string(),
            channel_type: "pagerduty".to_string(),
            credentials_secret: "pd-token".to_string(),
            condition: "error".to_string(),
            last_validated: Some("2026-03-14T12:00:00Z".to_string()),
            error: Some("Secret not found".to_string()),
        };

        let json = serde_json::to_string(&resp).unwrap();
        assert!(json.contains("\"condition\":\"error\""));
        assert!(json.contains("\"error\":\"Secret not found\""));
    }
}

#[cfg(test)]
mod integration_tests {
    use super::*;

    fn create_test_buffer() -> Arc<IngestionBuffer> {
        Arc::new(IngestionBuffer::new(1000))
    }

    #[tokio::test]
    async fn test_ingestion_stats_endpoint() {
        // Create a mock client - we can't easily create a real one in tests
        // So we test the response structure directly
        let mut sources = std::collections::HashMap::new();
        sources.insert(
            "prometheus".to_string(),
            SourceHealthResponse {
                bytes_received: 1024,
                parse_errors: 0,
                last_received_ns: 1234567890,
            },
        );

        let stats = IngestionStatsResponse {
            buffer_size: 1000,
            buffered_count: 0,
            dropped_count: 0,
            is_full: false,
            metrics_received: 42,
            logs_received: 17,
            sources,
        };

        let json = serde_json::to_string(&stats).unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&json).unwrap();

        assert_eq!(parsed["buffer_size"], 1000);
        assert_eq!(parsed["buffered_count"], 0);
        assert_eq!(parsed["dropped_count"], 0);
        assert_eq!(parsed["is_full"], false);
        assert_eq!(parsed["metrics_received"], 42);
        assert_eq!(parsed["logs_received"], 17);
        assert_eq!(parsed["sources"]["prometheus"]["bytes_received"], 1024);
        assert_eq!(parsed["sources"]["prometheus"]["parse_errors"], 0);
    }

    #[tokio::test]
    async fn test_buffer_stats_after_ingestion() {
        let buffer = create_test_buffer();

        // Add some items
        use crate::ingestion::buffer::{IngestionData, MetricSample};
        use std::collections::HashMap;

        for i in 0..5 {
            let sample = IngestionData::Metric(MetricSample {
                name: format!("test_metric_{}", i),
                labels: HashMap::new(),
                value: i as f64,
                timestamp_ms: 1234567890000,
            });
            buffer.try_send(sample).unwrap();
        }

        // Verify counts
        assert_eq!(buffer.buffered_count(), 5);
        assert_eq!(buffer.dropped_count(), 0);
        assert!(!buffer.is_full());
    }
}
