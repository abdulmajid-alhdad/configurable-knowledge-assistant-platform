# DEC-WORKSPACE-PROVIDER-MODEL-RUNTIME-001: Workspace provider and model runtime policy

- Status: Approved
- Date: 2026-09-17

## Context

`DEC-PROVIDER-MODEL-CONTROL-PLANE-001` established a multi-provider control
plane with one SYSTEM-global effective Generation configuration and one
SYSTEM-global effective Embedding configuration. It also classified
`workspace_provider_settings` as administrative metadata that did not affect
execution.

That separation is no longer sufficient. A provider setting shown for a
Workspace must have an immediate, server-enforced execution effect. In
particular, `workspace_provider_settings.enabled=false` must prevent that
Workspace from executing Generation or Embedding through the provider before
any remote request. Workspace administrators also need meaningful model
availability policy and Workspace-specific Generation and Embedding selection.

Descriptive-only provider status, endpoint, or model metadata is prohibited in
the product. If a control is presented as an operational setting, the canonical
runtime path must consume and enforce it.

This decision extends and supersedes the SYSTEM-global runtime-selection and
descriptive Workspace-provider portions of
`DEC-PROVIDER-MODEL-CONTROL-PLANE-001`. Its provider catalogue, remote-only,
credential secrecy, browser-to-FastAPI, usage, and execution-safety decisions
remain in force unless explicitly changed here.

## Decision

The platform separates five runtime concepts:

1. a SYSTEM-owned provider integration;
2. a provider-owned model catalogue;
3. an enforced Workspace provider policy;
4. an enforced Workspace model policy; and
5. a capability-specific Workspace runtime selection.

SYSTEM owns:

- supported provider integrations and their capabilities;
- provider catalogue integrations and canonical model identifiers;
- the single authoritative capability-specific execution endpoint and
  credential reference for each provider integration;
- safe capability-specific provider integration defaults;
- the System default Generation configuration; and
- the System default Embedding configuration.

Each Workspace owns the effective policy state that determines:

- which providers are enabled or disabled;
- which provider models are enabled;
- the runtime mode for Generation and Embedding; and
- its selected provider and model when a capability is in `SELECTED` mode.

Workspace scope does not imply Workspace-member administrative authority.
Provider/model policy and selection remain managed through canonical SYSTEM
authority unless a later decision explicitly delegates them. Workspace
membership or ordinary Workspace permissions are insufficient.

## Provider policy persistence

`platform.workspace_provider_settings` is evolved rather than replaced. Its
existing `(workspace_id, provider_code)` identity and `enabled` value already
model the required provider-policy predicate. After the enforcement migration:

- `enabled` is authoritative for all provider execution in that Workspace;
- `enabled=false` denies both Generation and Embedding through that provider;
- the check occurs on every execution after Workspace identity and operational
  gates are known and before credential resolution or any provider request;
- changing `enabled` takes effect without restart or login refresh; and
- no resolver fallback may bypass the disabled provider.

The current `administrative_status` and `base_url_override` fields do not become
runtime authority. Workspace endpoint overrides would conflict with the
SYSTEM-owned integration and credential boundary. They must be removed from
product UX and deprecated for later schema cleanup unless a separate decision
gives them an enforced meaning. They must not influence runtime resolution.

Provider integration is the single runtime authority for execution endpoint,
credential reference, and capability-specific integration defaults. A
Workspace provider row is policy, not an integration definition. Neither a
Workspace selection nor a System default independently owns or overrides an
endpoint or credential reference.

Environment bootstrap values may establish an in-memory/bootstrap SYSTEM
provider integration when no persisted integration definition is available.
After that boundary is resolved, execution still obtains endpoint and
credential reference through the canonical provider-integration abstraction;
the System default and Workspace selection never read those environment fields
as a second authority.

## Model policy semantics

Workspace model availability uses an explicit allow-list with an explicit
inheritance mode. A deny-list is rejected because absence would become
ambiguous as provider catalogues change.

For each `(workspace_id, provider_code, capability)`, policy has one mode:

- `INHERIT_SUPPORTED`: all models in the platform's locally established
  supported-model integration policy for that provider and capability are
  eligible; or
- `EXPLICIT_ALLOWLIST`: only canonical model IDs explicitly enabled for that
  Workspace, provider, and capability are eligible.

The locally established supported-model policy is persisted or otherwise
available locally at execution time. It is updated only through an explicit
SYSTEM administration, selection, policy, or catalogue-refresh workflow.
`INHERIT_SUPPORTED` never calls a remote provider catalogue during request
execution.

The model policy and its allow-list entries are separate from the live remote
model catalogue. A catalogue response is a configuration/control-plane input:
it helps an administrator discover, classify, validate, and explicitly select
models. Catalogue presence does not itself grant Workspace availability, and a
later catalogue refresh does not silently mutate Workspace policy or runtime
selection. Likewise, allowing a model does not select it for execution.

