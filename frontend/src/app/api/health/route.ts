import { NextResponse } from 'next/server'

export async function GET() {
  try {
    const res = await fetch('http://localhost:5001/', { 
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
