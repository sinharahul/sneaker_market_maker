export type PaperStatus = {
  run_id: string | null;
  strategy_enabled: boolean;
  strategy_mode: string;
  registry: {
    model_id: string | null;
    state: string | null;
  };
  inference_latency_budget_ms: number;
  pause_reason: string | null;
  fallback_reason: string | null;
  last_iql_action: {
    source: string;
    category: string;
    allocation: number;
    bid_offset_ticks: number;
    ask_offset_ticks: number;
  } | null;
  open_orders: number;
  fills: number;
  lots: number;
  capital: {
    initial: string;
    cash: string;
    reserved_buy_principal: string;
    available_cash: string;
  };
  pnl: {
    equity: string;
    pnl: string;
    inventory_landed_cost: string;
    cash: string;
  };
  replay: {
    status: string;
    speed: number;
    events_emitted: number;
    events_total: number;
    dataset_id: string | null;
    source_kind: string | null;
    simulation_time: string | null;
  };
};

export type PaperOrderView = {
  order_id: string;
  side: string;
  price: string;
  quantity: number;
  status: string;
  product_family: string;
  style_code: string;
};

export type PaperFillView = {
  fill_id: string;
  side: string;
  execution_price: string;
  total_fees: string;
  source_event_id: string;
};

export type PaperLotView = {
  lot_id: string;
  state: string;
  landed_cost: string;
  product_family: string;
  style_code: string;
};

export type OpsSnapshot = {
  status: PaperStatus;
  orders: PaperOrderView[];
  fills: PaperFillView[];
  lots: PaperLotView[];
};

async function postCommand(
  command: string,
  payload: Record<string, unknown> = {},
  fetcher: typeof fetch = fetch,
): Promise<void> {
  const response = await fetcher(`/api/paper/commands/${command}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": `${command}-${crypto.randomUUID()}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Paper command ${command} failed (${response.status})`);
  }
}

export async function loadOpsSnapshot(
  fetcher: typeof fetch = fetch,
): Promise<OpsSnapshot> {
  const [status, orders, fills, lots] = await Promise.all([
    fetcher("/api/paper/status").then(async (response) => {
      if (!response.ok) {
        throw new Error("Paper status unavailable");
      }
      return (await response.json()) as PaperStatus;
    }),
    fetcher("/api/paper/orders").then(async (response) => {
      if (!response.ok) {
        throw new Error("Paper orders unavailable");
      }
      return ((await response.json()) as { orders: PaperOrderView[] }).orders;
    }),
    fetcher("/api/paper/fills").then(async (response) => {
      if (!response.ok) {
        throw new Error("Paper fills unavailable");
      }
      return ((await response.json()) as { fills: PaperFillView[] }).fills;
    }),
    fetcher("/api/paper/lots").then(async (response) => {
      if (!response.ok) {
        throw new Error("Paper lots unavailable");
      }
      return ((await response.json()) as { lots: PaperLotView[] }).lots;
    }),
  ]);
  return { status, orders, fills, lots };
}

export const paperOpsCommands = {
  load: (fetcher?: typeof fetch) => postCommand("load", { seed: 0, speed: 1 }, fetcher),
  start: (fetcher?: typeof fetch) => postCommand("start", {}, fetcher),
  pause: (fetcher?: typeof fetch) => postCommand("pause", {}, fetcher),
  resume: (fetcher?: typeof fetch) => postCommand("resume", {}, fetcher),
  stop: (fetcher?: typeof fetch) => postCommand("stop", {}, fetcher),
  enable: (fetcher?: typeof fetch) => postCommand("enable", {}, fetcher),
  disable: (fetcher?: typeof fetch) => postCommand("disable", {}, fetcher),
  tick: (fetcher?: typeof fetch) => postCommand("tick", {}, fetcher),
  setMode: (mode: string, fetcher?: typeof fetch) =>
    postCommand("set-mode", { mode }, fetcher),
  setBudget: (limitMs: number, fetcher?: typeof fetch) =>
    postCommand("set-budget", { limit_ms: limitMs }, fetcher),
};