Changing to `EXPLICIT_ALLOWLIST` is atomic and is rejected if the resulting
list would make the Workspace's current Generation or Embedding state invalid.
An empty explicit allow-list is valid only when the same atomic mutation places
the capability in `DISABLED`; it cannot leave an `INHERIT` or `SELECTED`
capability without an allowed effective model.

Unknown or retired canonical model IDs are never silently substituted. If a
selected model disappears from a later live catalogue, its selection and
history remain visible where operationally relevant and its local policy state
does not change automatically. A replacement requires an explicit valid
selection. A provider rejection during later execution is a bounded
provider/runtime failure, not permission to choose another model.

## Workspace runtime selection

Each Workspace has exactly one authoritative runtime mode for each capability:

- `INHERIT`: there is no Workspace-specific provider/model override. Resolution
  considers the active System default and, only when no active persisted System
  default exists, the environment bootstrap candidate. Every inherited
  candidate remains subject to Workspace provider and model policy.
- `SELECTED`: execution uses the Workspace's explicit provider/model selection.
  An invalid or denied selection fails closed; it does not fall back to the
  System default or environment.
- `DISABLED`: the capability is intentionally unavailable for the Workspace.
  No Workspace selection, System default, or environment candidate is used and
  execution makes zero provider network calls.

The physical schema for these modes is chosen during implementation, but the
three states are authoritative product and runtime semantics. Each Workspace
has at most one complete effective state/configuration for Generation and one
for Embedding. Database uniqueness and serialized protected mutation
functions, not application convention alone, enforce this invariant.

A Workspace selection stores references to:

- Workspace;
- capability;
- SYSTEM provider integration/provider code;
- canonical provider model ID;
- authoritative embedding dimensions when capability is Embedding; and
- runtime mode/state.

It does not duplicate endpoint or credential reference. Those values are
resolved atomically from the selected SYSTEM provider integration. This avoids
Workspace-specific copies drifting from the adapter and credential boundary.
Raw credential values are never stored in provider policy or runtime-selection
rows.

The System default Generation and Embedding configurations likewise select only
the provider integration/provider code, canonical model ID, and dimensions
where applicable. They do not independently own endpoint or credential
reference. Existing SYSTEM-global runtime configuration revisions become
System defaults during migration; they cease to be mandatory execution choices
for every Workspace.

Existing `runtime_model_configuration_revisions.endpoint` and
`runtime_model_configuration_revisions.credential_reference` values may be
retained temporarily as immutable legacy/historical snapshots for a
backward-safe migration. Once this contract is activated, they are not an
independent source of execution authority. Runtime endpoint and credential
reference always resolve from the canonical SYSTEM provider integration.
Later schema cleanup may deprecate or remove the redundant legacy columns after
all readers have migrated.

## Runtime resolution and precedence

Resolution is capability-specific and atomic. Runtime mode controls precedence:

1. `DISABLED` stops resolution and denies execution.
2. `SELECTED` uses the complete Workspace selection and permits no fallback.
3. `INHERIT` uses the active System default; only when no active persisted
   System default exists may it consider the environment bootstrap candidate.

Precedence chooses exactly one complete candidate. It does not mix fields
between candidates.

Every candidate, including a System default or environment bootstrap candidate,
must pass the selected Workspace's provider and model policy. A failure does
not cause the resolver to try the next candidate. Specifically:

- a present but invalid `SELECTED` Workspace selection fails closed;
- a Workspace selection whose provider or model is disabled fails closed;
- in `INHERIT` mode, a System default whose provider or model is disabled fails
  closed rather than falling through to environment;
- in `INHERIT` mode, when environment bootstrap is the only candidate, its
  provider and model are still checked against Workspace policy;
- `DISABLED` never considers any candidate; and
- no automatic provider or model substitution is permitted.

System defaults are therefore defaults only. A Workspace may select another
allowed provider/model, but the default is never forced over an explicit valid
Workspace selection.

The resolver returns either a disabled outcome or one complete effective
configuration with provenance: `WORKSPACE_SELECTION`, `SYSTEM_DEFAULT`, or
`ENVIRONMENT_BOOTSTRAP`. Provider/model selection comes from the chosen
Workspace/System/bootstrap candidate. Endpoint and credential reference come
only from the canonical SYSTEM provider integration. The effective result also
includes Workspace ID, capability, dimensions where applicable, and structural
readiness. Secret values are resolved later and are not part of this result.

## Execution order

All Generation and Embedding execution follows this order:

