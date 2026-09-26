type ServerEntry = {
  fetch: (request: Request, env: unknown, ctx: unknown) => Promise<Response> | Response;
};

export default {
  async fetch(request: Request, env: unknown, ctx: unknown) {
    const module = await import("@tanstack/react-start/server-entry");
    const entry = (module.default ?? module) as ServerEntry;
    return entry.fetch(request, env, ctx);
  },
};
