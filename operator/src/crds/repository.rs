//! Repository CRD definition
//!
//! Represents a code repository registered with Beeper for auto-PR generation.
//! Admins configure repository URL, Git provider (GitHub/GitLab), credentials,
//! branch policies, and coding standards via this CRD.
//! The operator reconciles it, validates the spec, checks credentials, and reports status.

use kube::CustomResource;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

/// Specification for a Repository resource
#[derive(CustomResource, Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[kube(
    group = "beeper.dev",
    version = "v1",
    kind = "Repository",
    namespaced,
    status = "RepositoryStatus",
    shortname = "repo"
)]
#[serde(rename_all = "snake_case")]
pub struct RepositorySpec {
    /// Repository URL (e.g., "https://github.com/org/service")
    pub url: String,

    /// Git provider type
    pub provider: RepositoryProvider,

    /// Name of the K8s Secret containing per-repo scoped credentials (NFR9)
    pub credentials_secret: String,

    /// Branch policy configuration
    #[serde(skip_serializing_if = "Option::is_none")]
    pub branch_policy: Option<BranchPolicy>,

    /// Coding standards for auto-generated fixes
    #[serde(skip_serializing_if = "Option::is_none")]
    pub coding_standards: Option<CodingStandards>,
}

/// Git provider type
#[derive(Deserialize, Serialize, Clone, Debug, JsonSchema, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum RepositoryProvider {
    Github,
    Gitlab,
}

/// Branch policy configuration for auto-PR generation
#[derive(Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct BranchPolicy {
    /// Base branch for PRs (defaults to "main" in controller logic)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub base_branch: Option<String>,

    /// Prefix for fix branches (defaults to "beeper/")
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pr_branch_prefix: Option<String>,

    /// Whether PRs are required (defaults to true)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub require_pr: Option<bool>,
}

/// Coding standards configuration for auto-generated fixes
#[derive(Deserialize, Serialize, Clone, Debug, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct CodingStandards {
    /// Programming language
    #[serde(skip_serializing_if = "Option::is_none")]
    pub language: Option<String>,

    /// Linter tool (e.g., "ruff", "eslint")
    #[serde(skip_serializing_if = "Option::is_none")]
    pub linter: Option<String>,

    /// Test command (e.g., "pytest", "cargo test")
    #[serde(skip_serializing_if = "Option::is_none")]
    pub test_command: Option<String>,
}

/// Current condition of a Repository resource
#[derive(Deserialize, Serialize, Clone, Debug, Default, JsonSchema, PartialEq)]
#[serde(rename_all = "lowercase")]
pub enum RepositoryCondition {
    /// Initial state — not yet checked
    #[default]
    Pending,
    /// Repository accessible and credentials valid
    Connected,
    /// Credentials secret missing or invalid
    #[serde(rename = "auth_error")]
    AuthError,
    /// Repository URL not found or inaccessible
    #[serde(rename = "not_found")]
    NotFound,
    /// General error (e.g., validation failure)
    Error,
}

/// Status of a Repository resource
#[derive(Deserialize, Serialize, Clone, Debug, Default, JsonSchema)]
#[serde(rename_all = "snake_case")]
pub struct RepositoryStatus {
    /// Current condition of the repository connection
    #[serde(skip_serializing_if = "Option::is_none")]
    pub condition: Option<RepositoryCondition>,

    /// Last time the repository was checked (ISO 8601)
    #[serde(skip_serializing_if = "Option::is_none")]
    pub last_checked: Option<String>,

    /// Error message if validation or connectivity check failed
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<String>,

    /// Detected default branch from repository
    #[serde(skip_serializing_if = "Option::is_none")]
    pub default_branch_detected: Option<String>,
}