```text
Request
  -> Workspace identity
  -> Workspace operational gates
  -> resolve Workspace capability mode and configuration candidate
  -> verify provider enabled for Workspace
  -> verify selected model enabled for Workspace
  -> validate provider capability and adapter registration
  -> resolve endpoint and credential reference from SYSTEM provider integration
  -> resolve credential reference server-side
  -> DataEgressPolicy
  -> provider adapter
```

The policy checks are canonical application guards used by every execution
entry point, including normal conversations, System Assistant conversations,
knowledge processing, reprocessing, and any future evaluation execution.
Delivery-layer display logic is not an enforcement boundary.

Capability-disabled, provider-disabled, and model-disabled outcomes are bounded
policy denials. They occur before endpoint/credential resolution and guarantee
zero remote Generation and Embedding calls. Workspace suspension and
`ai_execution_enabled=false` remain earlier hard gates. Data egress remains a
later independent hard gate and is not replaced by provider/model policy.

## Fallback safety

Fallback describes configuration provenance in `INHERIT` mode, not permission
bypass. Each fallback candidate is evaluated locally and deterministically as
if it had been selected directly:

1. resolve the complete candidate atomically;
2. verify the referenced SYSTEM integration exists and supports the capability;
3. verify the provider is enabled for the target Workspace;
4. verify the canonical model is enabled under the Workspace's model-policy
   mode;
5. validate model and dimensions invariants;
6. resolve endpoint and credential reference from the single authoritative
   SYSTEM provider integration; and
7. only then resolve the credential value and continue toward egress.

If any step fails, execution stops. The resolver never searches for another
provider or model and never merges environment fields into a persisted
candidate.

Runtime policy evaluation never calls OpenRouter, Anthropic, OpenAI, Gemini, or
another provider's catalogue endpoint. Live catalogues are used only by
administration, model selection, policy configuration, and explicit
refresh/validation workflows. Catalogue refreshes do not mutate active policy
or selection implicitly.

## Atomic policy and selection mutations

A provider/model policy mutation must leave a complete valid capability state.
It cannot commit an accidental intermediate state that invalidates the current
effective Workspace configuration. Only these outcomes are valid:

1. **Atomic replacement:** disable the old provider/model as required and move
   the capability to a different allowed, structurally valid `SELECTED`
   provider/model in the same protected mutation.
2. **Explicit capability shutdown:** move the capability to `DISABLED`, then
   disable the provider/model in the same protected mutation.
3. **Rejection:** when neither complete outcome is supplied, reject the entire
   mutation without changing policy or selection.

For `INHERIT`, a policy mutation that would deny the inherited System-default
or environment-bootstrap candidate must atomically move the capability either
to `SELECTED` with a valid allowed replacement or to `DISABLED`. It cannot
silently search for another candidate.

Protected mutation functions and their application transactions serialize
provider policy, model policy, runtime mode, and selection changes. They
validate the complete prospective state before commit and roll back all parts
on failure. A provider mutation that affects both capabilities validates both
complete capability states in the same transaction. Embedding changes
additionally compare the current and prospective Workspace-scoped semantic
signature and enforce embedding compatibility before commit.

## Migration and existing Workspaces

Migration must preserve service continuity without treating historical
descriptive values as informed runtime-denial choices.

The transition is:

1. migrate current SYSTEM-global persisted Generation and Embedding
   configurations into System-default semantics without changing their
   selected provider, model, dimensions, or active state;
2. establish each provider integration as the single authoritative source for
   its capability-specific endpoint and credential reference; preserve current
   revision endpoint/credential values only as legacy historical snapshots,
   never as a second execution authority;
3. retain environment configuration solely as bootstrap when an active System
   default is absent;
4. initialize every existing Workspace with Generation mode `INHERIT` and
   Embedding mode `INHERIT`, unless concrete migration evidence requires an
   explicit `DISABLED` state;
5. initialize model policy as `INHERIT_SUPPORTED` using the platform's local
   supported-model integration policy;
6. ensure the provider used by each effective System-default or environment
   candidate is enabled for every existing Workspace before enforcement is
   activated; historical false values for such currently required providers
   are reset to enabled because they were previously descriptive and cannot be
   treated as consent to an outage;
7. record that compatibility normalization through the existing audit
   architecture; and
8. activate enforcement only after the resulting effective configuration for
   every existing Workspace can be resolved and validated.

Other existing provider rows may retain their enabled value because they do not
affect continuity until selected or inherited. After enforcement,
`workspace_provider_settings.enabled` is authoritative.

New provider integrations are not automatically enabled for existing or future
Workspaces merely by entering the global provider catalogue. A newly created
Workspace in `INHERIT` mode receives an enabled provider row only where the
current System-default continuity rule requires that provider for a complete
inherited capability; other integrations remain disabled. New Workspace
initialization must produce either a complete valid `INHERIT`/`SELECTED` state
or an explicit `DISABLED` state, never an ambiguous partial configuration.

