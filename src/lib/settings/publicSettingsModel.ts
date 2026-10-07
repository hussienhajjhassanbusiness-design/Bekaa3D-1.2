// #ARCHITECTURE-PUBLIC-SETTINGS-ADAPTER
//
// A frontend-normalized shape only — never a claim about
// `GET /api/v1/settings/public`'s real response field names or shape.
// That response's exact schema is unconfirmed
// (FVS-022-IMPLEMENTATION-PLAN.md §1): FVS-007's admin settings list is
// described as a generic typed-setting list ("a control per setting's
// declared type"), which may mean the public endpoint returns a
// similarly-shaped list of `{key, value}` entries rather than a flat
// object — guessing that shape here would mean inventing a backend
// contract. This module intentionally holds ONLY the one field this
// slice actually needs, with no backend setting-key name encoded
// anywhere, and deliberately does NOT yet add a free-shipping-threshold
// field ahead of FVS-025/026 landing their own confirmed contract.
export interface PublicSettingsModel {
  whatsappNumber: string | null;
}
