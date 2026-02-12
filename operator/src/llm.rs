//! LLM provider configuration and management
//!
//! This module provides configuration structures and validation for LLM providers.
//! Supports multiple providers: Anthropic, OpenAI, Azure OpenAI, and Ollama.

use k8s_openapi::api::core::v1::Secret;
use kube::{Api, Client};
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use thiserror::Error;
use tracing::{debug, warn};

/// Supported LLM providers
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum LlmProvider {
    Anthropic,
    Openai,
    Azure,
    Ollama,
}

impl LlmProvider {
    /// Returns true if this provider requires an API key
    pub fn requires_api_key(&self) -> bool {
        match self {
            LlmProvider::Anthropic | LlmProvider::Openai | LlmProvider::Azure => true,
            LlmProvider::Ollama => false,
        }
    }

    /// Returns the default model for this provider
    pub fn default_model(&self) -> &'static str {
        match self {
            LlmProvider::Anthropic => "claude-sonnet-4",
            LlmProvider::Openai => "gpt-4o",
            LlmProvider::Azure => "gpt-4",
            LlmProvider::Ollama => "llama3",
        }
    }

    /// Validates that the model name is in a valid format for this provider
    pub fn validate_model(&self, model: &str) -> Result<(), LlmConfigError> {
        if model.is_empty() {
            return Err(LlmConfigError::InvalidModel {
                model: model.to_string(),
                reason: "Model name cannot be empty".to_string(),
            });
        }

        match self {
            LlmProvider::Anthropic => {
                // Anthropic models: claude-*, claude-3-*, claude-sonnet-4, etc.
                if !model.starts_with("claude") {
                    return Err(LlmConfigError::InvalidModel {
                        model: model.to_string(),
                        reason: "Anthropic models must start with 'claude'".to_string(),
                    });
                }
            }
            LlmProvider::Openai => {
                // OpenAI models: gpt-*, o1-*, chatgpt-*, etc.
                if !model.starts_with("gpt-")
                    && !model.starts_with("o1")
                    && !model.starts_with("chatgpt")
                {
                    return Err(LlmConfigError::InvalidModel {
                        model: model.to_string(),
                        reason: "OpenAI models must start with 'gpt-', 'o1', or 'chatgpt'"
                            .to_string(),
                    });
                }
            }
            LlmProvider::Azure => {
                // Azure uses deployment names, which can be anything
                // Just check it's not empty (already done above)
            }
            LlmProvider::Ollama => {
                // Ollama models can be any name
                // Just check it's not empty (already done above)
            }
        }
        Ok(())
    }
}

impl std::fmt::Display for LlmProvider {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LlmProvider::Anthropic => write!(f, "anthropic"),
            LlmProvider::Openai => write!(f, "openai"),
            LlmProvider::Azure => write!(f, "azure"),
            LlmProvider::Ollama => write!(f, "ollama"),
        }
    }
}

/// LLM configuration
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub struct LlmConfig {
    /// LLM provider (anthropic, openai, azure, ollama)
    pub provider: LlmProvider,

    /// Model identifier (e.g., claude-sonnet-4, gpt-4o)
    pub model: String,

    /// Name of K8s Secret containing API key (required for cloud providers)
    #[serde(default)]
    pub api_key_secret: Option<String>,

    /// Key within the secret that contains the API key (default: "api-key")
    #[serde(default = "default_api_key_secret_key")]
    pub api_key_secret_key: String,

    /// Custom endpoint URL (optional, for Azure or self-hosted)
    #[serde(default)]
    pub endpoint: Option<String>,
}

fn default_api_key_secret_key() -> String {
    "api-key".to_string()
}

impl Default for LlmConfig {
    fn default() -> Self {
        Self {
            provider: LlmProvider::Anthropic,
            model: "claude-sonnet-4".to_string(),
            api_key_secret: None,
            api_key_secret_key: default_api_key_secret_key(),
            endpoint: None,
        }
    }
}

