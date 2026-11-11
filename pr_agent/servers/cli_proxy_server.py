"""CLI Proxy Server for PR-Agent.

This server wraps PR-Agent with CLI-based AI handlers (Claude Code, Kiro CLI, etc.),
allowing agents to use PR-Agent's code review capabilities without separate API keys.

The server exposes REST endpoints that mirror PR-Agent's commands:
- POST /api/v1/review - Run code review on a PR
- POST /api/v1/describe - Generate PR description
- POST /api/v1/improve - Get code improvement suggestions
- POST /api/v1/ask - Ask questions about a PR
- POST /api/v1/command - Run any PR-Agent command

Usage:
    # Start the server
    python -m pr_agent.servers.cli_proxy_server

    # Or with environment variables
    CLI_PROXY_TOOL=claude PORT=8080 python -m pr_agent.servers.cli_proxy_server

    # Call from curl
    curl -X POST http://localhost:8080/api/v1/review \\
        -H "Content-Type: application/json" \\
        -d '{"pr_url": "https://github.com/owner/repo/pull/123"}'
"""

import copy
import os
from contextlib import asynccontextmanager
from enum import StrEnum

import uvicorn
from fastapi import APIRouter
from pydantic import BaseModel, Field
from starlette.middleware import Middleware
from starlette_context import context
from starlette_context.middleware import RawContextMiddleware

from pr_agent.agent.pr_agent import PRAgent
from pr_agent.algo.ai_handlers.cli_ai_handler import CLI_ADAPTERS, CLIAIHandler, get_cli_adapter
from pr_agent.config_loader import get_settings, global_settings
from pr_agent.git_providers.utils import apply_repo_settings
from pr_agent.log import LoggingFormat, get_logger, setup_logger
from pr_agent.servers.request_body_limit import create_server_app

# Setup logging
setup_logger(fmt=LoggingFormat.JSON, level=os.getenv("LOG_LEVEL", "INFO"))

router = APIRouter()


# ============================================================================
# Request/Response Models
# ============================================================================


class CommandName(StrEnum):
    """Supported PR-Agent commands."""

    review = "review"
    describe = "describe"
    improve = "improve"
    ask = "ask"
    config = "config"
    help = "help"
    add_docs = "add_docs"
    generate_labels = "generate_labels"
    update_changelog = "update_changelog"


class CommandRequest(BaseModel):
    """Request model for PR-Agent commands."""

    pr_url: str = Field(
        ...,
        description="URL of the pull request (GitHub, GitLab, Bitbucket, etc.)",
        examples=["https://github.com/owner/repo/pull/123"],
    )
    args: list[str] = Field(
        default_factory=list,
        description="Additional command arguments",
        examples=[["--pr_reviewer.num_max_findings=5"]],
    )


class AskRequest(CommandRequest):
    """Request model for the /ask command."""

    question: str = Field(
        ...,
        description="Question to ask about the PR",
        examples=["What is the main purpose of this PR?"],
    )


class CommandResponse(BaseModel):
    """Response model for PR-Agent commands."""

    success: bool = Field(..., description="Whether the command completed successfully")
    command: str = Field(..., description="The command that was executed")
    pr_url: str = Field(..., description="The PR URL that was processed")
    message: str | None = Field(None, description="Success message or additional info")
    error: str | None = Field(None, description="Error message if command failed")


class HealthResponse(BaseModel):
    """Response model for health check endpoint."""

    status: str = Field(..., description="Server health status")
    cli_tool: str | None = Field(None, description="Configured CLI tool name")
    cli_available: bool = Field(..., description="Whether the CLI tool is available")
    available_tools: list[str] = Field(..., description="List of supported CLI tools")
    error: str | None = Field(None, description="Error message if unhealthy")


# ============================================================================
# Lifespan and Initialization
# ============================================================================


@asynccontextmanager
async def lifespan(app):
    """Validate CLI tool availability on startup."""
    tool_name = get_settings().get("CLI_PROXY.TOOL", os.getenv("CLI_PROXY_TOOL", "claude"))
    get_logger().info(f"CLI Proxy Server starting with tool: {tool_name}")

    try:
        adapter = get_cli_adapter(tool_name)
        if not adapter.is_available():
            get_logger().warning(
                f"{adapter.name} CLI not found in PATH. "
                f"Commands will fail until '{adapter.executable}' is available."
            )
        else:
            get_logger().info(f"{adapter.name} CLI found at: {adapter.get_executable_path()}")
    except ValueError as e:
        get_logger().error(f"Invalid CLI tool configuration: {e}")

    yield

    get_logger().info("CLI Proxy Server shutting down")


# ============================================================================
# Helper Functions
# ============================================================================


def _get_cli_handler_factory():
    """Get a CLIAIHandler factory function for PR-Agent commands."""

    def factory():
        return CLIAIHandler()

    return factory


