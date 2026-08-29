import os
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# ==========================================
# Azure OpenAI Settings
# ==========================================
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://devpulse-openai.openai.azure.com/")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
AZURE_OPENAI_MINI_DEPLOYMENT = os.getenv("AZURE_OPENAI_MINI_DEPLOYMENT", "gpt-5-mini")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")

# ==========================================
# Foundry Agent Service (Responses API) Settings
# NOTE: this is a DIFFERENT surface from plain Azure OpenAI above.
# It talks to a Foundry *project* endpoint, not the AOAI resource endpoint,
# and auths with Azure AD (DefaultAzureCredential), not AZURE_OPENAI_KEY.
# Format: https://<resource-name>.services.ai.azure.com/api/projects/<project-name>
# ==========================================
AZURE_AI_PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT", "")
AZURE_AI_AGENT_NAME = os.getenv("AZURE_AI_AGENT_NAME", "maintainer-assistant-agent")

# ==========================================
# Azure AI Search Settings & Index Names
# ==========================================
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "https://devpulse-search.search.windows.net")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY", "")
AZURE_SEARCH_ISSUES_INDEX = os.getenv("AZURE_SEARCH_ISSUES_INDEX", "devpulse-issues-index")
AZURE_SEARCH_PRS_INDEX = os.getenv("AZURE_SEARCH_PRS_INDEX", "devpulse-prs-index")
AZURE_SEARCH_CODE_INDEX = os.getenv("AZURE_SEARCH_CODE_INDEX", "devpulse-codebase-index")

# ==========================================
# Azure Blob Storage & Content Safety
# ==========================================
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "devpulse-repos")

AZURE_CONTENT_SAFETY_ENDPOINT = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT", "")
AZURE_CONTENT_SAFETY_KEY = os.getenv("AZURE_CONTENT_SAFETY_KEY", "")

AZURE_AI_AGENT_NAME = os.getenv("AZURE_AI_AGENT_NAME", "assistant-agent")
AZURE_AI_CRITIC_NAME = os.getenv("AZURE_AI_CRITIC_NAME", "critic-agent")

# ==========================================
# GitHub API Credentials
# ==========================================
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
DEFAULT_REPO = os.getenv("DEFAULT_REPO", "trpc/trpc")