impl LlmConfig {
    /// Validates the LLM configuration
    pub fn validate(&self) -> Result<(), LlmConfigError> {
        // Validate model name
        self.provider.validate_model(&self.model)?;

        // Check API key secret is provided for providers that require it
        if self.provider.requires_api_key() && self.api_key_secret.is_none() {
            return Err(LlmConfigError::MissingApiKeySecret {
                provider: self.provider,
            });
        }

        // Validate endpoint for Azure (required) and Ollama (has default)
        if self.provider == LlmProvider::Azure && self.endpoint.is_none() {
            return Err(LlmConfigError::MissingEndpoint {
                provider: self.provider,
            });
        }

        Ok(())
    }
}

/// Errors related to LLM configuration
#[derive(Debug, Error)]
pub enum LlmConfigError {
    #[error("Invalid model '{model}' for provider: {reason}")]
    InvalidModel { model: String, reason: String },

    #[error("API key secret is required for provider {provider}")]
    MissingApiKeySecret { provider: LlmProvider },

    #[error("Endpoint is required for provider {provider}")]
    MissingEndpoint { provider: LlmProvider },

    #[error("Secret '{secret_name}' not found in namespace")]
    SecretNotFound { secret_name: String },

    #[error("Key '{key}' not found in secret '{secret_name}'")]
    KeyNotFound { secret_name: String, key: String },

    #[error("Failed to decode API key from secret: {0}")]
    DecodeError(String),

    #[error("Kubernetes API error: {0}")]
    KubeError(#[from] kube::Error),

    #[error("LLM API error: {message}")]
    ApiError { message: String },
}

/// LLM configuration manager
pub struct LlmManager {
    client: Arc<Client>,
    config: LlmConfig,
    namespace: String,
}

impl LlmManager {
    /// Create a new LLM manager
    pub fn new(client: Arc<Client>, config: LlmConfig, namespace: String) -> Self {
        Self {
            client,
            config,
            namespace,
        }
    }

    /// Get the current LLM configuration
    pub fn config(&self) -> &LlmConfig {
        &self.config
    }

    /// Read the API key from the configured Kubernetes Secret
    pub async fn read_api_key(&self) -> Result<String, LlmConfigError> {
        let secret_name = match &self.config.api_key_secret {
            Some(name) => name,
            None => {
                if self.config.provider.requires_api_key() {
                    return Err(LlmConfigError::MissingApiKeySecret {
                        provider: self.config.provider,
                    });
                }
                return Ok(String::new()); // Ollama doesn't need an API key
            }
        };

        read_secret_key(
            &self.client,
            &self.namespace,
            secret_name,
            &self.config.api_key_secret_key,
        )
        .await
    }

