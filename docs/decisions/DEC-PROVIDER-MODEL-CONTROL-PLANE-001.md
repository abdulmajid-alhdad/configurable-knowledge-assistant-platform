# DEC-PROVIDER-MODEL-CONTROL-PLANE-001: Multi-provider provider/model control plane

- Status: Approved
- Date: 2026-09-14

## Context

The platform currently has OpenRouter as its first and primary implemented
remote provider. The control plane must support additional remote providers
without treating OpenRouter as a special architectural case. Provider,
Credential, Model, Runtime Configuration, and Usage are separate concepts and
must remain separate in the product, APIs, and runtime boundaries.

The approved conceptual chain is:

```text
Provider
  -> Credential
  -> Model Catalogue
  -> Runtime Configuration
  -> Execution
  -> Usage
```

The browser never communicates directly with a remote AI provider. All remote
provider access follows:

```text
Browser -> FastAPI -> provider adapter/client
```

## Decision

The Providers & Models control plane is multi-provider by design. A Provider is
a supported remote integration. A Credential identifies how the platform
authenticates to that provider. A Model Catalogue contains provider-specific
model identifiers and capabilities. Runtime Configuration selects the effective
models used for execution. Usage is read-only operational observability.

OpenRouter is one provider implementation, not a privileged control-plane
case. New providers must fit the same conceptual chain and adapter boundary.

### Model catalogue

Provider-specific backend integrations obtain model catalogues. The browser
does not treat a hard-coded provider model list as authoritative. Catalogues
are filtered by capability, with independent Generation and Embedding
catalogues. The persisted identifier is the canonical provider model ID, not a
friendly alias. A UI may show a display name or alias only when it is clearly
distinguished from that provider model ID.

### Runtime configuration

Under the current contract, runtime configuration is SYSTEM-global. There is
one effective Generation configuration and one effective Embedding
configuration at a time. Their providers may differ.

The canonical resolver remains the single runtime source of configuration:

1. A complete, valid, active persisted SYSTEM configuration is authoritative.
2. When no persisted active configuration exists, the explicit environment
   bootstrap/fallback configuration is used.
3. A deliberately active persisted configuration that is incomplete or invalid
   fails closed. It does not mix fields with, or silently fall back to, the
   environment configuration.

Generation and Embedding are separate capability-specific configurations. A
generation configuration must not be implicitly reused for embedding, and vice
versa.

## Runtime semantics

Generation models may change independently, but the selectable model must be
compatible with the implemented adapter for the selected provider. The
effective configuration selected by the canonical resolver is the one consumed
by provider execution adapters.

Embedding model changes are compatibility-sensitive. Indexed vectors cannot be
assumed compatible merely because embedding dimensions match. Once indexed
Knowledge exists, changing the embedding model or dimensions is blocked unless
an explicit, approved migration/reindex workflow exists. This decision does not
implement that reindex workflow.

Existing frozen execution gates remain unchanged. A Workspace that is
`SUSPENDED`, or has `ai_execution_enabled=false`, remains blocked before remote
execution. This decision does not change egress policy, provider safety,
retrieval, evidence, or model-output contracts.

Only remote models are supported. The platform does not introduce local model
runtimes, local model paths, LangChain, or LlamaIndex.

## UX responsibilities

Providers & Models answers which provider and model executes. Its primary view
is effective operational state: effective Generation and Embedding provider,
canonical model ID, endpoint, credential reference, dimensions where relevant,
and whether the source is persisted configuration or environment fallback.

The page provides clear Change Model actions when supported by the backend. It
shows the provider catalogue and provider structural availability second.
Workspace administrative provider availability is explicitly separate from
SYSTEM-global runtime model selection. Environment fallback and lower-level
configuration are advanced operational details rather than the primary UX.

Assistant-level legacy provider/model references and `model_configuration`
metadata must not be displayed as runtime-authoritative unless an approved
runtime contract makes them authoritative.

## Credential boundary

Provider is not Credential. Credentials answers how the platform authenticates;
Providers & Models answers which provider/model executes.

The current Workspace-scoped Credential Registry remains metadata and a
control-plane surface only. It is not authoritative runtime secret resolution
and must not be connected to SYSTEM-global runtime configuration by this
decision.

Current runtime credential resolution remains:

```text
credential reference name
  -> EnvironmentCredentialResolver
  -> server environment variable
```

Only credential references cross configuration boundaries. Provider secrets,
authorization headers, and raw credential values never reach the browser.
An authoritative System Credential Registry and Vault runtime adapter are
deferred to a separate architecture decision.

## Usage boundary

Usage answers what was consumed and what it cost. It is read-only operational
observability and must use real provider-returned usage data only. The platform
does not invent cost attribution or estimate provider billing locally.

Provider/key-level totals may be shown when that is all the provider API
authoritatively supplies. Model-level usage may be shown only when
authoritative provider data exists. Historical usage must never be relabeled as
belonging to a model selected later.

Credentials, Providers & Models, and Usage must not duplicate one another's
responsibilities.

## Explicit non-goals

This decision does not introduce:

- multiple simultaneously active generation models;
- per-assistant runtime model routing;
- model fallback chains;
- load balancing across models or providers;
- a model profile registry;
- an authoritative System Credential Store;
- a Vault runtime adapter;
- embedding reindex or migration implementation; or
- provider billing normalization across vendors.

## Consequences

SYSTEM administration owns global runtime provider/model configuration.
WORKSPACE authority remains separate and cannot select or alter the effective
global runtime configuration merely through Workspace membership or Workspace
provider metadata.

The runtime must continue to expose configuration provenance. A successful
persisted configuration update is only presented as active once the resolver
selects it for subsequent execution. Disabling a persisted configuration allows
the explicit environment fallback to become effective under the resolver
precedence rule.

Provider catalogue presence and structural configuration are not claims of live
provider connectivity. Loading the control-plane pages must not invoke remote
generation, embedding, or vector operations.

## Stage 4 implementation implications

Stage 4 implementation keeps the canonical ProviderConfigurationResolver as
the single boundary between persisted runtime configuration, environment
fallback, and execution adapters. Direct execution-path reads of model or
embedding environment settings are limited to the explicit environment fallback
source.

Current environment values remain a safe bootstrap fallback while no persisted
active configuration exists. Provider/model management APIs are SYSTEM
authorized, persist credential references only, and expose sanitized effective
configuration without secrets. Workspace provider settings remain
administrative metadata until an explicit future scope contract changes that
status.

The architecture preserves no direct Supabase access from the browser and no
direct provider secret exposure to the browser.

## Future extension points

Future decisions may define an authoritative System Credential Registry and
Vault integration, an approved embedding reindex/migration workflow, and
additional provider-specific catalogue integrations. Such work must preserve
the canonical resolver, capability separation, credential boundary, SYSTEM vs
WORKSPACE authority separation, and fail-closed configuration semantics.

Any future support for routing, fallback, load balancing, per-assistant
selection, or multiple active models requires a separate approved decision and
an explicit execution, provenance, compatibility, and usage-accounting
contract.
