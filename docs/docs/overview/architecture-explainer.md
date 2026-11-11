---
title: Architecture
sidebar_position: 2
---

# PR-Agent Architecture Explainer

PR-Agent is an open-source, AI-powered code review agent that automates pull request analysis across multiple Git providers. This document explains its architecture, components, and request flow.

## High-Level Architecture

```mermaid
flowchart TB
    subgraph Entry["Entry Points"]
        CLI["CLI<br/>(pr-agent)"]
        GHA["GitHub Action"]
        WH["Webhooks<br/>(GitHub/GitLab/Bitbucket/etc.)"]
        Lambda["AWS Lambda"]
    end

    subgraph Core["Core Engine"]
        Agent["PRAgent<br/>(Dispatcher)"]
        Registry["Command Registry"]
        Commands["Commands<br/>(review, describe, improve, ask...)"]
    end

    subgraph Providers["Git Providers"]
        GitHub["GitHub"]
        GitLab["GitLab"]
        Bitbucket["Bitbucket"]
        Azure["Azure DevOps"]
        Gitea["Gitea"]
        Gerrit["Gerrit"]
        CodeCommit["AWS CodeCommit"]
        Local["Local Git"]
    end

    subgraph AI["AI Layer"]
        LiteLLM["LiteLLM Handler"]
        Models["AI Models<br/>(GPT, Claude, Gemini, etc.)"]
    end

    subgraph Config["Configuration"]
        Settings["Settings<br/>(configuration.toml)"]
        Prompts["Prompt Templates"]
        RepoConfig[".pr_agent.toml"]
    end

    CLI --> Agent
    GHA --> Agent
    WH --> Agent
    Lambda --> Agent

    Agent --> Registry
    Registry --> Commands
    Commands --> Providers
    Commands --> AI
    
    LiteLLM --> Models
    AI --> LiteLLM

    Settings --> Agent
    Prompts --> Commands
    RepoConfig --> Settings
```

## Component Breakdown

### 1. Entry Points (`pr_agent/servers/`, `pr_agent/cli.py`)

PR-Agent supports multiple deployment modes:

| Entry Point | File | Description |
|-------------|------|-------------|
| CLI | `cli.py` | Local command-line usage |
| GitHub Action | `github_action_runner.py` | CI/CD integration |
| GitHub App | `github_app.py` | Webhook-based GitHub integration |
| GitLab Webhook | `gitlab_webhook.py` | Self-hosted GitLab integration |
| Bitbucket App | `bitbucket_app.py` | Bitbucket Cloud/Server |
| Gitea App | `gitea_app.py` | Gitea webhook handler |
| Gerrit Server | `gerrit_server.py` | Gerrit code review integration |
| AWS Lambda | `github_lambda_webhook.py`, `gitlab_lambda_webhook.py` | Serverless deployment |

### 2. Core Agent (`pr_agent/agent/`)

```mermaid
flowchart LR
    subgraph Agent["pr_agent.py"]
        Parse["parse_command()"]
        Prepare["prepare_command()"]
        Create["_create_command()"]
        Handle["handle_request()"]
    end

    subgraph Registry["command_registry.py"]
        Specs["COMMAND_SPECS"]
        Resolve["resolve_command()"]
    end

    Input["Command Input<br/>('/review', '/improve', etc.)"] --> Parse
    Parse --> Resolve
    Resolve --> Specs
    Specs --> Create
    Create --> Handle
    Handle --> Output["PR Comment/Output"]
```

The `PRAgent` class in `pr_agent.py` is the central dispatcher:
- Parses incoming commands (from comments, CLI, or webhooks)
- Resolves command aliases via the registry
- Instantiates the appropriate command class
- Executes the command and handles output

### 3. Command Registry (`pr_agent/agent/command_registry.py`)

The registry maps command names to their implementations:

```python
COMMAND_SPECS = {
    "review": CommandSpec(PRReviewer, check_run="review", ...),
    "describe": CommandSpec(PRDescription, check_run="describe", ...),
    "improve": CommandSpec(PRCodeSuggestions, check_run="suggestions", ...),
    "ask": CommandSpec(PRQuestions, ...),
    # ... more commands
}
```

### 4. Commands (`pr_agent/commands/`)

