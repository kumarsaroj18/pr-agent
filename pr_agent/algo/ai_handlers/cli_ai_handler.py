"""AI handler that routes completions through CLI tools (Claude Code, Kiro CLI, etc.).

This handler allows PR-Agent to use locally-installed AI CLI tools instead of
requiring separate API keys. The CLI tool must be authenticated independently
(e.g., via `claude` login or Kiro's auth mechanism).

Usage:
    from pr_agent.algo.ai_handlers.cli_ai_handler import CLIAIHandler

    # Use default CLI tool from config
    handler = CLIAIHandler()

    # Or specify adapter explicitly
    from pr_agent.algo.ai_handlers.cli_ai_handler import ClaudeCodeAdapter
    handler = CLIAIHandler(adapter=ClaudeCodeAdapter())
"""

import asyncio
import json
import shlex
import shutil
from abc import ABC, abstractmethod

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.run_details import record_ai_call
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger


class CLIAdapter(ABC):
    """Abstract adapter for CLI-based AI tools.

    Each adapter knows how to invoke a specific CLI tool and parse its output.
    Subclasses must implement the abstract methods to handle tool-specific details.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for logging and error messages."""

    @property
    @abstractmethod
    def executable(self) -> str:
        """CLI executable name (e.g., 'claude', 'kiro')."""

    @abstractmethod
    def build_command(self, prompt: str) -> list[str]:
        """Build the subprocess command arguments.

        Args:
            prompt: The combined system + user prompt text.

        Returns:
            List of command arguments for subprocess execution.
        """

    @abstractmethod
    def parse_response(self, stdout: str, stderr: str, returncode: int) -> str:
        """Parse CLI output to extract the response text.

        Args:
            stdout: Standard output from the CLI process.
            stderr: Standard error from the CLI process.
            returncode: Exit code from the CLI process.

        Returns:
            The extracted response text.

        Raises:
            RuntimeError: If the CLI output indicates an error.
        """

    def is_available(self) -> bool:
        """Check if the CLI tool is installed and accessible in PATH."""
        return shutil.which(self.executable) is not None

    def get_executable_path(self) -> str:
        """Get the full path to the CLI executable.

        Returns:
            Full path to the executable, or the executable name if not found.
        """
        path = get_settings().get("CLI_PROXY.EXECUTABLE_PATH", "")
        if path:
            return path
        return shutil.which(self.executable) or self.executable


class ClaudeCodeAdapter(CLIAdapter):
    """Adapter for Claude Code CLI (https://docs.anthropic.com/en/docs/claude-code).

    Claude Code supports a non-interactive mode with `claude -p "prompt"` that
    outputs JSON when `--output-format json` is specified.
    """

    @property
    def name(self) -> str:
        return "Claude Code"

    @property
    def executable(self) -> str:
        return "claude"

    def build_command(self, prompt: str) -> list[str]:
        """Build Claude Code CLI command.

        Uses:
        - `-p`: Print mode (non-interactive)
        - `--output-format json`: Structured output for parsing
        """
        return [
            self.get_executable_path(),
            "-p",
            prompt,
            "--output-format",
            "json",
        ]

    def parse_response(self, stdout: str, stderr: str, returncode: int) -> str:
        """Parse Claude Code JSON output.

        Expected format: {"result": "...", "cost_usd": ..., ...}
        Falls back to raw output if JSON parsing fails.
        """
        if returncode != 0:
            error_msg = stderr.strip() or stdout.strip() or f"Exit code {returncode}"
            raise RuntimeError(f"{self.name} CLI failed: {error_msg[:500]}")

        stdout = stdout.strip()
        if not stdout:
            raise RuntimeError(f"{self.name} CLI returned empty output")

        try:
            data = json.loads(stdout)
            # Claude Code returns result in "result" field
            if isinstance(data, dict):
                return data.get("result", data.get("response", data.get("content", str(data))))
            return str(data)
        except json.JSONDecodeError:
            # Fallback: return raw output (might be plain text mode)
            get_logger().debug(f"{self.name} output was not JSON, using raw output")
            return stdout


