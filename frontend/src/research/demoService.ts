import type { ActionView, DemoSnapshotView } from "./types";

export const DEMO_SEED = 20260717;

const FEE_KEYS = [
  "seller_fee",
  "processor_fee",
  "inbound_shipping",
  "outbound_shipping",
  "authentication",
  "slippage",
] as const;

const NO_OP: ActionView = {
  category: "NO_OP",
  allocation: 0,
  bid_offset_ticks: 0,
  ask_offset_ticks: 0,
};

const BID_QUOTE: ActionView = {
  category: "QUOTE",
  allocation: 0.4,
  bid_offset_ticks: -1,
  ask_offset_ticks: 0,
};

const ASK_QUOTE: ActionView = {
  category: "QUOTE",
  allocation: 0.35,
  bid_offset_ticks: 0,
  ask_offset_ticks: 2,
};

function zeroFees(): Record<string, string> {
  return Object.fromEntries(FEE_KEYS.map((key) => [key, "0"]));
}

function fees(overrides: Partial<Record<(typeof FEE_KEYS)[number], string>>) {
  return { ...zeroFees(), ...overrides };
}

interface DemoEventFixture {
  simulation_second: number;
  beat: string;
  deterministic_action: ActionView;
  pfhedge_score: number;
  iql_shadow_action: ActionView;
  final_action: ActionView;
  inventory_state: string;
  fees: Record<string, string>;
  cash: string;
  nav: string;
  realized_pnl: string;
  unrealized_pnl: string;
}

const DEMO_EVENTS: DemoEventFixture[] = [
  {
    simulation_second: 0,
    beat: "healthy_spread",
    deterministic_action: NO_OP,
    pfhedge_score: 0.18,
    iql_shadow_action: NO_OP,
    final_action: NO_OP,
    inventory_state: "flat",
    fees: zeroFees(),
    cash: "2500.00",
    nav: "2500.00",
    realized_pnl: "0",
    unrealized_pnl: "0",
  },
  {
    simulation_second: 60,
    beat: "deterministic_bid",
    deterministic_action: BID_QUOTE,
    pfhedge_score: 0.71,
    iql_shadow_action: {
      category: "QUOTE",
      allocation: 0.5,
      bid_offset_ticks: -2,
      ask_offset_ticks: 0,
    },
    final_action: BID_QUOTE,
    inventory_state: "bid_open",
    fees: zeroFees(),
    cash: "2500.00",
    nav: "2500.00",
    realized_pnl: "0",
    unrealized_pnl: "0",
  },
  {
    simulation_second: 120,
    beat: "paper_buy_fill",
    deterministic_action: NO_OP,
    pfhedge_score: 0.42,
    iql_shadow_action: NO_OP,
    final_action: NO_OP,
    inventory_state: "pending_logistics",
    fees: zeroFees(),
    cash: "2312.00",
    nav: "2498.00",
    realized_pnl: "0",
    unrealized_pnl: "-2.00",
  },
  {
    simulation_second: 180,
    beat: "shipping_authenticated",
    deterministic_action: NO_OP,
    pfhedge_score: 0.55,
    iql_shadow_action: NO_OP,
    final_action: NO_OP,
    inventory_state: "authenticated",
    fees: zeroFees(),
    cash: "2312.00",
    nav: "2502.00",
    realized_pnl: "0",
    unrealized_pnl: "2.00",
  },
  {
    simulation_second: 240,
    beat: "inventory_ask_sale",
    deterministic_action: ASK_QUOTE,
    pfhedge_score: 0.63,
    iql_shadow_action: {
      category: "QUOTE",
      allocation: 0.45,
      bid_offset_ticks: 0,
      ask_offset_ticks: 3,
    },
    final_action: ASK_QUOTE,
    inventory_state: "sold",
    fees: fees({
      seller_fee: "15.00",
      processor_fee: "4.50",
      inbound_shipping: "8.00",
      outbound_shipping: "2.00",
    }),
    cash: "2524.50",
    nav: "2524.50",
    realized_pnl: "24.50",
    unrealized_pnl: "0",
  },
  {
    simulation_second: 300,
    beat: "risk_gate_rejection",
    deterministic_action: BID_QUOTE,
    pfhedge_score: 0.84,
    iql_shadow_action: {
      category: "QUOTE",
      allocation: 0.6,
      bid_offset_ticks: -2,
      ask_offset_ticks: 1,
    },
    final_action: NO_OP,
    inventory_state: "flat",
    fees: zeroFees(),
    cash: "2524.50",
    nav: "2524.50",
    realized_pnl: "24.50",
    unrealized_pnl: "0",
  },
];

export class DemoService {
  private index = 0;
  private paused = true;

  snapshot(): DemoSnapshotView {
    const event = DEMO_EVENTS[this.index];
    return {
      index: this.index,
      simulation_second: event.simulation_second,
      paused: this.paused,
      beat: event.beat,
      deterministic_action: event.deterministic_action,
      pfhedge_score: event.pfhedge_score,
      iql_shadow_action: event.iql_shadow_action,
      final_action: event.final_action,
      inventory_state: event.inventory_state,
      fees: event.fees,
      cash: event.cash,
      nav: event.nav,
      realized_pnl: event.realized_pnl,
      unrealized_pnl: event.unrealized_pnl,
    };
  }

  pause(): DemoSnapshotView {
    this.paused = true;
    return this.snapshot();
  }

  resume(): DemoSnapshotView {
    this.paused = false;
    return this.snapshot();
  }

  restart(): DemoSnapshotView {
    this.index = 0;
    this.paused = true;
    return this.snapshot();
  }

  step(): DemoSnapshotView {
    if (this.index < DEMO_EVENTS.length - 1) {
      this.index += 1;
    }
    return this.snapshot();
  }
}

export function createDemoService(): DemoService {
  return new DemoService();
}
