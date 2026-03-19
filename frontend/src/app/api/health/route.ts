import { NextResponse } from 'next/server'

const BACKEND_URL = process.env.INTERNAL_BACKEND_URL || 'https://api.chesster.io'

export async function GET() {
  try {
    const res = await fetch(`${BACKEND_URL}/`, {
      signal: AbortSignal.timeout(3000)
    })
    if (res.ok) {
      return NextResponse.json({ status: 'ok' })
    }
    return NextResponse.json({ status: 'unhealthy' }, { status: 503 })
  } catch {
    return NextResponse.json({ status: 'unhealthy' }, { status: 503 })
  }
}
