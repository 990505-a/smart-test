import { NextRequest, NextResponse } from "next/server";

const PYTHON_API = process.env.PYTHON_API_URL || "http://localhost:5012";

export async function POST(request: NextRequest) {
  try {
    const { data, filename, mimeType, spaceId, agentName, threadId } = await request.json();

    if (!data || typeof data !== "string") {
      return NextResponse.json({ error: "Missing base64 data" }, { status: 400 });
    }

    const resp = await fetch(`${PYTHON_API}/api/v2/upload-to-workspace`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        data,
        filename: filename || "document.pdf",
        mime_type: mimeType || "application/pdf",
        space_id: spaceId || "default",
        agent_name: agentName || "testcase",
        thread_id: threadId || "",
      }),
    });

    if (resp.ok) {
      const result = await resp.json();
      return NextResponse.json(result);
    }

    const errorText = await resp.text();
    return NextResponse.json(
      { error: `Backend upload failed: ${errorText}` },
      { status: resp.status },
    );
  } catch (error) {
    console.error("[upload-to-workspace] Error:", error);
    return NextResponse.json(
      { error: `Upload error: ${String(error)}` },
      { status: 500 },
    );
  }
}
