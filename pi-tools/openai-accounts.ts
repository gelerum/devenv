import { lazyStream, type Model, type Provider, type TranscriptContext } from "@earendil-works/pi-ai";
import { builtinProviders } from "@earendil-works/pi-ai/providers/all";
import { getAgentDir, type ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const FAMILIES = [
  { id: "openai", label: "OpenAI", endpoint: "https://api.openai.com/v1", api: "openai-responses" },
  { id: "openai-codex", label: "Codex", endpoint: "https://chatgpt.com/backend-api", api: "openai-codex-responses" },
] as const;
type Family = typeof FAMILIES[number];

function checkSlotConfig(id: string) {
  let content: string;
  try {
    content = readFileSync(join(getAgentDir(), "models.json"), "utf8");
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return;
    throw new Error("Cannot verify models.json for OpenAI account slots");
  }
  let config: { providers?: Record<string, unknown> };
  try {
    // Match Pi's models.json syntax: BOM, line comments and trailing commas.
    config = JSON.parse(content.replace(/^\uFEFF/, "")
      .replace(/"(?:\\.|[^"\\])*"|\/\/[^\n]*/g, match => match.startsWith('"') ? match : "")
      .replace(/"(?:\\.|[^"\\])*"|,(\s*[}\]])/g, (match, tail) => tail ?? match));
  } catch {
    // Parsing errors can contain parts of the file, including unrelated keys.
    throw new Error("Cannot verify models.json for OpenAI account slots");
  }
  if (config?.providers && Object.hasOwn(config.providers, id)) {
    throw new Error(`Remove the ${id} entry from models.json before using this OpenAI account slot`);
  }
}

function isBuiltinModel(model: Model, family: Family): boolean {
  return model.baseUrl === family.endpoint && model.api === family.api;
}

function accountProvider(source: Provider, family: Family, id: string, name: string): Provider {
  const oauth = source.auth.oauth;
  if (!oauth) throw new Error(`The built-in ${family.id} OAuth is unavailable`);
  // models.json can change the API, bypassing the native stream wrapper.
  // Keep the slot blocked for this load if an override was already present,
  // and recheck before producing request auth in case one was added later.
  let configError: unknown;
  try { checkSlotConfig(id); } catch (error) { configError = error; }
  function verifyConfig() {
    if (configError) throw configError;
    checkSlotConfig(id);
  }
  const models = source.getModels().filter(model => isBuiltinModel(model, family));
  const byId = new Map(models.map(model => [model.id, model]));
  function wireModel<T extends Model>(model: T): T {
    const original = byId.get(model.id);
    if (!original || !isBuiltinModel(model, family)) {
      throw new Error(`Account slots only support built-in ${family.id} models`);
    }
    // The OpenAI Responses implementation recognizes ChatGPT login by provider ID.
    // Use the original, unconfigured model on the wire, not models.json overrides.
    return original as T;
  }
  function wireContext(context: TranscriptContext): TranscriptContext {
    // Keep normal replay within a slot, but let Pi treat conversation from
    // another slot as cross-provider (no replay of foreign reasoning state).
    return { ...context, messages: context.messages.map(message => {
      if (message.role !== "assistant") return message;
      if (message.provider === id) return { ...message, provider: family.id };
      if (message.provider === family.id) return { ...message, provider: id };
      return message;
    }) };
  }
  function streamWith<M extends Model, O extends { signal?: AbortSignal }>(
    start: (model: M, context: TranscriptContext, options: O) => ReturnType<Provider["stream"]>,
    model: M, context: TranscriptContext, options?: O,
  ) {
    async function* events() {
      // Discard custom headers (including Authorization) and custom transport.
      const stream = start(wireModel(model), wireContext(context), {
        ...options, headers: undefined, fetch: undefined,
        // Do not reuse Pi's Codex WebSocket (and server-side continuation)
        // from an earlier slot in the same conversation.
        ...(family.id === "openai-codex" ? { transport: "sse" } : {}),
      } as O);
      for await (const event of stream) {
        if (event.type === "done") yield { ...event, message: { ...event.message, provider: id } };
        else if (event.type === "error") yield { ...event, error: { ...event.error, provider: id } };
        else yield { ...event, partial: { ...event.partial, provider: id } };
      }
    }
    return lazyStream(model, async () => events(), undefined, options?.signal);
  }
  return {
    id,
    name,
    baseUrl: family.endpoint,
    // No OPENAI_API_KEY fallback for secondary accounts. Pin the URL at
    // auth resolution too, so a catalog overlay cannot redirect OAuth traffic.
    auth: { oauth: {
      ...oauth,
      async login(callbacks) {
        verifyConfig();
        return oauth.login(callbacks);
      },
      async refresh(credential, signal) {
        verifyConfig();
        return oauth.refresh(credential, signal);
      },
      async toAuth(credential) {
        verifyConfig();
        return { ...await oauth.toAuth(credential), baseUrl: family.endpoint };
      },
    } },
    getModels: () => models.map(model => ({ ...model, provider: id })),
    stream: (model, context, options) => streamWith(source.stream, model, context, options),
    streamSimple: (model, context, options) => streamWith(source.streamSimple, model, context, options),
  };
}

