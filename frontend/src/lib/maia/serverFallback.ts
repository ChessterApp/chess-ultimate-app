/**
 * Server-side Maia fallback client.
 *
 * When the local ONNX model hasn't finished downloading yet, the /play page
 * still needs a move. This asks the Flask backend (`POST /api/maia/move`),
 * which runs the SAME fp32 model, and returns the identical `{ policy, value }`
 * shape that `Maia.evaluateMaia3()` produces — so the page's own temperature
 * sampling behaves the same whether the move came from the browser or the
 * server. Once local Maia is ready the caller hot-swaps back automatically.
 */

export interface MaiaEvaluation {
  policy: Record<string, number>
  value: number
}

export async function fetchMaiaMoveFromServer(
  fen: string,
  eloSelf: number,
  eloOppo: number,
): Promise<MaiaEvaluation> {
  const res = await fetch('/api/maia/move', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ fen, elo_self: eloSelf, elo_oppo: eloOppo }),
  })

  if (!res.ok) {
    throw new Error(`Maia server fallback failed: ${res.status}`)
  }

  const data = await res.json()
  if (!data || !data.policy) {
    throw new Error('Maia server fallback returned no policy')
  }

  return { policy: data.policy, value: data.value }
}
