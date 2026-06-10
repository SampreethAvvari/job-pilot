import { google } from "googleapis";

export const SPREADSHEET_ID = process.env.SPREADSHEET_ID ?? "";
export const PROJECT = process.env.GOOGLE_CLOUD_PROJECT ?? "";
export const REGION = process.env.GOOGLE_CLOUD_LOCATION ?? "us-central1";

export function oauthClient() {
  const raw = JSON.parse(process.env.GOOGLE_OAUTH_CLIENT_JSON ?? "{}");
  const c = raw.installed ?? raw.web ?? raw;
  const client = new google.auth.OAuth2(c.client_id, c.client_secret);
  client.setCredentials({ refresh_token: process.env.GOOGLE_OAUTH_REFRESH_TOKEN });
  return client;
}

export function sheetsClient() {
  return google.sheets({ version: "v4", auth: oauthClient() });
}