export default function (pi: ExtensionAPI) {
  const providers = builtinProviders();
  const accounts = FAMILIES.flatMap(family => {
    const source = providers.find(provider => provider.id === family.id);
    if (!source?.auth.oauth || source.baseUrl !== family.endpoint) return [];
    const stockIds = new Set(source.getModels().filter(model => isBuiltinModel(model, family)).map(model => model.id));
    const slots = Array.from({ length: 4 }, (_, index) => {
      const number = index + 1;
      const primary = family.id === "openai-codex" && number === 1;
      const id = primary ? family.id : `${family.id}-account-${number}`;
      const label = primary ? "Codex — основной вход" : `${family.label} — аккаунт ${number}`;
      // Leave native Codex and its existing auth.json entry completely untouched.
      if (!primary) pi.registerProvider(accountProvider(source, family, id, label));
      return { id, label, family, stockIds, primary };
    });
    return slots;
  });

  pi.registerCommand("account", {
    description: "Switch the OpenAI or Codex login used in this session",
    async handler(_args, ctx) {
      if (!ctx.hasUI) return;
      const idle = () => ctx.isIdle() && !ctx.hasPendingMessages();
      if (!idle()) {
        ctx.ui.notify("Дождитесь окончания запроса перед сменой аккаунта.", "warning");
        return;
      }
      const registry = ctx.modelRegistry;
      const hasLogin = (id: string) => {
        const model = registry.getModelsOfType("chat", id)[0];
        return model !== undefined && registry.isUsingOAuth(model);
      };
      const sorted = [...accounts].sort((a, b) =>
        Number(ctx.model?.provider === b.id) - Number(ctx.model?.provider === a.id));
      const choices = sorted.map(({ id, label }) => {
        const loggedIn = hasLogin(id);
        const status = loggedIn ? "" : " (добавить вход)";
        const active = ctx.model?.provider === id && loggedIn ? " ●" : "";
        return `${label}${status}${active}`;
      });
      const answer = await ctx.ui.select("ChatGPT: какой аккаунт использовать?", choices);
      if (answer === undefined || !idle()) return;
      const account = sorted[choices.indexOf(answer)];
      if (!account) return;
      const { id, label, family, stockIds, primary } = account;
      if (!hasLogin(id)) {
        ctx.ui.setEditorText(`/login ${id}`);
        ctx.ui.notify("Нажмите Enter для входа, затем снова вызовите /account.", "info");
        return;
      }
      // The native provider still accepts models the user already configured,
      // but account slots themselves never accept custom adapter/URL overrides.
      const available = registry.getModelsOfType("chat", id)
        .filter(model => (primary || stockIds.has(model.id)) && isBuiltinModel(model, family));
      let model = available.find(entry => entry.id === ctx.model?.id);
      if (!model && available.length) {
        const models = available.map(entry => entry.id);
        const choice = await ctx.ui.select(`Выберите модель ${family.label}`, models);
        if (choice === undefined) return;
        model = available.find(entry => entry.id === choice);
      }
      if (!idle()) return;
      if (!model || !hasLogin(id)) {
        ctx.ui.notify(`Нет доступной модели ${family.label} с этим входом.`, "warning");
        return;
      }
      try {
        if (await pi.setModel(model)) {
          ctx.ui.notify(`Активен ${label}`, "info");
        } else {
          ctx.ui.notify("Pi не смог использовать выбранный вход.", "warning");
        }
      } catch {
        ctx.ui.notify("Pi не смог использовать выбранный вход. Проверьте /login.", "warning");
      }
    },
  });
}
