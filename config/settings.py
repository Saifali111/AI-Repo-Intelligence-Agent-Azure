"""
DevPulse Configuration and Environment Settings.
Loads and centralizes configuration values for Azure OpenAI, AI Foundry, AI Search, and GitHub.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Azure OpenAI Configuration
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "https://devpulse-openai.openai.azure.com/")
AZURE_OPENAI_KEY = os.getenv("AZURE_OPENAI_KEY", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-5")
AZURE_OPENAI_MINI_DEPLOYMENT = os.getenv("AZURE_OPENAI_MINI_DEPLOYMENT", "gpt-5-mini")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-large")

# Azure AI Foundry Configuration
AZURE_AI_PROJECT_ENDPOINT = os.getenv("AZURE_AI_PROJECT_ENDPOINT", "")
AZURE_AI_AGENT_NAME = os.getenv("AZURE_AI_AGENT_NAME", "assistant-agent")
AZURE_AI_CRITIC_NAME = os.getenv("AZURE_AI_CRITIC_NAME", "critic-agent")

# Azure AI Search Configuration
AZURE_SEARCH_ENDPOINT = os.getenv("AZURE_SEARCH_ENDPOINT", "https://devpulse-search.search.windows.net")
AZURE_SEARCH_KEY = os.getenv("AZURE_SEARCH_KEY", "")
AZURE_SEARCH_ISSUES_INDEX = os.getenv("AZURE_SEARCH_ISSUES_INDEX", "devpulse-issues-index")
AZURE_SEARCH_PRS_INDEX = os.getenv("AZURE_SEARCH_PRS_INDEX", "devpulse-prs-index")
AZURE_SEARCH_CODE_INDEX = os.getenv("AZURE_SEARCH_CODE_INDEX", "devpulse-codebase-index")

# Storage and Content Safety
AZURE_STORAGE_CONNECTION_STRING = os.getenv("AZURE_STORAGE_CONNECTION_STRING", "")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "devpulse-repos")
AZURE_CONTENT_SAFETY_ENDPOINT = os.getenv("AZURE_CONTENT_SAFETY_ENDPOINT", "")
AZURE_CONTENT_SAFETY_KEY = os.getenv("AZURE_CONTENT_SAFETY_KEY", "")

# GitHub API Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
DEFAULT_REPO = os.getenv("DEFAULT_REPO", "trpc/trpc")