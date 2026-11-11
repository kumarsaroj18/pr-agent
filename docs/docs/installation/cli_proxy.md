---
title: "CLI Proxy Server"
sidebar_position: 10
---

# CLI Proxy Server

The CLI Proxy Server allows you to use PR-Agent with CLI-based AI agents like Claude Code or Kiro CLI, without needing a separate LLM API key. It routes AI completions through your locally-installed CLI tools instead of HTTP APIs.

## When to Use

- You have Claude Code or Kiro CLI with an active subscription
- You don't have (or don't want to use) a separate OpenAI/Anthropic API key
- You want to integrate PR-Agent into your existing CLI-based AI workflow

## Prerequisites

- One of these CLI tools installed and authenticated:
  - [Claude Code](https://docs.anthropic.com/en/docs/claude-code) (`claude` command)
  - [Kiro CLI](https://kiro.dev) (`kiro` command)
  - Any CLI tool that accepts prompts and returns text
- Git provider token (GitHub, GitLab, etc.) for accessing repositories

## Quick Start

### Using Docker (Recommended)

```bash
# Set your git provider token
export GITHUB_TOKEN=your_github_token

# Start the proxy server
docker compose -f docker/docker-compose.cli-proxy.yml up --build

# The server is now running at http://localhost:8080
```

### Using Docker Directly

```bash
# Build the CLI proxy image
docker build -f docker/Dockerfile --target cli_proxy -t pr-agent-cli-proxy .

# Run it (mount your CLI tool config if needed)
docker run -p 8080:8080 \
  -e GITHUB.USER_TOKEN=$GITHUB_TOKEN \
  -e CLI_PROXY.TOOL=claude \
  pr-agent-cli-proxy
```

### Running Locally

```bash
# Install dependencies
uv sync

# Set environment variables
export CLI_PROXY_TOOL=claude  # or 'kiro' or 'generic'
export GITHUB__USER_TOKEN=your_github_token

# Start the server
uv run python -m pr_agent.servers.cli_proxy_server
```

## API Endpoints

### Health Check

```bash
curl http://localhost:8080/health
```

Returns the status of the CLI tool and server.

### Review a PR

```bash
curl -X POST http://localhost:8080/api/v1/review \
  -H "Content-Type: application/json" \
  -d '{"pr_url": "https://github.com/owner/repo/pull/123"}'
```

### Generate PR Description

```bash
curl -X POST http://localhost:8080/api/v1/describe \
  -H "Content-Type: application/json" \
  -d '{"pr_url": "https://github.com/owner/repo/pull/123"}'
```

### Get Code Improvement Suggestions

```bash
curl -X POST http://localhost:8080/api/v1/improve \
  -H "Content-Type: application/json" \
  -d '{"pr_url": "https://github.com/owner/repo/pull/123"}'
```

### Ask a Question

```bash
curl -X POST http://localhost:8080/api/v1/ask \
  -H "Content-Type: application/json" \
  -d '{
    "pr_url": "https://github.com/owner/repo/pull/123",
    "question": "What are the security implications of this change?"
  }'
```

### Run Any Command

```bash
curl -X POST "http://localhost:8080/api/v1/command?command=generate_labels" \
  -H "Content-Type: application/json" \
  -d '{"pr_url": "https://github.com/owner/repo/pull/123"}'
```

## Configuration

Configuration can be set via environment variables or in `.pr_agent.toml`:

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CLI_PROXY_TOOL` or `CLI_PROXY.TOOL` | CLI tool to use: `claude`, `kiro`, or `generic` | `claude` |
| `CLI_PROXY_TIMEOUT` or `CLI_PROXY.TIMEOUT` | Timeout in seconds for CLI commands | `300` |
| `CLI_PROXY_VERBOSE` or `CLI_PROXY.VERBOSE` | Enable verbose logging | `false` |
| `CLI_PROXY_EXECUTABLE_PATH` or `CLI_PROXY.EXECUTABLE_PATH` | Custom path to CLI executable | (auto-detected) |
| `CLI_PROXY_GENERIC_COMMAND` or `CLI_PROXY.GENERIC_COMMAND` | Command template for generic adapter | `"{executable} {prompt}"` |

### TOML Configuration

```toml
[cli_proxy]
tool = "claude"           # claude, kiro, or generic
timeout = 300             # seconds
verbose = false
executable_path = ""      # custom path to CLI tool
generic_command = ""      # command template for generic adapter
```

## Supported CLI Tools

### Claude Code

Uses the `claude` command with print mode:

```bash
claude -p "your prompt" --output-format json --no-input
```

Set with `CLI_PROXY_TOOL=claude`.

### Kiro CLI

Uses the `kiro` command:

```bash
kiro chat --message "your prompt" --no-interactive
```

Set with `CLI_PROXY_TOOL=kiro`.

### Generic CLI Tool

For other CLI tools, use the generic adapter with a custom command template:

```bash
export CLI_PROXY_TOOL=generic
export CLI_PROXY_GENERIC_COMMAND="my-ai-tool --prompt {prompt}"
```

The `{prompt}` and `{executable}` placeholders are replaced at runtime.

## Docker Compose Configuration

The `docker/docker-compose.cli-proxy.yml` file supports these environment variables:

| Variable | Description |
|----------|-------------|
| `CLI_PROXY_PORT` | Host port (default: 8080) |
| `OPENAI_API_KEY` | OpenAI key (if using as fallback) |
| `ANTHROPIC_API_KEY` | Anthropic key (if using as fallback) |
| `GITHUB_TOKEN` | GitHub personal access token |
| `GITLAB_TOKEN` | GitLab personal access token |
| `BITBUCKET_USERNAME` | Bitbucket username |
| `BITBUCKET_PASSWORD` | Bitbucket app password |
| `CONFIG_FILE` | Path to custom `.pr_agent.toml` |

## Integration Examples

### Using with Claude Code MCP

You can expose PR-Agent as an MCP tool for Claude Code:

```json
{
  "mcpServers": {
    "pr-agent": {
      "command": "curl",
      "args": ["-X", "POST", "http://localhost:8080/api/v1/review", "-H", "Content-Type: application/json", "-d"]
    }
  }
}
```

### Using in CI/CD

```yaml
# GitHub Actions example
- name: Start PR-Agent Proxy
  run: |
    docker compose -f docker/docker-compose.cli-proxy.yml up -d
    sleep 5  # Wait for startup

- name: Review PR
  run: |
    curl -X POST http://localhost:8080/api/v1/review \
      -H "Content-Type: application/json" \
      -d '{"pr_url": "${{ github.event.pull_request.html_url }}"}'
```

## Troubleshooting

### CLI Tool Not Found

If you get "CLI tool not available" errors:

1. Verify the CLI tool is installed: `which claude` or `which kiro`
2. Check if it's in PATH inside Docker (you may need to mount the binary)
3. Use `CLI_PROXY_EXECUTABLE_PATH` to specify the full path

### Timeout Errors

For large PRs, increase the timeout:

```bash
export CLI_PROXY_TIMEOUT=600  # 10 minutes
```

### Authentication Issues

Make sure your CLI tool is authenticated:

```bash
# For Claude Code
claude auth status

# For Kiro CLI
kiro auth status
```

### Verbose Logging

Enable verbose mode to see CLI commands and responses:

```bash
export CLI_PROXY_VERBOSE=true
```

## Architecture

```
┌─────────────────┐     HTTP      ┌──────────────────┐
│  Your Client    │──────────────▶│  CLI Proxy       │
│  (curl, script) │               │  Server (FastAPI)│
└─────────────────┘               └────────┬─────────┘
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │  CLIAIHandler    │
                                  │  (routes to CLI) │
                                  └────────┬─────────┘
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │  CLI Adapter     │
                                  │  (subprocess)    │
                                  └────────┬─────────┘
                                           │
                                           ▼
                                  ┌──────────────────┐
                                  │  Claude/Kiro CLI │
                                  │  (local tool)    │
                                  └──────────────────┘
```

The proxy intercepts AI completion calls and routes them through your local CLI tool instead of making HTTP API calls, allowing you to use your existing CLI subscription.