    /// Check if the LLM provider is healthy
    pub async fn check_health(&self) -> LlmHealthStatus {
        // First validate configuration
        if let Err(e) = self.config.validate() {
            return LlmHealthStatus {
                status: "unhealthy".to_string(),
                message: format!("Configuration error: {}", e),
                provider: Some(self.config.provider.to_string()),
                model: Some(self.config.model.clone()),
            };
        }

        // Check if we can read the API key
        if self.config.provider.requires_api_key() {
            match self.read_api_key().await {
                Ok(_) => {
                    debug!(
                        provider = %self.config.provider,
                        model = %self.config.model,
                        "LLM credentials validated"
                    );
                }
                Err(e) => {
                    warn!(error = %e, "Failed to read LLM credentials");
                    return LlmHealthStatus {
                        status: "unhealthy".to_string(),
                        message: map_error_to_message(&e),
                        provider: Some(self.config.provider.to_string()),
                        model: Some(self.config.model.clone()),
                    };
                }
            }
        }

        LlmHealthStatus {
            status: "healthy".to_string(),
            message: format!(
                "Configured: {}/{}",
                self.config.provider, self.config.model
            ),
            provider: Some(self.config.provider.to_string()),
            model: Some(self.config.model.clone()),
        }
    }
}

/// LLM health status for API responses
#[derive(Debug, Clone, Serialize)]
pub struct LlmHealthStatus {
    pub status: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub provider: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
}

/// Read a key from a Kubernetes Secret
pub async fn read_secret_key(
    client: &Client,
    namespace: &str,
    secret_name: &str,
    key: &str,
) -> Result<String, LlmConfigError> {
    let secrets: Api<Secret> = Api::namespaced(client.clone(), namespace);

    let secret = secrets.get(secret_name).await.map_err(|e| {
        if let kube::Error::Api(ae) = &e {
            if ae.code == 404 {
                return LlmConfigError::SecretNotFound {
                    secret_name: secret_name.to_string(),
                };
            }
        }
        LlmConfigError::KubeError(e)
    })?;

    let data = secret.data.ok_or_else(|| LlmConfigError::KeyNotFound {
        secret_name: secret_name.to_string(),
        key: key.to_string(),
    })?;

    let value = data.get(key).ok_or_else(|| LlmConfigError::KeyNotFound {
        secret_name: secret_name.to_string(),
        key: key.to_string(),
    })?;

    // Secret data is base64-encoded by Kubernetes, but kube-rs decodes it for us
    // The ByteString contains the raw bytes
    String::from_utf8(value.0.clone())
        .map_err(|e| LlmConfigError::DecodeError(format!("Invalid UTF-8 in API key: {}", e)))
}

/// Map LLM errors to user-friendly messages
fn map_error_to_message(error: &LlmConfigError) -> String {
    match error {
        LlmConfigError::SecretNotFound { secret_name } => {
            format!(
                "LLM credentials secret '{}' not found in namespace",
                secret_name
            )
        }
        LlmConfigError::KeyNotFound { secret_name, key } => {
            format!("Key '{}' not found in secret '{}'", key, secret_name)
        }
        LlmConfigError::DecodeError(_) => "Failed to decode API key from secret".to_string(),
        LlmConfigError::MissingApiKeySecret { provider } => {
            format!(
                "API key secret is required for provider {}",
                provider
            )
        }
        LlmConfigError::MissingEndpoint { provider } => {
            format!("Endpoint URL is required for provider {}", provider)
        }
        LlmConfigError::InvalidModel { model, reason } => {
            format!("Invalid model '{}': {}", model, reason)
        }
        LlmConfigError::KubeError(e) => format!("Kubernetes API error: {}", e),
        LlmConfigError::ApiError { message } => message.clone(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_llm_provider_requires_api_key() {
        assert!(LlmProvider::Anthropic.requires_api_key());
        assert!(LlmProvider::Openai.requires_api_key());
        assert!(LlmProvider::Azure.requires_api_key());
        assert!(!LlmProvider::Ollama.requires_api_key());
    }

    #[test]
    fn test_llm_provider_validate_model_anthropic() {
        assert!(LlmProvider::Anthropic
            .validate_model("claude-sonnet-4")
            .is_ok());
        assert!(LlmProvider::Anthropic
            .validate_model("claude-3-haiku")
            .is_ok());
        assert!(LlmProvider::Anthropic.validate_model("gpt-4").is_err());
        assert!(LlmProvider::Anthropic.validate_model("").is_err());
    }

    #[test]
    fn test_llm_provider_validate_model_openai() {
        assert!(LlmProvider::Openai.validate_model("gpt-4o").is_ok());
        assert!(LlmProvider::Openai.validate_model("gpt-4-turbo").is_ok());
        assert!(LlmProvider::Openai.validate_model("o1-preview").is_ok());
        assert!(LlmProvider::Openai.validate_model("claude-3").is_err());
    }

    #[test]
    fn test_llm_provider_validate_model_azure() {
        // Azure accepts any model name (it's a deployment name)
        assert!(LlmProvider::Azure
            .validate_model("my-deployment")
            .is_ok());
        assert!(LlmProvider::Azure.validate_model("gpt-4").is_ok());
    }

    #[test]
    fn test_llm_provider_validate_model_ollama() {
        // Ollama accepts any model name
        assert!(LlmProvider::Ollama.validate_model("llama3").is_ok());
        assert!(LlmProvider::Ollama.validate_model("codellama").is_ok());
    }

    #[test]
    fn test_llm_config_validate_anthropic_valid() {
        let config = LlmConfig {
            provider: LlmProvider::Anthropic,
            model: "claude-sonnet-4".to_string(),
            api_key_secret: Some("anthropic-api-key".to_string()),
            api_key_secret_key: "api-key".to_string(),
            endpoint: None,
        };
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_llm_config_validate_anthropic_missing_secret() {
        let config = LlmConfig {
            provider: LlmProvider::Anthropic,
            model: "claude-sonnet-4".to_string(),
            api_key_secret: None,
            api_key_secret_key: "api-key".to_string(),
            endpoint: None,
        };
        assert!(matches!(
            config.validate(),
            Err(LlmConfigError::MissingApiKeySecret { .. })
        ));
    }

    #[test]
    fn test_llm_config_validate_azure_missing_endpoint() {
        let config = LlmConfig {
            provider: LlmProvider::Azure,
            model: "my-deployment".to_string(),
            api_key_secret: Some("azure-api-key".to_string()),
            api_key_secret_key: "api-key".to_string(),
            endpoint: None,
        };
        assert!(matches!(
            config.validate(),
            Err(LlmConfigError::MissingEndpoint { .. })
        ));
    }

    #[test]
    fn test_llm_config_validate_ollama_no_secret_needed() {
        let config = LlmConfig {
            provider: LlmProvider::Ollama,
            model: "llama3".to_string(),
            api_key_secret: None,
            api_key_secret_key: "api-key".to_string(),
            endpoint: Some("http://localhost:11434".to_string()),
        };
        assert!(config.validate().is_ok());
    }

    #[test]
    fn test_llm_config_default() {
        let config = LlmConfig::default();
        assert_eq!(config.provider, LlmProvider::Anthropic);
        assert_eq!(config.model, "claude-sonnet-4");
        assert_eq!(config.api_key_secret_key, "api-key");
    }

    #[test]
    fn test_llm_config_serialization() {
        let config = LlmConfig {
            provider: LlmProvider::Anthropic,
            model: "claude-sonnet-4".to_string(),
            api_key_secret: Some("llm-credentials".to_string()),
            api_key_secret_key: "api-key".to_string(),
            endpoint: None,
        };

        let json = serde_json::to_string(&config).unwrap();
        assert!(json.contains("\"provider\":\"anthropic\""));
        assert!(json.contains("\"model\":\"claude-sonnet-4\""));
        assert!(json.contains("\"api_key_secret\":\"llm-credentials\""));
    }

    #[test]
    fn test_llm_config_deserialization() {
        let json = r#"{
            "provider": "openai",
            "model": "gpt-4o",
            "api_key_secret": "openai-key"
        }"#;

        let config: LlmConfig = serde_json::from_str(json).unwrap();
        assert_eq!(config.provider, LlmProvider::Openai);
        assert_eq!(config.model, "gpt-4o");
        assert_eq!(config.api_key_secret, Some("openai-key".to_string()));
        assert_eq!(config.api_key_secret_key, "api-key"); // default value
    }

    #[test]
    fn test_llm_health_status_serialization() {
        let status = LlmHealthStatus {
            status: "healthy".to_string(),
            message: "Configured: anthropic/claude-sonnet-4".to_string(),
            provider: Some("anthropic".to_string()),
            model: Some("claude-sonnet-4".to_string()),
        };

        let json = serde_json::to_string(&status).unwrap();
        assert!(json.contains("\"status\":\"healthy\""));
        assert!(json.contains("\"provider\":\"anthropic\""));
    }
}