class KiroCLIAdapter(CLIAdapter):
    """Adapter for Kiro CLI.

    Note: Kiro CLI interface may vary. Adjust build_command and parse_response
    based on actual Kiro CLI documentation and behavior.
    """

    @property
    def name(self) -> str:
        return "Kiro CLI"

    @property
    def executable(self) -> str:
        return "kiro"

    def build_command(self, prompt: str) -> list[str]:
        """Build Kiro CLI command.

        Note: Adjust flags based on actual Kiro CLI interface.
        """
        return [
            self.get_executable_path(),
            "chat",
            "--message",
            prompt,
            "--no-interactive",
        ]

    def parse_response(self, stdout: str, stderr: str, returncode: int) -> str:
        """Parse Kiro CLI output."""
        if returncode != 0:
            error_msg = stderr.strip() or stdout.strip() or f"Exit code {returncode}"
            raise RuntimeError(f"{self.name} CLI failed: {error_msg[:500]}")

        stdout = stdout.strip()
        if not stdout:
            raise RuntimeError(f"{self.name} CLI returned empty output")

        # Try JSON parsing first
        try:
            data = json.loads(stdout)
            if isinstance(data, dict):
                return data.get("response", data.get("content", data.get("result", str(data))))
            return str(data)
        except json.JSONDecodeError:
            # Kiro might output plain text
            return stdout


class GenericCLIAdapter(CLIAdapter):
    """Generic adapter for custom CLI tools.

    Configure via settings:
        [cli_proxy]
        tool = "generic"
        generic_command = "my-ai-cli --prompt {prompt}"
    """

    @property
    def name(self) -> str:
        return "Generic CLI"

    @property
    def executable(self) -> str:
        cmd = get_settings().get("CLI_PROXY.GENERIC_COMMAND", "")
        if cmd:
            # Extract executable from command template
            return shlex.split(cmd)[0]
        return "ai-cli"

    def build_command(self, prompt: str) -> list[str]:
        """Build command from configured template.

        The template can use {prompt} as a placeholder.
        """
        cmd_template = get_settings().get("CLI_PROXY.GENERIC_COMMAND", "")
        if not cmd_template:
            raise ValueError(
                "CLI_PROXY.GENERIC_COMMAND must be set when using generic adapter. "
                "Example: 'my-ai-cli --prompt {prompt}'"
            )

        # Replace {prompt} placeholder
        cmd_str = cmd_template.replace("{prompt}", shlex.quote(prompt))
        return shlex.split(cmd_str)

    def parse_response(self, stdout: str, stderr: str, returncode: int) -> str:
        """Parse generic CLI output (assumes plain text)."""
        if returncode != 0:
            error_msg = stderr.strip() or stdout.strip() or f"Exit code {returncode}"
            raise RuntimeError(f"{self.name} CLI failed: {error_msg[:500]}")

        return stdout.strip()


# Registry of available adapters
CLI_ADAPTERS: dict[str, type[CLIAdapter]] = {
    "claude": ClaudeCodeAdapter,
    "claude-code": ClaudeCodeAdapter,
    "kiro": KiroCLIAdapter,
    "kiro-cli": KiroCLIAdapter,
    "generic": GenericCLIAdapter,
}


def get_cli_adapter(tool_name: str | None = None) -> CLIAdapter:
    """Get a CLI adapter instance by name.

    Args:
        tool_name: Name of the CLI tool. If None, reads from CLI_PROXY.TOOL setting.

    Returns:
        Instantiated CLIAdapter for the specified tool.

    Raises:
        ValueError: If the tool name is not recognized.
    """
    if tool_name is None:
        tool_name = get_settings().get("CLI_PROXY.TOOL", "claude")

    tool_name = tool_name.lower().strip()
    adapter_class = CLI_ADAPTERS.get(tool_name)

    if adapter_class is None:
        available = ", ".join(sorted(CLI_ADAPTERS.keys()))
        raise ValueError(f"Unknown CLI tool: {tool_name!r}. Available tools: {available}")

    return adapter_class()


