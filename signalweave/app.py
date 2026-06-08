# Copyright (c) Microsoft. All rights reserved.
"""Hosted agent setup for SignalWeave.

Builds the :class:`~agent_framework.Agent` and runs it behind the Foundry
hosted HTTP server (``responses`` protocol).
"""

import os

from agent_framework import Agent, SkillsProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework.observability import configure_otel_providers
from agent_framework_foundry_hosting import ResponsesHostServer  # type: ignore
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from .paths import INSTRUCTIONS_PATH, SKILLS_DIR
from .tools import (
    complete_processing,
    describe_process,
    load_application,
    load_authorization,
    load_beneficiary_case,
    load_claim,
    load_eligibility,
    load_fraud_signal,
    load_lab_results,
    load_medical_report,
    load_provider,
    load_rate_class,
    load_surrender_case,
    log_escalation,
    run_checks,
)

# Load environment variables from .env file.
# override=False so that Foundry-injected env vars take precedence at runtime.
load_dotenv(override=False)

### Set up for OpenTelemetry tracing ###
# Instruments chat clients, agents, and tools automatically. Traces are exported
# to the Foundry Toolkit trace collector (gRPC port 4317) by default. If the
# OTEL_EXPORTER_OTLP_ENDPOINT environment variable is set, that endpoint is used
# instead (e.g. when running in Foundry or against another OTLP backend).
configure_otel_providers(
    vs_code_extension_port=4317,
    enable_sensitive_data=True,
)
### Set up for OpenTelemetry tracing ###

# Agent instructions live in a separate file for easy editing.
INSTRUCTIONS = INSTRUCTIONS_PATH.read_text(encoding="utf-8").strip()


def create_agent() -> Agent:
    """Construct the SignalWeave agent."""
    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=DefaultAzureCredential(),
    )

    skills_provider = SkillsProvider(skill_paths=SKILLS_DIR)

    return Agent(
        client=client,
        name="SignalWeave",
        instructions=INSTRUCTIONS,
        tools=[
            load_claim,
            load_eligibility,
            load_provider,
            load_authorization,
            load_fraud_signal,
            load_beneficiary_case,
            load_surrender_case,
            load_application,
            load_medical_report,
            load_lab_results,
            load_rate_class,
            run_checks,
            describe_process,
            complete_processing,
            log_escalation,
        ],
        context_providers=[skills_provider],
        # History is managed by the hosting infrastructure, so there is no
        # need to store it on the service side. Learn more at:
        # https://developers.openai.com/api/reference/resources/responses/methods/create
        default_options={"store": False},
    )


def main() -> None:
    """Build the agent and run the Foundry hosted HTTP server."""
    server = ResponsesHostServer(create_agent())
    server.run()


if __name__ == "__main__":
    main()