```mermaid
flowchart TB
    subgraph Commands["Available Commands"]
        Review["PRReviewer<br/>/review"]
        Describe["PRDescription<br/>/describe"]
        Improve["PRCodeSuggestions<br/>/improve"]
        Ask["PRQuestions<br/>/ask"]
        AskLine["PR_LineQuestions<br/>/ask_line"]
        Config["PRConfig<br/>/config"]
        Help["PRHelpMessage<br/>/help"]
        Labels["PRGenerateLabels<br/>/generate_labels"]
        Changelog["PRUpdateChangelog<br/>/update_changelog"]
        Docs["PRAddDocs<br/>/add_docs"]
        Similar["PRSimilarIssue<br/>/similar_issue"]
    end

    Review --> |"Analyzes code changes"| Output1["Review Summary<br/>Key Issues<br/>Security Concerns"]
    Describe --> |"Generates PR description"| Output2["Title<br/>Summary<br/>File Changes"]
    Improve --> |"Suggests improvements"| Output3["Code Suggestions<br/>Inline Comments"]
    Ask --> |"Answers questions"| Output4["AI Response"]
```

Each command follows a similar pattern:
1. Initialize with PR URL and git provider
2. Fetch PR diff and context
3. Build prompts with diff data
4. Call AI model for analysis
5. Parse response and publish results

### 5. Git Providers (`pr_agent/git_providers/`)

```mermaid
classDiagram
    class GitProvider {
        <<abstract>>
        +get_diff_files()
        +get_pr_description()
        +publish_comment()
        +publish_code_suggestions()
        +get_languages()
        +is_supported()
    }

    GitProvider <|-- GithubProvider
    GitProvider <|-- GitLabProvider
    GitProvider <|-- BitbucketProvider
    GitProvider <|-- BitbucketServerProvider
    GitProvider <|-- AzureDevopsProvider
    GitProvider <|-- GiteaProvider
    GitProvider <|-- GerritProvider
    GitProvider <|-- CodeCommitProvider
    GitProvider <|-- LocalGitProvider
    GitProvider <|-- PlainDiffGitProvider

    class GithubProvider {
        +PyGithub integration
        +GraphQL API support
    }

    class GitLabProvider {
        +python-gitlab integration
        +MR discussions
    }

    class BitbucketProvider {
        +REST API client
        +Cloud support
    }
```

The `GitProvider` abstract base class defines the interface for all provider implementations. Each provider handles:
- Authentication and API access
- Fetching PR/MR metadata and diffs
- Publishing comments and suggestions
- Managing labels and reviews

### 6. AI Handlers (`pr_agent/algo/ai_handlers/`)

```mermaid
flowchart LR
    subgraph Handlers["AI Handler Layer"]
        Base["BaseAiHandler"]
        LiteLLM["LiteLLMAIHandler"]
        OpenAI["OpenAIHandler"]
        LangChain["LangChainOpenAIHandler"]
    end

    subgraph Models["Supported Models"]
        GPT["OpenAI GPT-4/GPT-6"]
        Claude["Anthropic Claude"]
        Gemini["Google Gemini"]
        DeepSeek["DeepSeek"]
        Bedrock["AWS Bedrock"]
        Vertex["Google Vertex AI"]
        Azure["Azure OpenAI"]
        Local["Ollama/Local"]
    end

    LiteLLM --> |"litellm library"| Models
    Handlers --> LiteLLM
```

