export type AuthUser = {
  id: number;
  name: string;
  email: string;
  role: string;
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};
