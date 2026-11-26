// P1-4 (docs/backend-handoff/BACKEND-RESPONSE.md, schema `AdminUserDetail`)
// — used for both list items and the detail read. Nothing else exists in
// V1: no order history, address, or notes.
export interface AdminUserDetail {
  id: string;
  email: string;
  role: "customer" | "admin";
  is_active: boolean;
  email_verified_at: string | null;
  created_at: string;
}

export interface AdminUserPage {
  items: AdminUserDetail[];
  next_cursor: string | null;
}

export interface AdminUsersQueryParams {
  cursor?: string;
  limit?: number;
  verified?: boolean;
  active?: boolean;
  search?: string;
}
