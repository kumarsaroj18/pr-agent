"""Unit tests for CLI Proxy Server."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from pr_agent.servers.cli_proxy_server import (
    CommandName,
    CommandRequest,
    CommandResponse,
    HealthResponse,
    _get_cli_handler_factory,
    create_app,
)


@pytest.fixture
def client():
    """Create a test client for the CLI proxy server."""
    app = create_app()
    return TestClient(app)


@pytest.fixture
def mock_cli_adapter():
    """Create a mock CLI adapter."""
    adapter = MagicMock()
    adapter.name = "Mock CLI"
    adapter.executable = "mock-cli"
    adapter.is_available.return_value = True
    adapter.get_executable_path.return_value = "/usr/bin/mock-cli"
    return adapter


class TestHealthEndpoint:
    """Tests for the /health endpoint."""

    def test_health_check_healthy(self, client, mock_cli_adapter):
        with patch(
            "pr_agent.servers.cli_proxy_server.get_cli_adapter",
            return_value=mock_cli_adapter,
        ):
            response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["cli_tool"] == "Mock CLI"
        assert data["cli_available"] is True
        assert "available_tools" in data
        assert data["error"] is None

    def test_health_check_degraded_cli_not_available(self, client, mock_cli_adapter):
        mock_cli_adapter.is_available.return_value = False

        with patch(
            "pr_agent.servers.cli_proxy_server.get_cli_adapter",
            return_value=mock_cli_adapter,
        ):
            response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["cli_available"] is False
        assert "not found" in data["error"]

    def test_health_check_unhealthy_invalid_tool(self, client):
        with patch(
            "pr_agent.servers.cli_proxy_server.get_cli_adapter",
            side_effect=ValueError("Unknown CLI tool: invalid"),
        ):
            response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["cli_tool"] is None
        assert data["cli_available"] is False
        assert "Unknown CLI tool" in data["error"]


class TestRootEndpoint:
    """Tests for the / endpoint."""

    def test_root_returns_service_info(self, client):
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["service"] == "PR-Agent CLI Proxy"
        assert "version" in data
        assert "cli_tool" in data
        assert data["docs"] == "/docs"
        assert data["health"] == "/health"


class TestReviewEndpoint:
    """Tests for the /api/v1/review endpoint."""

    @pytest.mark.asyncio
    async def test_review_success(self, client):
        with patch(
            "pr_agent.servers.cli_proxy_server._run_pr_agent_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = CommandResponse(
                success=True,
                command="review",
                pr_url="https://github.com/test/repo/pull/1",
                message="Command /review completed successfully",
            )

            response = client.post(
                "/api/v1/review",
                json={"pr_url": "https://github.com/test/repo/pull/1"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["command"] == "review"

    def test_review_requires_pr_url(self, client):
        response = client.post("/api/v1/review", json={})

        assert response.status_code == 422  # Validation error

    def test_review_with_args(self, client):
        with patch(
            "pr_agent.servers.cli_proxy_server._run_pr_agent_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = CommandResponse(
                success=True,
                command="review",
                pr_url="https://github.com/test/repo/pull/1",
                message="Success",
            )

            response = client.post(
                "/api/v1/review",
                json={
                    "pr_url": "https://github.com/test/repo/pull/1",
                    "args": ["--pr_reviewer.num_max_findings=10"],
                },
            )

        assert response.status_code == 200
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert call_args[0][2] == ["--pr_reviewer.num_max_findings=10"]


class TestDescribeEndpoint:
    """Tests for the /api/v1/describe endpoint."""

    def test_describe_success(self, client):
        with patch(
            "pr_agent.servers.cli_proxy_server._run_pr_agent_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = CommandResponse(
                success=True,
                command="describe",
                pr_url="https://github.com/test/repo/pull/1",
                message="Success",
            )

            response = client.post(
                "/api/v1/describe",
                json={"pr_url": "https://github.com/test/repo/pull/1"},
            )

        assert response.status_code == 200
        mock_run.assert_called_once_with(
            "https://github.com/test/repo/pull/1",
            "describe",
            [],
        )


class TestImproveEndpoint:
    """Tests for the /api/v1/improve endpoint."""

    def test_improve_success(self, client):
        with patch(
            "pr_agent.servers.cli_proxy_server._run_pr_agent_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = CommandResponse(
                success=True,
                command="improve",
                pr_url="https://github.com/test/repo/pull/1",
                message="Success",
            )

            response = client.post(
                "/api/v1/improve",
                json={"pr_url": "https://github.com/test/repo/pull/1"},
            )

        assert response.status_code == 200
        mock_run.assert_called_once_with(
            "https://github.com/test/repo/pull/1",
            "improve",
            [],
        )


class TestAskEndpoint:
    """Tests for the /api/v1/ask endpoint."""

    def test_ask_success(self, client):
        with patch(
            "pr_agent.servers.cli_proxy_server._run_pr_agent_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = CommandResponse(
                success=True,
                command="ask",
                pr_url="https://github.com/test/repo/pull/1",
                message="Success",
            )

            response = client.post(
                "/api/v1/ask",
                json={
                    "pr_url": "https://github.com/test/repo/pull/1",
                    "question": "What does this PR do?",
                },
            )

        assert response.status_code == 200
        mock_run.assert_called_once()
        call_args = mock_run.call_args
        assert "What does this PR do?" in call_args[0][2]

    def test_ask_requires_question(self, client):
        response = client.post(
            "/api/v1/ask",
            json={"pr_url": "https://github.com/test/repo/pull/1"},
        )

        assert response.status_code == 422  # Validation error


class TestGenericCommandEndpoint:
    """Tests for the /api/v1/command endpoint."""

    def test_generic_command_review(self, client):
        with patch(
            "pr_agent.servers.cli_proxy_server._run_pr_agent_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = CommandResponse(
                success=True,
                command="review",
                pr_url="https://github.com/test/repo/pull/1",
                message="Success",
            )

            response = client.post(
                "/api/v1/command?command=review",
                json={"pr_url": "https://github.com/test/repo/pull/1"},
            )

        assert response.status_code == 200
        mock_run.assert_called_once_with(
            "https://github.com/test/repo/pull/1",
            "review",
            [],
        )

    def test_generic_command_describe(self, client):
        with patch(
            "pr_agent.servers.cli_proxy_server._run_pr_agent_command",
            new_callable=AsyncMock,
        ) as mock_run:
            mock_run.return_value = CommandResponse(
                success=True,
                command="describe",
                pr_url="https://github.com/test/repo/pull/1",
                message="Success",
            )

            response = client.post(
                "/api/v1/command?command=describe",
                json={"pr_url": "https://github.com/test/repo/pull/1"},
            )

        assert response.status_code == 200

    def test_generic_command_invalid(self, client):
        response = client.post(
            "/api/v1/command?command=invalid_command",
            json={"pr_url": "https://github.com/test/repo/pull/1"},
        )

        assert response.status_code == 422  # Validation error


class TestCommandNameEnum:
    """Tests for CommandName enum."""

    def test_all_commands_defined(self):
        expected = {
            "review",
            "describe",
            "improve",
            "ask",
            "config",
            "help",
            "add_docs",
            "generate_labels",
            "update_changelog",
        }
        assert set(c.value for c in CommandName) == expected


class TestCLIHandlerFactory:
    """Tests for the CLI handler factory function."""

    def test_factory_returns_cli_handler(self, mock_cli_adapter):
        with patch(
            "pr_agent.servers.cli_proxy_server.get_cli_adapter",
            return_value=mock_cli_adapter,
        ):
            with patch(
                "pr_agent.algo.ai_handlers.cli_ai_handler.get_cli_adapter",
                return_value=mock_cli_adapter,
            ):
                factory = _get_cli_handler_factory()
                handler = factory()

                # Verify it's a CLIAIHandler instance
                from pr_agent.algo.ai_handlers.cli_ai_handler import CLIAIHandler

                assert isinstance(handler, CLIAIHandler)


class TestRequestModels:
    """Tests for request/response Pydantic models."""

    def test_command_request_valid(self):
        req = CommandRequest(pr_url="https://github.com/test/repo/pull/1")
        assert req.pr_url == "https://github.com/test/repo/pull/1"
        assert req.args == []

    def test_command_request_with_args(self):
        req = CommandRequest(
            pr_url="https://github.com/test/repo/pull/1",
            args=["--arg1=value1", "--arg2=value2"],
        )
        assert len(req.args) == 2

    def test_command_response_success(self):
        resp = CommandResponse(
            success=True,
            command="review",
            pr_url="https://github.com/test/repo/pull/1",
            message="Success",
        )
        assert resp.success is True
        assert resp.error is None

    def test_command_response_failure(self):
        resp = CommandResponse(
            success=False,
            command="review",
            pr_url="https://github.com/test/repo/pull/1",
            error="Something went wrong",
        )
        assert resp.success is False
        assert resp.message is None

    def test_health_response(self):
        resp = HealthResponse(
            status="healthy",
            cli_tool="Claude Code",
            cli_available=True,
            available_tools=["claude", "kiro"],
        )
        assert resp.status == "healthy"
        assert resp.error is None


class TestCreateApp:
    """Tests for app creation."""

    def test_create_app_returns_fastapi(self):
        app = create_app()

        from fastapi import FastAPI

        assert isinstance(app, FastAPI)
        assert app.title == "PR-Agent CLI Proxy"

    def test_create_app_includes_routes(self):
        app = create_app()
        # Use OpenAPI schema to verify routes are registered
        openapi = app.openapi()
        paths = openapi.get("paths", {}).keys()

        assert "/health" in paths
        assert "/api/v1/review" in paths
        assert "/api/v1/describe" in paths
        assert "/api/v1/improve" in paths
        assert "/api/v1/ask" in paths
        assert "/api/v1/command" in paths
        assert "/" in paths