/// Validate a RepositorySpec and return an error message if invalid
pub fn validate_spec(spec: &RepositorySpec) -> Result<(), String> {
    if spec.url.is_empty() {
        return Err("spec.url must not be empty".to_string());
    }

    if spec.credentials_secret.is_empty() {
        return Err("spec.credentials_secret must not be empty".to_string());
    }

    // Validate branch policy if present
    if let Some(branch_policy) = &spec.branch_policy {
        if let Some(ref base_branch) = branch_policy.base_branch {
            if base_branch.is_empty() {
                return Err("spec.branch_policy.base_branch must not be empty when specified".to_string());
            }
        }
        if let Some(ref prefix) = branch_policy.pr_branch_prefix {
            if prefix.is_empty() {
                return Err("spec.branch_policy.pr_branch_prefix must not be empty when specified".to_string());
            }
        }
    }

    // Validate coding standards if present
    if let Some(coding_standards) = &spec.coding_standards {
        if let Some(ref language) = coding_standards.language {
            if language.is_empty() {
                return Err("spec.coding_standards.language must not be empty when specified".to_string());
            }
        }
        if let Some(ref linter) = coding_standards.linter {
            if linter.is_empty() {
                return Err("spec.coding_standards.linter must not be empty when specified".to_string());
            }
        }
        if let Some(ref test_command) = coding_standards.test_command {
            if test_command.is_empty() {
                return Err("spec.coding_standards.test_command must not be empty when specified".to_string());
            }
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_github_spec() -> RepositorySpec {
        RepositorySpec {
            url: "https://github.com/org/payment-service".to_string(),
            provider: RepositoryProvider::Github,
            credentials_secret: "github-token-payments".to_string(),
            branch_policy: Some(BranchPolicy {
                base_branch: Some("main".to_string()),
                pr_branch_prefix: Some("beeper/".to_string()),
                require_pr: Some(true),
            }),
            coding_standards: Some(CodingStandards {
                language: Some("python".to_string()),
                linter: Some("ruff".to_string()),
                test_command: Some("pytest".to_string()),
            }),
        }
    }

    fn sample_gitlab_spec() -> RepositorySpec {
        RepositorySpec {
            url: "https://gitlab.com/org/api-service".to_string(),
            provider: RepositoryProvider::Gitlab,
            credentials_secret: "gitlab-token-api".to_string(),
            branch_policy: None,
            coding_standards: None,
        }
    }

    // ----- Serialization tests -----

    #[test]
    fn test_github_spec_serialization() {
        let spec = sample_github_spec();
        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"url\":\"https://github.com/org/payment-service\""));
        assert!(json.contains("\"provider\":\"github\""));
        assert!(json.contains("\"credentials_secret\":\"github-token-payments\""));
    }

    #[test]
    fn test_gitlab_spec_serialization() {
        let spec = sample_gitlab_spec();
        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"provider\":\"gitlab\""));
        assert!(json.contains("\"credentials_secret\":\"gitlab-token-api\""));
    }

    #[test]
    fn test_spec_without_optional_fields_omits_them() {
        let spec = sample_gitlab_spec();
        let json = serde_json::to_string(&spec).unwrap();
        assert!(!json.contains("branch_policy"));
        assert!(!json.contains("coding_standards"));
    }

    #[test]
    fn test_branch_policy_serialization() {
        let spec = sample_github_spec();
        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"base_branch\":\"main\""));
        assert!(json.contains("\"pr_branch_prefix\":\"beeper/\""));
        assert!(json.contains("\"require_pr\":true"));
    }

    #[test]
    fn test_coding_standards_serialization() {
        let spec = sample_github_spec();
        let json = serde_json::to_string(&spec).unwrap();
        assert!(json.contains("\"language\":\"python\""));
        assert!(json.contains("\"linter\":\"ruff\""));
        assert!(json.contains("\"test_command\":\"pytest\""));
    }

    #[test]
    fn test_branch_policy_optional_fields_omitted() {
        let bp = BranchPolicy {
            base_branch: None,
            pr_branch_prefix: None,
            require_pr: None,
        };
        let json = serde_json::to_string(&bp).unwrap();
        assert!(!json.contains("base_branch"));
        assert!(!json.contains("pr_branch_prefix"));
        assert!(!json.contains("require_pr"));
    }

    #[test]
    fn test_coding_standards_optional_fields_omitted() {
        let cs = CodingStandards {
            language: None,
            linter: None,
            test_command: None,
        };
        let json = serde_json::to_string(&cs).unwrap();
        assert!(!json.contains("language"));
        assert!(!json.contains("linter"));
        assert!(!json.contains("test_command"));
    }

    // ----- Deserialization tests -----

    #[test]
    fn test_provider_deserialization() {
        let github: RepositoryProvider = serde_json::from_str("\"github\"").unwrap();
        assert_eq!(github, RepositoryProvider::Github);

        let gitlab: RepositoryProvider = serde_json::from_str("\"gitlab\"").unwrap();
        assert_eq!(gitlab, RepositoryProvider::Gitlab);
    }

    #[test]
    fn test_condition_deserialization() {
        let pending: RepositoryCondition = serde_json::from_str("\"pending\"").unwrap();
        assert_eq!(pending, RepositoryCondition::Pending);

        let connected: RepositoryCondition = serde_json::from_str("\"connected\"").unwrap();
        assert_eq!(connected, RepositoryCondition::Connected);

        let auth_error: RepositoryCondition = serde_json::from_str("\"auth_error\"").unwrap();
        assert_eq!(auth_error, RepositoryCondition::AuthError);

        let not_found: RepositoryCondition = serde_json::from_str("\"not_found\"").unwrap();
        assert_eq!(not_found, RepositoryCondition::NotFound);

        let error: RepositoryCondition = serde_json::from_str("\"error\"").unwrap();
        assert_eq!(error, RepositoryCondition::Error);
    }

    #[test]
    fn test_condition_default() {
        let condition: RepositoryCondition = Default::default();
        assert_eq!(condition, RepositoryCondition::Pending);
    }

    #[test]
    fn test_spec_deserialization_full() {
        let json = r#"{
            "url": "https://github.com/org/service",
            "provider": "github",
            "credentials_secret": "my-token",
            "branch_policy": {
                "base_branch": "main",
                "pr_branch_prefix": "beeper/fix-",
                "require_pr": true
            },
            "coding_standards": {
                "language": "python",
                "linter": "ruff",
                "test_command": "pytest"
            }
        }"#;

        let spec: RepositorySpec = serde_json::from_str(json).unwrap();
        assert_eq!(spec.url, "https://github.com/org/service");
        assert_eq!(spec.provider, RepositoryProvider::Github);
        assert_eq!(spec.credentials_secret, "my-token");
        let bp = spec.branch_policy.unwrap();
        assert_eq!(bp.base_branch.unwrap(), "main");
        assert_eq!(bp.pr_branch_prefix.unwrap(), "beeper/fix-");
        assert_eq!(bp.require_pr.unwrap(), true);
        let cs = spec.coding_standards.unwrap();
        assert_eq!(cs.language.unwrap(), "python");
        assert_eq!(cs.linter.unwrap(), "ruff");
        assert_eq!(cs.test_command.unwrap(), "pytest");
    }

    #[test]
    fn test_spec_deserialization_minimal() {
        let json = r#"{
            "url": "https://gitlab.com/org/api",
            "provider": "gitlab",
            "credentials_secret": "gl-token"
        }"#;

        let spec: RepositorySpec = serde_json::from_str(json).unwrap();
        assert_eq!(spec.provider, RepositoryProvider::Gitlab);
        assert!(spec.branch_policy.is_none());
        assert!(spec.coding_standards.is_none());
    }

    // ----- Status tests -----

    #[test]
    fn test_status_serialization_connected() {
        let status = RepositoryStatus {
            condition: Some(RepositoryCondition::Connected),
            last_checked: Some("2026-03-16T12:00:00Z".to_string()),
            error: None,
            default_branch_detected: None,
        };
        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"condition\":\"connected\""));
        assert!(json.contains("\"last_checked\":\"2026-03-16T12:00:00Z\""));
        assert!(!json.contains("error"));
        assert!(!json.contains("default_branch_detected"));
    }

    #[test]
    fn test_status_serialization_auth_error() {
        let status = RepositoryStatus {
            condition: Some(RepositoryCondition::AuthError),
            last_checked: Some("2026-03-16T12:00:00Z".to_string()),
            error: Some("credentials secret not found".to_string()),
            default_branch_detected: None,
        };
        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"condition\":\"auth_error\""));
        assert!(json.contains("\"error\":\"credentials secret not found\""));
    }

    #[test]
    fn test_status_empty_default() {
        let status = RepositoryStatus::default();
        let json = serde_json::to_string(&status).unwrap();
        assert_eq!(json, "{}");
    }

    // ----- Validation tests -----

    #[test]
    fn test_validate_github_spec_valid() {
        let spec = sample_github_spec();
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_gitlab_spec_valid() {
        let spec = sample_gitlab_spec();
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_empty_url() {
        let mut spec = sample_github_spec();
        spec.url = "".to_string();
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("url must not be empty"));
    }

    #[test]
    fn test_validate_empty_credentials_secret() {
        let mut spec = sample_github_spec();
        spec.credentials_secret = "".to_string();
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("credentials_secret must not be empty"));
    }

    #[test]
    fn test_validate_empty_base_branch() {
        let mut spec = sample_github_spec();
        spec.branch_policy.as_mut().unwrap().base_branch = Some("".to_string());
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("base_branch must not be empty"));
    }

    #[test]
    fn test_validate_empty_pr_branch_prefix() {
        let mut spec = sample_github_spec();
        spec.branch_policy.as_mut().unwrap().pr_branch_prefix = Some("".to_string());
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("pr_branch_prefix must not be empty"));
    }

    #[test]
    fn test_validate_empty_language() {
        let mut spec = sample_github_spec();
        spec.coding_standards.as_mut().unwrap().language = Some("".to_string());
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("language must not be empty"));
    }

    #[test]
    fn test_validate_empty_linter() {
        let mut spec = sample_github_spec();
        spec.coding_standards.as_mut().unwrap().linter = Some("".to_string());
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("linter must not be empty"));
    }

    #[test]
    fn test_validate_empty_test_command() {
        let mut spec = sample_github_spec();
        spec.coding_standards.as_mut().unwrap().test_command = Some("".to_string());
        let result = validate_spec(&spec);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("test_command must not be empty"));
    }

    #[test]
    fn test_validate_none_branch_policy_is_ok() {
        let spec = sample_gitlab_spec();
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_branch_policy_with_all_none_fields() {
        let mut spec = sample_github_spec();
        spec.branch_policy = Some(BranchPolicy {
            base_branch: None,
            pr_branch_prefix: None,
            require_pr: None,
        });
        assert!(validate_spec(&spec).is_ok());
    }

    #[test]
    fn test_validate_coding_standards_with_all_none_fields() {
        let mut spec = sample_github_spec();
        spec.coding_standards = Some(CodingStandards {
            language: None,
            linter: None,
            test_command: None,
        });
        assert!(validate_spec(&spec).is_ok());
    }
}
