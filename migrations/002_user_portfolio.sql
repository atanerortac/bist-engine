-- BIST Ajan — User Portfolio Schema
-- RLS: each user sees only their own rows; prices table is public read

-- User positions: one row per buy lot (no auto-merge of same ticker)
create table if not exists user_positions (
  id               uuid primary key default gen_random_uuid(),
  user_id          uuid not null references auth.users(id) on delete cascade,
  ticker           text not null,
  initial_shares   numeric(12,2) not null,
  remaining_shares numeric(12,2) not null,
  avg_cost         numeric(12,4) not null,
  entry_date       date not null,
  target_price     numeric(12,4),
  stop_loss        numeric(12,4),
  notes            text,
  realized_pnl_try numeric(14,4) not null default 0,
  status           text not null default 'active' check (status in ('active', 'closed')),
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

-- User trades: immutable audit log — no UPDATE/DELETE
create table if not exists user_trades (
  id          uuid primary key default gen_random_uuid(),
  user_id     uuid not null references auth.users(id) on delete cascade,
  position_id uuid not null references user_positions(id) on delete cascade,
  ticker      text not null,
  action      text not null check (action in ('buy', 'sell', 'partial_sell')),
  shares      numeric(12,2) not null,
  price       numeric(12,4) not null,
  trade_date  date not null,
  notes       text,
  created_at  timestamptz not null default now()
);

-- Prices: public market data written by service_role via sync
create table if not exists prices (
  ticker  text not null,
  date    date not null,
  close   numeric(12,4) not null,
  primary key (ticker, date)
);

-- Auto-update updated_at on user_positions
create or replace function update_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger user_positions_updated_at
  before update on user_positions
  for each row execute function update_updated_at();

-- Indexes
create index if not exists idx_user_positions_user_status on user_positions (user_id, status);
create index if not exists idx_user_positions_user_ticker on user_positions (user_id, ticker);
create index if not exists idx_user_trades_position       on user_trades (position_id);
create index if not exists idx_user_trades_user           on user_trades (user_id);
create index if not exists idx_prices_ticker_date         on prices (ticker, date desc);

-- RLS
alter table user_positions enable row level security;
alter table user_trades     enable row level security;
alter table prices          enable row level security;

-- user_positions: owner full access
create policy "user_positions_select" on user_positions for select using (auth.uid() = user_id);
create policy "user_positions_insert" on user_positions for insert with check (auth.uid() = user_id);
create policy "user_positions_update" on user_positions for update using (auth.uid() = user_id);
create policy "user_positions_delete" on user_positions for delete using (auth.uid() = user_id);

-- user_trades: owner read + insert only (no update/delete — audit log)
create policy "user_trades_select" on user_trades for select using (auth.uid() = user_id);
create policy "user_trades_insert" on user_trades for insert with check (auth.uid() = user_id);

-- prices: anyone can read, only service_role writes (no policy needed for service_role)
create policy "prices_anon_read" on prices for select to anon using (true);
create policy "prices_auth_read" on prices for select to authenticated using (true);