The existing provider seed trigger/path must be updated accordingly; it must
not keep assigning unconditional `enabled=true` to every future provider and
Workspace combination.

## Workspace-aware embedding compatibility

Embedding compatibility is evaluated at the same Workspace scope as persisted
indexed embeddings. The compatibility query answers whether the target
Workspace has stored embedding vectors; it does not use a platform-global
existence result.

The embedding semantic signature remains:

- provider;
- canonical model ID;
- effective integration endpoint; and
- dimensions.

Credential reference and configuration provenance are not semantic differences.

Before a Workspace Embedding selection, System default, provider policy, or
model policy change becomes effective, the application compares the current
and prospective effective signatures for each affected Workspace. A changed
signature is rejected when that Workspace has indexed embeddings unless an
approved reindex/migration workflow exists. Unaffected Workspaces do not block
one another.

Disabling a provider or model does not trigger substitution. It denies future
execution, so it cannot silently switch indexed Knowledge to another embedding
space. A System-default embedding change must be checked independently for all
Workspaces that inherit it; one Workspace with incompatible indexed embeddings
causes the default mutation to fail atomically.

## Credential and security boundary

Workspace runtime selections reference a SYSTEM provider integration. The
integration owns the endpoint and credential reference name. Runtime secret
resolution remains:

```text
effective Workspace configuration
  -> credential reference name
  -> server-side credential resolver
  -> secret available only inside adapter construction/execution
```

Raw secrets, authorization headers, and resolved credential values never cross
the database runtime-configuration boundary or FastAPI/browser responses.
Workspace policy APIs expose canonical provider/model identifiers and enforced
state only.

All policy and selection mutations require canonical SYSTEM authority, use
backend-authoritative validation, and are audited. Runtime roles receive only
the minimum read/execute privileges needed by protected functions. Workspace
membership does not grant direct table access or policy-management authority.

## Product UX responsibilities

The Providers & Models product presents only controls with enforced meaning:

- SYSTEM-supported provider integrations and capabilities;
- System default Generation and Embedding configurations;
- selected Workspace provider policy;
- selected Workspace model allow-list policy; and
- selected/effective Workspace Generation and Embedding configurations with
  provenance.

The UI must clearly distinguish provider catalogue, Workspace model policy,
Workspace runtime selection, and the resulting effective configuration. Saving
a policy must change the next eligible execution immediately, without restart
or relogin.

Every control presented as enabled/disabled, selected, runtime state, endpoint
state, or credential-reference state must map to a canonical server-side
execution decision. Displayed endpoint and credential-reference state comes
from the authoritative SYSTEM provider integration and is not independently
editable as Workspace metadata.

`administrative_status`, `base_url_override`, assistant-level descriptive model
references, or other metadata must not be shown as operational controls unless
and until a canonical server-side execution path consumes them. Provider
catalogue availability or structural readiness must not be labelled as live
provider health.

## Consequences

- The canonical resolver becomes Workspace-aware and requires a Workspace ID
  for execution.
- Generation and Embedding may use different providers within one Workspace.
- Two Workspaces may select different provider/model combinations while still
  sharing SYSTEM-owned integrations and secret-resolution infrastructure.
- Provider and model denials are immediate, fail closed, and precede all remote
  activity.
- Environment bootstrap remains possible but is always subordinate to
  Workspace policy.
- Existing SYSTEM-global runtime records remain valuable as defaults rather
  than being discarded.
- The current global embedding-existence guard must be replaced by a
  Workspace-scoped guard before Workspace-specific embedding selection can be
  activated.
- Usage remains provider-authoritative observability and gains no invented
  Workspace or model attribution from this decision.

## Explicit non-goals

This decision does not introduce:

- raw credential persistence or a System Credential Vault;
- per-assistant runtime model routing;
- multiple simultaneous Generation selections within one Workspace;
- provider/model fallback chains or automatic substitution;
- load balancing;
- local models, LangChain, or LlamaIndex;
- embedding reindex implementation;
- invented provider billing attribution; or
- delegation of provider/model policy management to ordinary Workspace roles.

## Implementation implications

Implementation requires a forward migration and a coordinated application
change. Schema enforcement, resolver changes, provider/model policy guards,
Workspace-scoped embedding compatibility, APIs, and UX must ship as one
fail-closed contract. A descriptive UI must not precede executable enforcement.

The current Anthropic catalogue, structured-generation transport, and
provider-keyed factory are reusable SYSTEM integration infrastructure. The
unapplied Anthropic provider migration must be reviewed against the new
provider-seeding rules before application; this decision does not approve or
apply it.

No current provider/model value is changed by this decision document itself.
