"""Tests for the Embedding service."""

from unittest.mock import MagicMock, patch

import pytest

from beeper_ui.services.embedding_service import (
    DEFAULT_EMBEDDING_DIMENSIONS,
    DEFAULT_EMBEDDING_MODEL,
    EmbeddingService,
    EmbeddingServiceError,
    get_embedding_service,
    reset_embedding_service,
)


class TestEmbeddingService:
    """Tests for EmbeddingService."""

    def test_init_defaults(self) -> None:
        """Test initialization with defaults."""
        service = EmbeddingService()
        assert service.model == DEFAULT_EMBEDDING_MODEL
        assert service._cache_size == 128

    def test_init_custom_model(self) -> None:
        """Test initialization with custom model."""
        service = EmbeddingService(model="text-embedding-3-large", cache_size=64)
        assert service.model == "text-embedding-3-large"
        assert service._cache_size == 64

    @patch("beeper_ui.services.embedding_service.litellm")
    def test_get_embedding_success(self, mock_litellm: MagicMock) -> None:
        """Test successful embedding generation."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2, 0.3, 0.4, 0.5]}]
        mock_litellm.embedding.return_value = mock_response

        service = EmbeddingService(api_key="test-key")
        embedding = service.get_embedding("test query")

        assert embedding == [0.1, 0.2, 0.3, 0.4, 0.5]
        mock_litellm.embedding.assert_called_once()

    @patch("beeper_ui.services.embedding_service.litellm")
    def test_get_embedding_caches_identical_queries(self, mock_litellm: MagicMock) -> None:
        """Test that identical queries use cache."""
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]
        mock_litellm.embedding.return_value = mock_response

        service = EmbeddingService(api_key="test-key")

        # Call twice with same query
        service.get_embedding("same query")
        service.get_embedding("same query")

        # Should only call API once
        assert mock_litellm.embedding.call_count == 1

    @patch("beeper_ui.services.embedding_service.litellm")
    def test_get_embedding_different_queries_not_cached(
        self, mock_litellm: MagicMock
    ) -> None:
        """Test that different queries are not cached together."""
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2, 0.3]}]
        mock_litellm.embedding.return_value = mock_response

        service = EmbeddingService(api_key="test-key")

        service.get_embedding("query one")
        service.get_embedding("query two")

        assert mock_litellm.embedding.call_count == 2

    def test_get_embedding_empty_text_raises(self) -> None:
        """Test that empty text raises error."""
        service = EmbeddingService(api_key="test-key")

        with pytest.raises(EmbeddingServiceError, match="empty text"):
            service.get_embedding("")

        with pytest.raises(EmbeddingServiceError, match="empty text"):
            service.get_embedding("   ")

    @patch("beeper_ui.services.embedding_service.litellm")
    def test_get_embedding_api_error(self, mock_litellm: MagicMock) -> None:
        """Test handling of API errors."""
        mock_litellm.embedding.side_effect = Exception("API error")

        service = EmbeddingService(api_key="test-key")

        with pytest.raises(EmbeddingServiceError, match="Failed to generate embedding"):
            service.get_embedding("test query")

    def test_get_embedding_dimensions_known_models(self) -> None:
        """Test getting dimensions for known models."""
        service = EmbeddingService(model="text-embedding-3-small")
        assert service.get_embedding_dimensions() == 1536

        service = EmbeddingService(model="text-embedding-3-large")
        assert service.get_embedding_dimensions() == 3072

        service = EmbeddingService(model="text-embedding-ada-002")
        assert service.get_embedding_dimensions() == 1536

    def test_get_embedding_dimensions_unknown_model(self) -> None:
        """Test getting dimensions for unknown model uses default."""
        service = EmbeddingService(model="unknown-model")
        assert service.get_embedding_dimensions() == DEFAULT_EMBEDDING_DIMENSIONS

    @patch("beeper_ui.services.embedding_service.litellm")
    def test_clear_cache(self, mock_litellm: MagicMock) -> None:
        """Test cache clearing."""
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2]}]
        mock_litellm.embedding.return_value = mock_response

        service = EmbeddingService(api_key="test-key")
        service.get_embedding("test")

        # Clear cache
        service.clear_cache()

        # Get embedding again - should call API
        service.get_embedding("test")
        assert mock_litellm.embedding.call_count == 2

    @patch("beeper_ui.services.embedding_service.litellm")
    def test_get_cache_info(self, mock_litellm: MagicMock) -> None:
        """Test getting cache statistics."""
        mock_response = MagicMock()
        mock_response.data = [{"embedding": [0.1, 0.2]}]
        mock_litellm.embedding.return_value = mock_response

        service = EmbeddingService(api_key="test-key", cache_size=100)
        service.get_embedding("test1")
        service.get_embedding("test1")  # Cache hit
        service.get_embedding("test2")

        info: dict[str, int | None] = service.get_cache_info()
        assert info["hits"] == 1
        assert info["misses"] == 2
        assert info["maxsize"] == 100
        assert info["currsize"] == 2

    def test_is_configured_with_api_key(self) -> None:
        """Test is_configured returns True when API key is set."""
        service = EmbeddingService(api_key="test-key")
        assert service.is_configured() is True

    @patch.dict("os.environ", {}, clear=True)
    def test_is_configured_without_api_key(self) -> None:
        """Test is_configured returns False when no API key."""
        service = EmbeddingService(api_key=None)
        assert service.is_configured() is False


class TestGetEmbeddingService:
    """Tests for get_embedding_service singleton."""

    def test_returns_same_instance(self) -> None:
        """Test that get_embedding_service returns singleton."""
        # Reset the singleton for test using the proper reset function
        reset_embedding_service()

        service1 = get_embedding_service()
        service2 = get_embedding_service()

        assert service1 is service2

        # Clean up
        reset_embedding_service()

    def test_reset_creates_new_instance(self) -> None:
        """Test that reset_embedding_service creates a new instance."""
        reset_embedding_service()

        service1 = get_embedding_service()
        reset_embedding_service()
        service2 = get_embedding_service()

        assert service1 is not service2

        # Clean up
        reset_embedding_service()