class CLIAIHandler(BaseAiHandler):
    """AI handler that delegates completions to CLI tools.

    This handler runs AI completions through locally-installed CLI tools like
    Claude Code or Kiro CLI, instead of making HTTP API calls. The CLI tool
    must be pre-authenticated.

    Attributes:
        adapter: The CLI adapter used for command execution.
        main_pr_language: Primary language of the PR (set by commands).
    """

    def __init__(self, adapter: CLIAdapter | None = None):
        """Initialize the CLI AI handler.

        Args:
            adapter: Optional CLI adapter instance. If None, creates one from config.

        Raises:
            RuntimeError: If the CLI tool is not available in PATH.
        """
        super().__init__()
        self.adapter = adapter or get_cli_adapter()
        self.main_pr_language = None

        if not self.adapter.is_available():
            raise RuntimeError(
                f"{self.adapter.name} CLI not found. "
                f"Ensure '{self.adapter.executable}' is installed and in PATH, "
                f"or set CLI_PROXY.EXECUTABLE_PATH to the full path."
            )

        get_logger().info(
            "CLIAIHandler initialized",
            cli_tool=self.adapter.name,
            executable=self.adapter.get_executable_path(),
        )

    @property
    def deployment_id(self) -> str:
        """Return a deployment identifier for logging and tracking."""
        return f"cli-proxy/{self.adapter.executable}"

    async def chat_completion(
        self,
        model: str,
        system: str,
        user: str,
        temperature: float = 0.2,
        img_path: str | None = None,
    ) -> tuple[str, str]:
        """Execute a completion via CLI subprocess.

        Args:
            model: Model name (logged but not used - CLI tool decides).
            system: System prompt text.
            user: User prompt text.
            temperature: Temperature setting (logged but not used by most CLI tools).
            img_path: Image path (not supported, will log a warning).

        Returns:
            Tuple of (response_text, finish_reason).

        Raises:
            RuntimeError: If the CLI execution fails.
            TimeoutError: If the CLI execution exceeds the timeout.
        """
        if img_path:
            get_logger().warning(
                f"{self.adapter.name} CLI proxy does not support image inputs",
                img_path=img_path,
            )

        # Combine prompts with clear separation
        full_prompt = f"{system}\n\n---\n\n{user}"

        # Build command
        cmd = self.adapter.build_command(full_prompt)
        timeout = get_settings().get("CLI_PROXY.TIMEOUT", 300)
        verbose = get_settings().get("CLI_PROXY.VERBOSE", False)

        get_logger().info(
            f"Executing {self.adapter.name} CLI",
            model_requested=model,
            prompt_length=len(full_prompt),
            timeout=timeout,
        )

        if verbose:
            get_logger().debug(f"CLI command: {cmd[0]} ...", prompt_preview=full_prompt[:200])

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )

        except TimeoutError:
            # Try to terminate gracefully, then kill
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=5)
            except (TimeoutError, ProcessLookupError):
                proc.kill()

            raise TimeoutError(
                f"{self.adapter.name} CLI timed out after {timeout}s. "
                f"Increase CLI_PROXY.TIMEOUT if needed."
            ) from None

        except FileNotFoundError as e:
            raise RuntimeError(
                f"{self.adapter.name} CLI executable not found: {cmd[0]}. "
                f"Ensure the CLI is installed and in PATH."
            ) from e

        stdout_str = stdout_bytes.decode("utf-8", errors="replace")
        stderr_str = stderr_bytes.decode("utf-8", errors="replace")
        returncode = proc.returncode

        if verbose:
            get_logger().debug(
                f"{self.adapter.name} CLI completed",
                returncode=returncode,
                stdout_length=len(stdout_str),
                stderr_preview=stderr_str[:200] if stderr_str else None,
            )

        # Parse response (may raise RuntimeError)
        response = self.adapter.parse_response(stdout_str, stderr_str, returncode)

        # Record the call (no token counts available from CLI)
        usage = type("Usage", (), {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0})()
        record_ai_call(usage)

        get_logger().info(
            f"{self.adapter.name} CLI response received",
            response_length=len(response),
            returncode=returncode,
        )

        # Return (response, finish_reason) to match other handlers
        finish_reason = "stop"
        return response, finish_reason
