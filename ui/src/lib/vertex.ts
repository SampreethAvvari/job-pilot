import { GoogleAuth } from "google-auth-library";

import { PROJECT, REGION } from "./google";

const auth = new GoogleAuth({
  scopes: ["https://www.googleapis.com/auth/cloud-platform"],
});

// Model ids env-overridable so a rename never needs a redeploy.
// (3.x Gemini isn't enabled for this project; 2.5-pro is the available Pro tier.)
export const FLASH = process.env.ASSISTANT_MODEL_FLASH ?? "gemini-2.5-flash";
export const PRO = process.env.ASSISTANT_MODEL_PRO ?? "gemini-2.5-pro";

export type ChatMessage = { role: "user" | "model"; text: string };

export async function generate(
  model: string,
  system: string,
  messages: ChatMessage[],
  { search = true, maxTokens = 4096 }: { search?: boolean; maxTokens?: number } = {},
): Promise<string> {
  const client = await auth.getClient();
  const url =
    `https://${REGION}-aiplatform.googleapis.com/v1/projects/${PROJECT}` +
    `/locations/${REGION}/publishers/google/models/${model}:generateContent`;
  const res = await client.request<{
    candidates?: { content?: { parts?: { text?: string }[] } }[];
  }>({
    url,
    method: "POST",
    data: {
      systemInstruction: { parts: [{ text: system }] },
      contents: messages.map((m) => ({ role: m.role, parts: [{ text: m.text }] })),
      ...(search ? { tools: [{ googleSearch: {} }] } : {}),
      generationConfig: { temperature: 0.6, maxOutputTokens: maxTokens },
    },
  });
  const parts = res.data.candidates?.[0]?.content?.parts ?? [];
  return parts.map((p) => p.text ?? "").join("").trim();
}
