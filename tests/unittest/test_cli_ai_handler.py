"""Unit tests for CLIAIHandler and CLI adapters."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pr_agent.algo.ai_handlers.cli_ai_handler import (
    CLI_ADAPTERS,
    ClaudeCodeAdapter,
    CLIAdapter,
    CLIAIHandler,
    GenericCLIAdapter,
    KiroCLIAdapter,
    get_cli_adapter,
)


class TestClaudeCodeAdapter:
    """Tests for ClaudeCodeAdapter."""

    def test_name(self):
        adapter = ClaudeCodeAdapter()
        assert adapter.name == "Claude Code"

    def test_executable(self):
        adapter = ClaudeCodeAdapter()
        assert adapter.executable == "claude"

    def test_build_command(self):
        adapter = ClaudeCodeAdapter()
        with patch.object(adapter, "get_executable_path", return_value="/usr/bin/claude"):
            cmd = adapter.build_command("test prompt")

        assert cmd[0] == "/usr/bin/claude"
        assert "-p" in cmd
        assert "test prompt" in cmd
        assert "--output-format" in cmd
        assert "json" in cmd

    def test_parse_response_json_success(self):
        adapter = ClaudeCodeAdapter()
        stdout = json.dumps({"result": "This is the AI response"})

        result = adapter.parse_response(stdout, "", 0)

        assert result == "This is the AI response"

    def test_parse_response_json_with_response_field(self):
        adapter = ClaudeCodeAdapter()
        stdout = json.dumps({"response": "Alternative field name"})

        result = adapter.parse_response(stdout, "", 0)

        assert result == "Alternative field name"

    def test_parse_response_plain_text_fallback(self):
        adapter = ClaudeCodeAdapter()
        stdout = "Plain text response without JSON"

        result = adapter.parse_response(stdout, "", 0)

        assert result == "Plain text response without JSON"

    def test_parse_response_error_on_nonzero_exit(self):
        adapter = ClaudeCodeAdapter()

        with pytest.raises(RuntimeError, match="Claude Code CLI failed"):
            adapter.parse_response("", "Error message", 1)

    def test_parse_response_error_on_empty_output(self):
        adapter = ClaudeCodeAdapter()

        with pytest.raises(RuntimeError, match="returned empty output"):
            adapter.parse_response("", "", 0)

    def test_is_available_true(self):
        adapter = ClaudeCodeAdapter()
        with patch("shutil.which", return_value="/usr/bin/claude"):
            assert adapter.is_available() is True

    def test_is_available_false(self):
        adapter = ClaudeCodeAdapter()
        with patch("shutil.which", return_value=None):
            assert adapter.is_available() is False


class TestKiroCLIAdapter:
    """Tests for KiroCLIAdapter."""

    def test_name(self):
        adapter = KiroCLIAdapter()
        assert adapter.name == "Kiro CLI"

    def test_executable(self):
        adapter = KiroCLIAdapter()
        assert adapter.executable == "kiro"

    def test_build_command(self):
        adapter = KiroCLIAdapter()
        with patch.object(adapter, "get_executable_path", return_value="/usr/bin/kiro"):
            cmd = adapter.build_command("test prompt")

        assert cmd[0] == "/usr/bin/kiro"
        assert "chat" in cmd
        assert "--message" in cmd
        assert "test prompt" in cmd

    def test_parse_response_json(self):
        adapter = KiroCLIAdapter()
        stdout = json.dumps({"response": "Kiro response"})

        result = adapter.parse_response(stdout, "", 0)

        assert result == "Kiro response"

    def test_parse_response_plain_text(self):
        adapter = KiroCLIAdapter()
        stdout = "Plain Kiro response"

        result = adapter.parse_response(stdout, "", 0)

        assert result == "Plain Kiro response"


class TestGenericCLIAdapter:
    """Tests for GenericCLIAdapter."""

    def test_name(self):
        adapter = GenericCLIAdapter()
        assert adapter.name == "Generic CLI"

    @patch("pr_agent.algo.ai_handlers.cli_ai_handler.get_settings")
    def test_build_command_with_template(self, mock_settings):
        mock_settings.return_value.get.return_value = "my-ai --prompt {prompt}"
        adapter = GenericCLIAdapter()

        cmd = adapter.build_command("test prompt")

        assert cmd[0] == "my-ai"
        assert "--prompt" in cmd

    @patch("pr_agent.algo.ai_handlers.cli_ai_handler.get_settings")
    def test_build_command_raises_without_template(self, mock_settings):
        mock_settings.return_value.get.return_value = ""
        adapter = GenericCLIAdapter()

        with pytest.raises(ValueError, match="GENERIC_COMMAND must be set"):
            adapter.build_command("test prompt")


class TestGetCliAdapter:
    """Tests for get_cli_adapter factory function."""

    @patch("pr_agent.algo.ai_handlers.cli_ai_handler.get_settings")
    def test_get_claude_adapter(self, mock_settings):
        mock_settings.return_value.get.return_value = "claude"

        adapter = get_cli_adapter()

        assert isinstance(adapter, ClaudeCodeAdapter)

    @patch("pr_agent.algo.ai_handlers.cli_ai_handler.get_settings")
    def test_get_kiro_adapter(self, mock_settings):
        mock_settings.return_value.get.return_value = "kiro"

        adapter = get_cli_adapter()

        assert isinstance(adapter, KiroCLIAdapter)

    def test_get_adapter_by_name(self):
        adapter = get_cli_adapter("claude-code")
        assert isinstance(adapter, ClaudeCodeAdapter)

        adapter = get_cli_adapter("kiro-cli")
        assert isinstance(adapter, KiroCLIAdapter)

    def test_unknown_adapter_raises(self):
        with pytest.raises(ValueError, match="Unknown CLI tool"):
            get_cli_adapter("unknown-tool")

    def test_case_insensitive(self):
        adapter = get_cli_adapter("CLAUDE")
        assert isinstance(adapter, ClaudeCodeAdapter)

        adapter = get_cli_adapter("Claude-Code")
        assert isinstance(adapter, ClaudeCodeAdapter)


class TestCLIAIHandler:
    """Tests for CLIAIHandler."""

    @pytest.fixture
    def mock_adapter(self):
        """Create a mock adapter for testing."""
        adapter = MagicMock(spec=CLIAdapter)
        adapter.name = "Mock CLI"
        adapter.executable = "mock-cli"
        adapter.is_available.return_value = True
        adapter.get_executable_path.return_value = "/usr/bin/mock-cli"
        adapter.build_command.return_value = ["mock-cli", "-p", "prompt"]
        adapter.parse_response.return_value = "Mock response"
        return adapter

    def test_init_with_adapter(self, mock_adapter):
        handler = CLIAIHandler(adapter=mock_adapter)

        assert handler.adapter is mock_adapter
        mock_adapter.is_available.assert_called_once()

    def test_init_raises_when_cli_not_available(self, mock_adapter):
        mock_adapter.is_available.return_value = False

        with pytest.raises(RuntimeError, match="CLI not found"):
            CLIAIHandler(adapter=mock_adapter)

    def test_deployment_id(self, mock_adapter):
        handler = CLIAIHandler(adapter=mock_adapter)

        assert handler.deployment_id == "cli-proxy/mock-cli"

    @pytest.mark.asyncio
    async def test_chat_completion_success(self, mock_adapter):
        handler = CLIAIHandler(adapter=mock_adapter)

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"Mock response", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("pr_agent.algo.ai_handlers.cli_ai_handler.record_ai_call"):
                response, finish_reason = await handler.chat_completion(
                    model="test-model",
                    system="You are a helpful assistant",
                    user="Review this code",
                )

        assert response == "Mock response"
        assert finish_reason == "stop"
        mock_adapter.build_command.assert_called_once()
        mock_adapter.parse_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_chat_completion_combines_prompts(self, mock_adapter):
        handler = CLIAIHandler(adapter=mock_adapter)

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"response", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("pr_agent.algo.ai_handlers.cli_ai_handler.record_ai_call"):
                await handler.chat_completion(
                    model="model",
                    system="System prompt",
                    user="User prompt",
                )

        # Verify prompts are combined
        call_args = mock_adapter.build_command.call_args[0][0]
        assert "System prompt" in call_args
        assert "User prompt" in call_args
        assert "---" in call_args  # Separator

    @pytest.mark.asyncio
    async def test_chat_completion_timeout(self, mock_adapter):
        handler = CLIAIHandler(adapter=mock_adapter)

        mock_proc = AsyncMock()
        mock_proc.communicate.side_effect = TimeoutError()
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_proc.wait = AsyncMock()

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("asyncio.wait_for", side_effect=TimeoutError()):
                with pytest.raises(TimeoutError, match="timed out"):
                    await handler.chat_completion(
                        model="model",
                        system="system",
                        user="user",
                    )

    @pytest.mark.asyncio
    async def test_chat_completion_file_not_found(self, mock_adapter):
        handler = CLIAIHandler(adapter=mock_adapter)

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError()):
            with pytest.raises(RuntimeError, match="executable not found"):
                await handler.chat_completion(
                    model="model",
                    system="system",
                    user="user",
                )

    @pytest.mark.asyncio
    async def test_chat_completion_warns_on_image_path(self, mock_adapter):
        handler = CLIAIHandler(adapter=mock_adapter)

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"response", b"")
        mock_proc.returncode = 0

        with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
            with patch("pr_agent.algo.ai_handlers.cli_ai_handler.record_ai_call"):
                with patch("pr_agent.algo.ai_handlers.cli_ai_handler.get_logger") as mock_logger:
                    await handler.chat_completion(
                        model="model",
                        system="system",
                        user="user",
                        img_path="/path/to/image.png",
                    )

                    # Verify warning was logged
                    mock_logger.return_value.warning.assert_called()


class TestCLIAdaptersRegistry:
    """Tests for the CLI_ADAPTERS registry."""

    def test_all_adapters_registered(self):
        expected = {"claude", "claude-code", "kiro", "kiro-cli", "generic"}
        assert set(CLI_ADAPTERS.keys()) == expected

    def test_all_adapters_are_cli_adapter_subclasses(self):
        for name, adapter_class in CLI_ADAPTERS.items():
            assert issubclass(adapter_class, CLIAdapter), f"{name} is not a CLIAdapter subclass"

    def test_adapter_aliases_point_to_same_class(self):
        assert CLI_ADAPTERS["claude"] is CLI_ADAPTERS["claude-code"]
        assert CLI_ADAPTERS["kiro"] is CLI_ADAPTERS["kiro-cli"]