async def _run_pr_agent_command(
    pr_url: str,
    command: str,
    args: list[str] | None = None,
) -> CommandResponse:
    """Execute a PR-Agent command with CLI AI handler.

    Args:
        pr_url: URL of the pull request.
        command: Command name (review, describe, improve, etc.).
        args: Additional command arguments.

    Returns:
        CommandResponse with success status and any error details.
    """
    args = args or []
    full_command = f"/{command}" + (" " + " ".join(args) if args else "")

    get_logger().info(
        "CLI Proxy executing command",
        command=command,
        pr_url=pr_url,
        args=args,
    )

    try:
        # Initialize request-scoped settings
        context["settings"] = copy.deepcopy(global_settings)

        # Apply repository settings if available
        try:
            apply_repo_settings(pr_url)
        except Exception as e:
            get_logger().warning(f"Could not apply repo settings: {e}")

        # Create PR-Agent with CLI handler
        agent = PRAgent(ai_handler=_get_cli_handler_factory())

        # Run the command
        result = await agent.handle_request(pr_url, full_command)

        if result:
            return CommandResponse(
                success=True,
                command=command,
                pr_url=pr_url,
                message=f"Command /{command} completed successfully",
            )
        else:
            return CommandResponse(
                success=False,
                command=command,
                pr_url=pr_url,
                error="Command returned False (check server logs for details)",
            )

    except Exception as e:
        get_logger().exception(f"CLI Proxy command failed: {e}")
        return CommandResponse(
            success=False,
            command=command,
            pr_url=pr_url,
            error=str(e),
        )


# ============================================================================
# API Endpoints
# ============================================================================


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Check server health and CLI tool availability."""
    tool_name = get_settings().get("CLI_PROXY.TOOL", os.getenv("CLI_PROXY_TOOL", "claude"))
    available_tools = sorted(set(CLI_ADAPTERS.keys()))

    try:
        adapter = get_cli_adapter(tool_name)
        is_available = adapter.is_available()

        return HealthResponse(
            status="healthy" if is_available else "degraded",
            cli_tool=adapter.name,
            cli_available=is_available,
            available_tools=available_tools,
            error=None if is_available else f"{adapter.executable} not found in PATH",
        )
    except ValueError as e:
        return HealthResponse(
            status="unhealthy",
            cli_tool=None,
            cli_available=False,
            available_tools=available_tools,
            error=str(e),
        )


@router.post("/api/v1/review", response_model=CommandResponse, tags=["Commands"])
async def review(request: CommandRequest):
    """Run /review command to analyze code changes in a PR.

    The review command analyzes the PR diff and provides:
    - Summary of changes
    - Key issues and concerns
    - Security considerations
    - Code quality feedback
    """
    return await _run_pr_agent_command(request.pr_url, "review", request.args)


@router.post("/api/v1/describe", response_model=CommandResponse, tags=["Commands"])
async def describe(request: CommandRequest):
    """Run /describe command to generate a PR description.

    The describe command analyzes the PR and generates:
    - Title suggestion
    - Summary of changes
    - File-by-file walkthrough
    - Labels suggestion
    """
    return await _run_pr_agent_command(request.pr_url, "describe", request.args)


@router.post("/api/v1/improve", response_model=CommandResponse, tags=["Commands"])
async def improve(request: CommandRequest):
    """Run /improve command to get code improvement suggestions.

    The improve command analyzes the PR diff and suggests:
    - Code quality improvements
    - Bug fixes
    - Performance optimizations
    - Best practice recommendations
    """
    return await _run_pr_agent_command(request.pr_url, "improve", request.args)


@router.post("/api/v1/ask", response_model=CommandResponse, tags=["Commands"])
async def ask(request: AskRequest):
    """Run /ask command to ask questions about a PR.

    Provide a question about the PR changes and receive an AI-generated answer
    based on the PR context.
    """
    args = [request.question] + request.args
    return await _run_pr_agent_command(request.pr_url, "ask", args)


@router.post("/api/v1/command", response_model=CommandResponse, tags=["Commands"])
async def generic_command(command: CommandName, request: CommandRequest):
    """Run any supported PR-Agent command.

    Use the `command` query parameter to specify which command to run.
    This endpoint provides access to all PR-Agent commands through a single interface.
    """
    return await _run_pr_agent_command(request.pr_url, command.value, request.args)


@router.get("/", tags=["Health"])
async def root():
    """Root endpoint with server information."""
    tool_name = get_settings().get("CLI_PROXY.TOOL", os.getenv("CLI_PROXY_TOOL", "claude"))
    return {
        "service": "PR-Agent CLI Proxy",
        "version": "1.0.0",
        "cli_tool": tool_name,
        "docs": "/docs",
        "health": "/health",
    }


# ============================================================================
# Server Setup
# ============================================================================


def create_app():
    """Create the FastAPI application with middleware."""
    middleware = [Middleware(RawContextMiddleware)]
    app = create_server_app(middleware=middleware)
    app.include_router(router)

    # Add OpenAPI metadata
    app.title = "PR-Agent CLI Proxy"
    app.description = __doc__
    app.version = "1.0.0"

    return app


def start():
    """Start the CLI proxy server."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8080"))

    # Configure CLI mode to prevent adding help messages
    get_settings().set("CONFIG.CLI_MODE", True)

    app = create_app()

    get_logger().info(f"Starting PR-Agent CLI Proxy on {host}:{port}")
    get_logger().info(f"API docs available at http://{host}:{port}/docs")

    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    start()
