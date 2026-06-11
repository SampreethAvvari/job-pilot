import { addCompany, readCompanies, removeCompany } from "@/lib/companies";

export async function GET() {
  try {
    return Response.json({ companies: await readCompanies() });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const body = (await request.json()) as {
      remove?: boolean;
      row?: number;
      company?: string;
      careersUrl?: string;
    };
    if (body.remove) {
      const row = Number(body.row);
      if (!row || row < 2) {
        return Response.json({ error: "row required" }, { status: 400 });
      }
      await removeCompany(row);
      return Response.json({ ok: true });
    }
    const company = String(body.company ?? "").trim();
    const careersUrl = String(body.careersUrl ?? "").trim();
    if (!company) {
      return Response.json({ error: "company required" }, { status: 400 });
    }
    await addCompany(company, careersUrl);
    return Response.json({ ok: true });
  } catch (e) {
    return Response.json({ error: String(e) }, { status: 500 });
  }
}
