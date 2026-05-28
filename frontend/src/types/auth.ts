export interface UserInfo {
  id: number;
  username: string;
  role: 'admin' | 'user';
}

export interface LoginRequest {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserInfo;
}

export interface RefreshResponse {
  access_token: string;
  token_type: string;
}

export interface UserResponse {
  id: number;
  username: string;
  role: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface UserListResponse {
  items: UserResponse[];
  total: number;
  page: number;
  limit: number;
}

export interface UserCreateRequest {
  username: string;
  password: string;
  role: string;
}

export interface UserUpdateRequest {
  username?: string;
  password?: string;
  role?: string;
  is_active?: boolean;
}
