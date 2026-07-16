'use client'

import { useRouter } from 'next/navigation'
import { useLocalStorage } from 'usehooks-ts'
import { BOARD_THEMES, PIECE_STYLE_TYPES, DEFAULT_BOARD_SHOW_COORDINATE, DEFAULT_BOARD_ANIMATION_DURATION } from '@/lib/setting/helper'
import { useDarkMode } from '@/hooks/useDarkMode'
import Image from 'next/image'

const BOARD_THEME_KEYS = Object.keys(BOARD_THEMES) as (keyof typeof BOARD_THEMES)[]
const PIECE_KEYS = Object.keys(PIECE_STYLE_TYPES) as (keyof typeof PIECE_STYLE_TYPES)[]

export default function SettingsPage() {
  const router = useRouter()

  // Board settings — same localStorage keys as AiChessboard/DebutBoard
  const [boardTheme, setBoardTheme] = useLocalStorage<string>('board_theme', 'chessbase')
  const [pieceType, setPieceType] = useLocalStorage<string>('board_piece_type', 'Fritz')
  const [showCoordinates, setShowCoordinates] = useLocalStorage<boolean>('board_show_coordinates', DEFAULT_BOARD_SHOW_COORDINATE)
  const [animationDuration, setAnimationDuration] = useLocalStorage<number>('board_ui_animation_duration', DEFAULT_BOARD_ANIMATION_DURATION)
  const [showEvalBar, setShowEvalBar] = useLocalStorage<boolean>('board_show_eval_bar', true)

  // Sound settings
  const [soundEnabled, setSoundEnabled] = useLocalStorage<boolean>('sound_enabled', true)
  const [moveSound, setMoveSound] = useLocalStorage<boolean>('sound_move', true)

  // Dark mode
  const { theme, setTheme } = useDarkMode()

  const currentThemeColors = BOARD_THEMES[boardTheme as keyof typeof BOARD_THEMES] || BOARD_THEMES.classic

  return (
    <div className="min-h-screen bg-gray-50 pb-24">
      {/* Header */}
      <div className="bg-gradient-to-br from-purple-600 to-purple-800 text-white">
        <div className="container mx-auto px-4 py-6">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.back()}
              className="p-2 rounded-xl bg-white/10 hover:bg-white/20 transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <div>
              <h1 className="text-2xl font-bold">Settings</h1>
              <p className="text-purple-200 text-sm">Customize your chess experience</p>
            </div>
          </div>
        </div>
      </div>

      <div className="container mx-auto px-4 py-6 space-y-6 animate-page-enter">

        {/* Appearance */}
        <div className="bg-white rounded-2xl shadow-md p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-1">🌗 Appearance</h2>
          <p className="text-sm text-gray-500 mb-4">Choose your display mode</p>

          <div className="grid grid-cols-3 gap-3">
            {(['light', 'dark', 'system'] as const).map((mode) => {
              const isSelected = theme === mode
              const labels = { light: 'Light', dark: 'Dark', system: 'System' }
              const icons = { light: '☀️', dark: '🌙', system: '💻' }
              return (
                <button
                  key={mode}
                  onClick={() => setTheme(mode)}
                  className={`rounded-xl p-4 transition-all flex flex-col items-center gap-2 ${
                    isSelected
                      ? 'bg-purple-50 ring-2 ring-purple-500 scale-105'
                      : 'bg-gray-50 hover:bg-gray-100'
                  }`}
                >
                  <span className="text-2xl">{icons[mode]}</span>
                  <span className={`text-sm font-medium ${isSelected ? 'text-purple-700' : 'text-gray-600'}`}>
                    {labels[mode]}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Board Theme */}
        <div className="bg-white rounded-2xl shadow-md p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-1">♞ Board Theme</h2>
          <p className="text-sm text-gray-500 mb-4">Choose your board colors</p>

          <div className="grid grid-cols-3 gap-3">
            {BOARD_THEME_KEYS.map((key) => {
              const theme = BOARD_THEMES[key]
              const isSelected = boardTheme === key
              return (
                <button
                  key={key}
                  onClick={() => setBoardTheme(key)}
                  className={`relative rounded-xl p-1 transition-all ${
                    isSelected
                      ? 'ring-2 ring-purple-500 ring-offset-2 scale-105'
                      : 'hover:scale-102 opacity-80 hover:opacity-100'
                  }`}
                >
                  {/* Mini board preview */}
                  <div className="aspect-square rounded-lg overflow-hidden grid grid-cols-4 grid-rows-4">
                    {Array.from({ length: 16 }).map((_, i) => {
                      const row = Math.floor(i / 4)
                      const col = i % 4
                      const isLight = (row + col) % 2 === 0
                      return (
                        <div
                          key={i}
                          style={{
                            backgroundColor: isLight ? theme.lightSquareColor : theme.darkSquareColor,
                          }}
                        />
                      )
                    })}
                  </div>
                  <div className={`text-xs font-medium text-center mt-1.5 ${isSelected ? 'text-purple-700' : 'text-gray-600'}`}>
                    {theme.name}
                  </div>
                  {isSelected && (
                    <div className="absolute -top-1 -right-1 w-5 h-5 bg-purple-500 rounded-full flex items-center justify-center">
                      <svg className="w-3 h-3 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                  )}
                </button>
              )
            })}
          </div>
        </div>

        {/* Piece Style */}
        <div className="bg-white rounded-2xl shadow-md p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-1">♚ Piece Style</h2>
          <p className="text-sm text-gray-500 mb-4">Choose your piece design</p>

          <div className="grid grid-cols-3 gap-3">
            {PIECE_KEYS.map((key) => {
              const isSelected = pieceType === key
              const previewSrc = `/static/pieces/${key}/bN.svg`
              return (
                <button
                  key={key}
                  onClick={() => setPieceType(key)}
                  className={`rounded-xl p-3 transition-all flex flex-col items-center ${
                    isSelected
                      ? 'bg-purple-50 ring-2 ring-purple-500 scale-105'
                      : 'bg-gray-50 hover:bg-gray-100 opacity-80 hover:opacity-100'
                  }`}
                >
                  <div className="w-12 h-12 relative" style={{ backgroundColor: currentThemeColors.darkSquareColor, borderRadius: '8px' }}>
                    <Image
                      src={previewSrc}
                      alt={key}
                      width={48}
                      height={48}
                      className="w-full h-full"
                      onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                    />
                  </div>
                  <span className={`text-xs font-medium mt-2 ${isSelected ? 'text-purple-700' : 'text-gray-600'}`}>
                    {PIECE_STYLE_TYPES[key].name}
                  </span>
                </button>
              )
            })}
          </div>
        </div>

        {/* Board Options */}
        <div className="bg-white rounded-2xl shadow-md p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-4">⚙️ Board Options</h2>

          <div className="space-y-4">
            {/* Show Coordinates */}
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-gray-900">Show coordinates</div>
                <div className="text-sm text-gray-500">Display a-h and 1-8 labels</div>
              </div>
              <button
                onClick={() => setShowCoordinates(!showCoordinates)}
                className={`relative w-12 h-7 rounded-full transition-colors ${
                  showCoordinates ? 'bg-purple-500' : 'bg-gray-300'
                }`}
              >
                <div className={`absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform ${
                  showCoordinates ? 'translate-x-5' : 'translate-x-0.5'
                }`} />
              </button>
            </div>

            {/* Show Eval Bar */}
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-gray-900">Evaluation bar</div>
                <div className="text-sm text-gray-500">Show engine evaluation</div>
              </div>
              <button
                onClick={() => setShowEvalBar(!showEvalBar)}
                className={`relative w-12 h-7 rounded-full transition-colors ${
                  showEvalBar ? 'bg-purple-500' : 'bg-gray-300'
                }`}
              >
                <div className={`absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform ${
                  showEvalBar ? 'translate-x-5' : 'translate-x-0.5'
                }`} />
              </button>
            </div>

            {/* Animation Speed */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <div>
                  <div className="font-medium text-gray-900">Animation speed</div>
                  <div className="text-sm text-gray-500">{animationDuration}ms</div>
                </div>
              </div>
              <input
                type="range"
                min={0}
                max={600}
                step={50}
                value={animationDuration}
                onChange={(e) => setAnimationDuration(Number(e.target.value))}
                className="w-full accent-purple-500"
              />
              <div className="flex justify-between text-xs text-gray-400 mt-1">
                <span>Instant</span>
                <span>Slow</span>
              </div>
            </div>
          </div>
        </div>

        {/* Sound Settings */}
        <div className="bg-white rounded-2xl shadow-md p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-4">🔊 Sound</h2>

          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-gray-900">Sound effects</div>
                <div className="text-sm text-gray-500">Enable all sounds</div>
              </div>
              <button
                onClick={() => setSoundEnabled(!soundEnabled)}
                className={`relative w-12 h-7 rounded-full transition-colors ${
                  soundEnabled ? 'bg-purple-500' : 'bg-gray-300'
                }`}
              >
                <div className={`absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform ${
                  soundEnabled ? 'translate-x-5' : 'translate-x-0.5'
                }`} />
              </button>
            </div>

            <div className="flex items-center justify-between">
              <div>
                <div className="font-medium text-gray-900">Move sounds</div>
                <div className="text-sm text-gray-500">Play sound on piece moves</div>
              </div>
              <button
                onClick={() => setMoveSound(!moveSound)}
                disabled={!soundEnabled}
                className={`relative w-12 h-7 rounded-full transition-colors ${
                  !soundEnabled ? 'bg-gray-200 cursor-not-allowed' :
                  moveSound ? 'bg-purple-500' : 'bg-gray-300'
                }`}
              >
                <div className={`absolute top-0.5 w-6 h-6 rounded-full bg-white shadow transition-transform ${
                  moveSound && soundEnabled ? 'translate-x-5' : 'translate-x-0.5'
                }`} />
              </button>
            </div>
          </div>
        </div>

        {/* Live Preview */}
        <div className="bg-white rounded-2xl shadow-md p-6">
          <h2 className="text-lg font-bold text-gray-900 mb-4">👁️ Preview</h2>
          <div className="flex justify-center">
            <div className="w-64 aspect-square rounded-xl overflow-hidden grid grid-cols-8 grid-rows-8 shadow-lg">
              {Array.from({ length: 64 }).map((_, i) => {
                const row = Math.floor(i / 8)
                const col = i % 8
                const isLight = (row + col) % 2 === 0
                // Place some pieces for preview
                const pieces: Record<string, string> = {
                  '0,0': 'bR', '0,1': 'bN', '0,2': 'bB', '0,3': 'bQ',
                  '0,4': 'bK', '0,5': 'bB', '0,6': 'bN', '0,7': 'bR',
                  '1,0': 'bP', '1,1': 'bP', '1,2': 'bP', '1,3': 'bP',
                  '1,4': 'bP', '1,5': 'bP', '1,6': 'bP', '1,7': 'bP',
                  '6,0': 'wP', '6,1': 'wP', '6,2': 'wP', '6,3': 'wP',
                  '6,4': 'wP', '6,5': 'wP', '6,6': 'wP', '6,7': 'wP',
                  '7,0': 'wR', '7,1': 'wN', '7,2': 'wB', '7,3': 'wQ',
                  '7,4': 'wK', '7,5': 'wB', '7,6': 'wN', '7,7': 'wR',
                }
                const piece = pieces[`${row},${col}`]
                return (
                  <div
                    key={i}
                    className="relative flex items-center justify-center"
                    style={{
                      backgroundColor: isLight ? currentThemeColors.lightSquareColor : currentThemeColors.darkSquareColor,
                    }}
                  >
                    {piece && (
                      <Image
                        src={`/static/pieces/${pieceType}/${piece}.svg`}
                        alt=""
                        width={32}
                        height={32}
                        className="w-full h-full p-0.5"
                        onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }}
                      />
                    )}
                    {showCoordinates && row === 7 && (
                      <span className={`absolute bottom-0 right-0.5 text-[6px] font-bold ${isLight ? 'text-gray-600' : 'text-gray-300'}`}>
                        {String.fromCharCode(97 + col)}
                      </span>
                    )}
                    {showCoordinates && col === 0 && (
                      <span className={`absolute top-0 left-0.5 text-[6px] font-bold ${isLight ? 'text-gray-600' : 'text-gray-300'}`}>
                        {8 - row}
                      </span>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