The `LiteLLMAIHandler` is the primary AI handler, using the [LiteLLM](https://github.com/BerriAI/litellm) library to provide a unified interface to 100+ LLM providers.

Key features:
- Automatic retry with fallback models
- Token counting and budget management
- Streaming response support
- Cloud authentication (Azure OIDC, AWS credentials, etc.)

### 7. Algorithm Layer (`pr_agent/algo/`)

```mermaid
flowchart TB
    subgraph Processing["Diff Processing"]
        GitPatch["git_patch_processing.py"]
        PRProc["pr_processing.py"]
        LangHandler["language_handler.py"]
    end

    subgraph Tokens["Token Management"]
        TokenHandler["token_handler.py"]
        TokenBudget["token_budget.py"]
    end

    subgraph Context["Context Building"]
        RepoContext["repo_context.py"]
        Skills["skills_loader.py"]
        Artifacts["artifacts.py"]
    end

    subgraph Output["Output Formatting"]
        CommentID["comment_identity.py"]
        RunOutput["run_output.py"]
        Findings["findings.py"]
    end

    PRProc --> TokenHandler
    TokenHandler --> TokenBudget
    RepoContext --> PRProc
    PRProc --> Output
```

Key algorithm modules:
- **token_handler.py** - Token counting using tiktoken
- **token_budget.py** - Managing prompt/response token limits
- **pr_processing.py** - PR diff preparation and chunking
- **repo_context.py** - Loading repository context files (AGENTS.md, etc.)
- **review_merge.py** - Merging chunked review results

## Request Flow

```mermaid
sequenceDiagram
    participant User
    participant Entry as Entry Point
    participant Agent as PRAgent
    participant Provider as Git Provider
    participant Algo as Algorithm Layer
    participant AI as AI Handler
    participant Model as LLM

    User->>Entry: /review command
    Entry->>Agent: handle_request(pr_url, command)
    Agent->>Agent: parse_command()
    Agent->>Provider: get_git_provider()
    Provider->>Provider: Authenticate & fetch PR
    Agent->>Algo: get_pr_diff()
    Algo->>Provider: get_diff_files()
    Provider-->>Algo: Diff data
    Algo->>Algo: Process & chunk diff
    Algo->>Algo: Build prompts
    Agent->>AI: chat_completion()
    AI->>Model: API Request
    Model-->>AI: Response
    AI-->>Agent: Parsed result
    Agent->>Provider: publish_comment()
    Provider-->>User: Review posted
```

## Configuration System

```mermaid
flowchart TB
    subgraph Sources["Configuration Sources"]
        Default["configuration.toml<br/>(defaults)"]
        Host["Host Settings<br/>(environment)"]
        Global["Global Repo Settings<br/>(.pr_agent.toml in settings repo)"]
        Repo["Repository Settings<br/>(.pr_agent.toml)"]
        CLI["CLI Arguments<br/>(--config.key=value)"]
    end

    subgraph Loader["config_loader.py"]
        Dynaconf["Dynaconf"]
        GetSettings["get_settings()"]
    end

    Default --> Dynaconf
    Host --> Dynaconf
    Global --> Dynaconf
    Repo --> Dynaconf
    CLI --> Dynaconf
    Dynaconf --> GetSettings

    GetSettings --> Commands
```

Configuration precedence (lowest to highest):
1. Default `configuration.toml`
2. Host-level environment variables
3. Global organization settings repo
4. Repository-level `.pr_agent.toml`
5. CLI arguments / comment commands

## Prompt System

PR-Agent uses a template-based prompt system with Jinja2 rendering. Here's how prompts are built:

```mermaid
flowchart TB
    subgraph Templates["1. Prompt Templates (TOML)"]
        SystemTpl["System Prompt Template<br/>(role, instructions, output schema)"]
        UserTpl["User Prompt Template<br/>(PR context, diff, task)"]
    end

    subgraph Variables["2. Variable Collection"]
        PRData["PR Metadata<br/>(title, branch, description)"]
        Diff["Processed Diff<br/>(with line numbers)"]
        Context["Repository Context<br/>(AGENTS.md, etc.)"]
        Settings["Command Settings<br/>(flags, thresholds)"]
        Skills["Skills Context<br/>(custom instructions)"]
        Tickets["Related Tickets<br/>(Jira, GitHub Issues)"]
    end

    subgraph Rendering["3. Jinja2 Rendering"]
        Budget["AttemptTokenBudget"]
        Jinja["SandboxedEnvironment"]
        Render["render_prompt_templates()"]
    end

    subgraph Output["4. Final Prompts"]
        SysPrompt["Rendered System Prompt"]
        UserPrompt["Rendered User Prompt"]
    end

    Templates --> Rendering
    Variables --> Rendering
    Budget --> Jinja
    Jinja --> Render
    Render --> Output
```

### Step 1: Load Prompt Templates

Prompts are defined in TOML files under `pr_agent/settings/`. Example from `pr_reviewer_prompts.toml`:

```toml
[pr_review_prompt]
system="""You are PR-Reviewer, a language model designed to review a Git Pull Request (PR).
Your task is to provide constructive and concise feedback for the PR.
...
{%- if repo_context %}
Repository context:
======
{{ repo_context }}
======
{% endif %}
...
"""

user="""PR Info:
Title: '{{ title }}'
Branch: '{{ branch }}'
Description: '{{ description }}'
...
The PR Diff:
======
{{ diff }}
======
...
"""
```

### Step 2: Collect Variables

Each command builds a `self.vars` dictionary with all data needed for the prompt:

```python
# From pr_reviewer.py __init__
self.vars = {
    "title": self.git_provider.pr.title,
    "branch": self.git_provider.get_pr_branch(),
    "description": self.pr_description,
    "language": self.main_language,
    "diff": "",  # filled later after token budgeting
    "num_max_findings": get_settings().pr_reviewer.num_max_findings,
    "require_score": get_settings().pr_reviewer.require_score_review,
    "extra_instructions": get_settings().pr_reviewer.extra_instructions,
    "repo_context": build_repo_context(self.git_provider),
    "skills_context": get_skills_context(),
    "related_tickets": get_settings().get('related_tickets', []),
    # ... more variables
}
```

### Step 3: Token Budgeting and Diff Fitting

Before rendering, the algorithm layer ensures the diff fits within token limits:

```mermaid
flowchart LR
    subgraph Input
        FullDiff["Full PR Diff"]
        MaxTokens["Model Token Limit"]
    end

    subgraph Processing["Token Budget Processing"]
        Count["Count Tokens"]
        Fit["Fit Diff to Budget"]
        Chunk["Chunk if Too Large"]
    end

    subgraph Output
        FittedDiff["Fitted Diff"]
        Remaining["Remaining Files List"]
    end

    FullDiff --> Count
    MaxTokens --> Count
    Count --> Fit
    Fit --> Chunk
    Chunk --> FittedDiff
    Chunk --> Remaining
```

The `AttemptTokenBudget` class manages this:
- Calculates available tokens after system prompt overhead
- Fits the diff to the remaining budget
- Tracks files that couldn't fit (reported as "additional modified files")

### Step 4: Render with Jinja2

The `render_prompt_templates()` method renders the final prompts:

```python
# From token_budget.py
def render_prompt_templates(self, variables: dict) -> tuple[str, str]:
    """Render this attempt handler's templates with the supplied variables."""
    environment = SandboxedEnvironment(undefined=StrictUndefined)
    system_prompt = environment.from_string(self.token_handler.system).render(variables)
    user_prompt = environment.from_string(self.token_handler.user).render(variables)
    return system_prompt, user_prompt
```

Key features:
- **SandboxedEnvironment** — Prevents code execution in templates
- **StrictUndefined** — Fails fast if a variable is missing
- **Conditional sections** — `{% if repo_context %}...{% endif %}` includes content only when present

### Step 5: Prepare and Send Request

After rendering, the prompts are packaged into an API request:

```mermaid
sequenceDiagram
    participant Cmd as Command
    participant Budget as AttemptTokenBudget
    participant AI as AI Handler
    participant Model as LLM API

    Cmd->>Budget: render_prompt_templates(vars)
    Budget-->>Cmd: (system_prompt, user_prompt)
    Cmd->>Budget: prepare_request(ai_handler, system, user)
    Budget->>Budget: normalize_request_prompts()
    Budget->>Budget: count_request_tokens()
    Budget-->>Cmd: FittedPrompt
    Cmd->>AI: chat_completion(model, system, user)
    AI->>Model: API Request (messages)
    Model-->>AI: Response
    AI-->>Cmd: Parsed Output
```

### Variable Sources Summary

| Variable | Source | Example |
|----------|--------|---------|
| `title` | Git Provider | "Fix null pointer in auth module" |
| `diff` | `pr_processing.py` | Unified diff with line numbers |
| `repo_context` | `repo_context.py` | Contents of AGENTS.md |
| `skills_context` | `skills_loader.py` | Custom review instructions |
| `related_tickets` | `ticket_pr_compliance_check.py` | Jira/GitHub issue content |
| `extra_instructions` | Configuration | User-defined review focus |
| `require_*` | Settings | Feature flags for output sections |

## Data Flow Summary

```mermaid
flowchart TB
    subgraph Input
        PR["Pull Request URL"]
        CMD["Command<br/>(/review, /improve, etc.)"]
    end

    subgraph Fetch
        Diff["Fetch Diff"]
        Meta["Fetch Metadata"]
        Context["Load Context"]
    end

    subgraph Process
        Chunk["Chunk Large Diffs"]
        Token["Token Budgeting"]
        Prompt["Build Prompts"]
    end

    subgraph AI
        Call["AI API Call"]
        Parse["Parse Response"]
        Merge["Merge Chunks"]
    end

    subgraph Output
        Comment["PR Comment"]
        Inline["Inline Suggestions"]
        Labels["Labels"]
        JSON["JSON Output"]
    end

    PR --> Fetch
    CMD --> Fetch
    Fetch --> Process
    Process --> AI
    AI --> Output
```

## Key Design Patterns

1. **Provider Abstraction** - All Git platforms implement the same interface
2. **Command Pattern** - Each command is a self-contained class
3. **Fallback Chain** - Automatic retry with weaker models on failure
4. **Chunked Processing** - Large PRs are split into manageable pieces
5. **Token Budget Management** - Precise control over prompt sizes
6. **Configuration Layering** - Hierarchical settings with clear precedence
7. **Identity Markers** - Comments carry hidden markers for deduplication

## File Structure Overview

```
pr_agent/
├── agent/                  # Core dispatcher
│   ├── pr_agent.py        # Main PRAgent class
│   └── command_registry.py # Command mapping
├── commands/              # Command implementations
│   ├── pr_reviewer.py
│   ├── pr_description.py
│   ├── pr_code_suggestions.py
│   └── ...
├── git_providers/         # Git platform integrations
│   ├── github_provider.py
│   ├── gitlab_provider.py
│   └── ...
├── algo/                  # Core algorithms
│   ├── ai_handlers/       # AI model integrations
│   ├── token_handler.py
│   ├── pr_processing.py
│   └── ...
├── servers/               # Webhook servers
│   ├── github_app.py
│   ├── gitlab_webhook.py
│   └── ...
├── settings/              # Configuration & prompts
│   ├── configuration.toml
│   ├── pr_reviewer_prompts.toml
│   └── ...
└── cli.py                 # CLI entry point
```

## FAQ

### Can I use Claude Code or Kiro CLI instead of an API key?

**Short answer:** Not directly. These are interactive terminal agents, not API endpoints.

**Why not?** PR-Agent expects an HTTP API that accepts JSON requests and returns structured responses. Claude Code/Kiro CLI are designed for human-in-the-loop usage with their own session state and tool management.

**Workaround:** Create a local proxy server that wraps the CLI's non-interactive mode:

```python
# claude_proxy.py
from fastapi import FastAPI
from pydantic import BaseModel
import subprocess, json

app = FastAPI()

class ChatRequest(BaseModel):
    messages: list

@app.post("/v1/chat/completions")
async def chat(request: ChatRequest):
    prompt = "\n".join(f"{m['role']}: {m['content']}" for m in request.messages)
    result = subprocess.run(
        ["claude", "-p", prompt, "--output-format", "json"],
        capture_output=True, text=True, timeout=300
    )
    response = json.loads(result.stdout)
    return {
        "choices": [{"message": {"content": response.get("result", "")}}],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0}
    }
```

Then configure PR-Agent to use it:
```toml
[config]
model = "openai/claude-proxy"

[openai]
api_base = "http://localhost:8000/v1"
key = "dummy"
```

**Alternatives without separate API keys:**
- **AWS Bedrock** — Use Claude via existing AWS credentials
- **Google Vertex AI** — Use Claude via existing GCP credentials
- **Ollama** — Run open-source models locally (requires GPU)

## Further Reading

- [Installation Guide](../installation/github.md)
- [Configuration Options](../usage-guide/configuration_options.md)
- [Changing a Model](../usage-guide/changing_a_model.md)
- [Contributing Guidelines](https://github.com/The-PR-Agent/pr-agent/blob/main/CONTRIBUTING.md)
