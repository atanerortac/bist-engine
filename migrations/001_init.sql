-- BIST Ajan — Supabase Schema
-- RLS: anon = SELECT only, service_role = full access

-- Signals: daily buy signals from strategy engine
create table if not exists signals (
  id           bigserial primary key,
  date         date not null,
  ticker       text not null,
  close        numeric(12,4),
  strategy     text,
  signal       text,
  stop_loss    numeric(12,4),
  target_price numeric(12,4),
  potential_return numeric(8,4),
  score        integer,
  vade         text,
  tier         text,
  created_at   timestamptz default now(),
  unique (date, ticker, strategy)
);

-- Positions: open algorithmic simulation positions
create table if not exists positions (
  id            bigserial primary key,
  ticker        text not null unique,
  entry_date    date,
  entry_price   numeric(12,4),
  current_stop  numeric(12,4),
  target_price  numeric(12,4),
  vade          text,
  tier          text,
  updated_at    timestamptz default now()
);

-- Trades: closed algorithmic simulation trades
create table if not exists trades (
  id            bigserial primary key,
  ticker        text not null,
  entry_date    date,
  exit_date     date,
  entry_price   numeric(12,4),
  exit_price    numeric(12,4),
  pnl_pct       numeric(8,4),
  close_reason  text,
  vade          text,
  tier          text,
  created_at    timestamptz default now(),
  unique (ticker, entry_date)
);

-- Market breadth: daily Green/Yellow/Red state
create table if not exists market_breadth (
  id          bigserial primary key,
  date        date not null unique,
  breadth_pct numeric(5,1),
  durum       text,
  created_at  timestamptz default now()
);

-- Tavan Takip: ≥9.5% circuit-breaker moves, possible continuation day
create table if not exists tavan_takip (
  id          bigserial primary key,
  date        date not null,
  ticker      text not null,
  move_pct    numeric(6,2),
  volume_tl   numeric(16,2),
  vol_ratio   numeric(6,2),
  created_at  timestamptz default now(),
  unique (date, ticker)
);

-- Indexes for common query patterns
create index if not exists idx_signals_date    on signals (date desc);
create index if not exists idx_signals_ticker  on signals (ticker);
create index if not exists idx_trades_exit     on trades (exit_date desc);
create index if not exists idx_breadth_date    on market_breadth (date desc);
create index if not exists idx_tavan_date      on tavan_takip (date desc);

-- RLS policies
alter table signals        enable row level security;
alter table positions      enable row level security;
alter table trades         enable row level security;
alter table market_breadth enable row level security;
alter table tavan_takip    enable row level security;

-- anon can read everything
create policy "anon_read_signals"        on signals        for select to anon using (true);
create policy "anon_read_positions"      on positions      for select to anon using (true);
create policy "anon_read_trades"         on trades         for select to anon using (true);
create policy "anon_read_market_breadth" on market_breadth for select to anon using (true);
create policy "anon_read_tavan_takip"    on tavan_takip    for select to anon using (true);

-- service_role has full access (default Supabase behaviour, no explicit policy needed)
