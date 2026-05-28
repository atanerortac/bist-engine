import { createClient } from 'jsr:@supabase/supabase-js@2'

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Headers': 'authorization, content-type',
}

Deno.serve(async (req: Request) => {
  if (req.method === 'OPTIONS') {
    return new Response(null, { headers: CORS_HEADERS })
  }

  const authHeader = req.headers.get('Authorization')
  if (!authHeader) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401, headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
    })
  }

  // Validate the Supabase JWT — rejects expired or forged tokens
  const supabase = createClient(
    Deno.env.get('SUPABASE_URL') ?? '',
    Deno.env.get('SUPABASE_ANON_KEY') ?? '',
    { global: { headers: { Authorization: authHeader } } },
  )

  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) {
    return new Response(JSON.stringify({ error: 'Unauthorized' }), {
      status: 401, headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
    })
  }

  const owner = Deno.env.get('GITHUB_OWNER') ?? ''
  const repo  = Deno.env.get('GITHUB_REPO')  ?? 'bist-engine'
  const pat   = Deno.env.get('GITHUB_PAT')   ?? ''

  if (!owner || !pat) {
    return new Response(JSON.stringify({ error: 'Server misconfiguration: GITHUB_OWNER or GITHUB_PAT missing' }), {
      status: 500, headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
    })
  }

  const ghRes = await fetch(
    `https://api.github.com/repos/${owner}/${repo}/actions/workflows/daily_pipeline.yml/dispatches`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${pat}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ ref: 'main' }),
    },
  )

  if (ghRes.status === 204) {
    return new Response(JSON.stringify({ ok: true, message: 'Pipeline started' }), {
      status: 200, headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
    })
  }

  const errorText = await ghRes.text()
  return new Response(JSON.stringify({ ok: false, error: errorText }), {
    status: ghRes.status, headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
  })
})
