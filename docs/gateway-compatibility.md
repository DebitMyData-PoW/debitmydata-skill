# Gateway compatibility

Compared again with Gateway 0.52.3 on 16 November 2026 (staging and production both run it):

- Since Gateway 0.31.0 the quote's and the credential's `service` is
  `DebitMyData Agentic DID-LLM Registration` (a DID is now called a DID-LLM). The helpers
  accept it and the earlier `DebitMyData Agentic DID Registration`, which credentials issued
  before 0.31.0 keep. Without this, the CLI stopped right after the quote with "Quote is
  outside the staging registration contract." and paid nothing.
- Nothing else the CLI sends or checks has changed: discovery and payment options, quote,
  test payment, payment status, controller challenge and proof, issuance result, DID
  document and credential.
- New on the Gateway since v0.11.0, outside this skill's v1: the MCP server with OAuth
  sign-in (`debitmydata_whoami`, `debitmydata_verify_agent`), card, PayPal and x402
  payments, the public DID-LLM directory, owner changes and revocation
  (`debitmydata_change_owner`, `debitmydata_revoke_did`), add-ons, and the Gateway's own
  Agent Skill, `debitmydata-did-llm`, listed at `/.well-known/agent-skills/index.json`.
- Since Gateway 0.51.0 a person can pay with PayPal (payment option `paypal`), on PayPal's
  own page like the card option. The CLI ignores the payment options it does not use: it
  only checks that `dmd_pow_native` on `dmd:regtest` is listed and enabled, so the new
  option changes nothing for it.
- Since Gateway 0.50.0 every MCP tool's name starts with `debitmydata_`; the earlier `dmd_`
  names still work when called but are no longer listed. This skill's CLI uses the REST API
  only, so it is not affected. The `dmd_` prefixes of IDs (`dmd_identity_...`,
  `dmd_did_intent_...`) and payment option IDs such as `dmd_pow_native` are unchanged.
