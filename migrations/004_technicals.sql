-- Technicals: latest technical-indicator snapshot per ticker.
-- One row per ticker (most recent trading day). Powers the analyze modal
-- and portfolio "current day analysis" view in the frontend.

create table if not exists technicals (
  ticker        text not null,
  date          date not null,
  close         numeric(12,4),
  -- trend
  ema_20        numeric(12,4),
  ema_50        numeric(12,4),
  ema_200       numeric(12,4),
  -- momentum / oscillators
  rsi_14        numeric(6,2),
  macd          numeric(12,4),
  macd_signal   numeric(12,4),
  macd_hist     numeric(12,4),
  stoch_k       numeric(6,2),
  stoch_d       numeric(6,2),
  mfi_14        numeric(6,2),
  adx_14        numeric(6,2),
  plus_di       numeric(6,2),
  minus_di      numeric(6,2),
  -- volatility
  atr_14        numeric(12,4),
  bb_ust        numeric(12,4),
  bb_orta       numeric(12,4),
  bb_alt        numeric(12,4),
  hv_20         numeric(8,2),
  hv_20_pct     numeric(6,2),
  -- volume
  hacim_tl      numeric(18,2),
  hacim_ort_20  numeric(18,2),
  -- relative strength / position
  rs_63         numeric(8,2),
  dist_52w_pct  numeric(8,2),
  created_at    timestamptz default now(),
  primary key (ticker)
);

create index if not exists idx_technicals_date on technicals (date desc);

alter table technicals enable row level security;

create policy "anon_read_technicals" on technicals for select to anon          using (true);
create policy "auth_read_technicals" on technicals for select to authenticated using (true);
