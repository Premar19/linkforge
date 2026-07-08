export interface LinkStat {
  code: string
  target_url: string
  is_active: boolean
  clicks: number
}

export interface AuthResponse {
  access_token: string
  token_type: string
}
