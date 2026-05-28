-- Allow authenticated users to read all public tables.
-- Required because 001_init.sql only granted SELECT to anon role.
-- After forcing auth (all users must log in), queries run as authenticated role.

create policy "auth_read_signals"        on signals        for select to authenticated using (true);
create policy "auth_read_positions"      on positions      for select to authenticated using (true);
create policy "auth_read_trades"         on trades         for select to authenticated using (true);
create policy "auth_read_market_breadth" on market_breadth for select to authenticated using (true);
create policy "auth_read_tavan_takip"    on tavan_takip    for select to authenticated using (true);
