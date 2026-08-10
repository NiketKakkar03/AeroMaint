import { CaptureClient, CaptureSdkError } from "@aeromaint/capture-sdk";

if (
  typeof CaptureClient !== "function" ||
  typeof CaptureSdkError !== "function"
) {
  throw new Error("Packed SDK exports are incomplete");
}
const client = new CaptureClient({
  baseUrl: "https://example.invalid",
  fetch: async () => new Response("[]")
});
const page = await client.listSessions();
if (page.items.length !== 0)
  throw new Error("Packed SDK client returned unexpected sessions");
process.stdout.write("packed SDK smoke test passed\n");
