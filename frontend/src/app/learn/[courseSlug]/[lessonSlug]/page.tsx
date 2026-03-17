'use client'

import { useEffect, useState, useRef } from 'react'
import { useAuth, SignInButton } from '@clerk/nextjs'
import { apiFetch, ApiError } from '@/lib/api'
import { useToast } from '@/components/ToastProvider'
import { useParams, useRouter } from 'next/navigation'
import ReactMarkdown from 'react-markdown'
import { useTranslations, useLocale } from 'next-intl'
import { AnimatedChessBoard, PuzzleSequence } from '@/components/chess'
import LoadingScreen from '@/components/LoadingScreen'
import Link from 'next/link'
import { ChevronDown, ChevronUp, MessageCircle } from 'lucide-react'
import Breadcrumbs from '@/components/Breadcrumbs'
import { XPGain } from '@/components/gamification/XPDisplay'
import { CelebrationOverlay, QuickCelebration } from '@/components/gamification/CelebrationOverlay'
import { InlineTip } from '@/components/mascot/SpeechBubble'

interface ArrowData {
  from: string
  path: string[]
}

interface ExerciseSolution {
  arrow?: ArrowData
  targets?: string[]
  requireAll?: boolean
  [key: string]: unknown
}

interface Lesson {
  id: string
  title: string
  content: string
  lesson_type: string
  slug: string
  course_slug: string
  course_title: string
  exercise_fen: string | null
  solution_move: string | null
  exercise_type: string | null
  hint_text: string | null
  success_message: string | null
  exercise_solution: ExerciseSolution | null
  has_multiple_puzzles: boolean | null
  puzzle_count: number | null
}

interface Message {
  role: 'user' | 'assistant'
  content: string
}

export default function LessonPage() {
  const params = useParams()
  const courseSlug = params?.courseSlug as string
  const lessonSlug = params?.lessonSlug as string
  const router = useRouter()
  const { getToken, isLoaded, isSignedIn } = useAuth()
  const t = useTranslations()
  const locale = useLocale()
  const { showToast } = useToast()
  const [lesson, setLesson] = useState<Lesson | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputMessage, setInputMessage] = useState('')
  const [sendingMessage, setSendingMessage] = useState(false)
  const [completingLesson, setCompletingLesson] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isChatExpanded, setIsChatExpanded] = useState(true)
  const chatContentRef = useRef<HTMLDivElement>(null)

  // Gamification state
  const [showXPGain, setShowXPGain] = useState(false)
  const [xpEarned, setXpEarned] = useState(0)
  const [showCelebration, setShowCelebration] = useState(false)
  const [showQuickCelebration, setShowQuickCelebration] = useState(false)
  const [quickCelebrationMessage, setQuickCelebrationMessage] = useState('')

  useEffect(() => {
    async function fetchLesson() {
      try {
        // Wait for auth to be loaded
        if (!isLoaded) return

        if (!isSignedIn) {
          setError(t('lesson.signInRequired'))
          setLoading(false)
          return
        }

        const token = await getToken()

        if (!token) {
          setError(t('lesson.authError'))
          setLoading(false)
          return
        }

        const apiUrl = process.env.NEXT_PUBLIC_API_URL
        const headers = { 'Authorization': `Bearer ${token}` }

        // Fetch lesson and chat history in parallel for faster loading
        try {
          const [lessonData, chatData] = await Promise.all([
            apiFetch<Lesson>(`${apiUrl}/api/learn/${courseSlug}/${lessonSlug}?locale=${locale}`, { headers }),
            apiFetch<any>(`${apiUrl}/api/learn/${courseSlug}/${lessonSlug}/chat?locale=${locale}`, { headers }).catch(() => ({ messages: [] }))
          ])

          setLesson(lessonData)
          setError(null)
          setMessages(chatData.messages || [])
        } catch (e) {
          if (e instanceof ApiError && e.status === 401) {
            setError(t('lesson.sessionExpired'))
            setLoading(false)
            return
          }
          throw e
        }

        // Mark lesson as in progress (fire-and-forget, don't block rendering)
        apiFetch(`${apiUrl}/api/learn/${courseSlug}/${lessonSlug}/progress?locale=${locale}`, {
          method: 'POST',
          headers: { ...headers, 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'in_progress' })
        }).catch(err => console.warn('Failed to update progress:', err))

      } catch (err) {
        console.error('Failed to fetch lesson:', err)
        setError(t('lesson.loadError'))
        if (err instanceof ApiError) {
          if (err.status === 408) {
            showToast('Request timed out — try again', 'error')
          } else if (err.status === 0) {
            showToast('Network error — check your connection', 'error')
          }
        }
      } finally {
        setLoading(false)
      }
    }

    if (courseSlug && lessonSlug && isLoaded) {
      fetchLesson()
    }
  }, [courseSlug, lessonSlug, getToken, isLoaded, isSignedIn])

  const sendMessage = async () => {
    if (!inputMessage.trim() || sendingMessage) return

    setSendingMessage(true)
    const userMessage = inputMessage
    setInputMessage('')

    // Optimistically add user message
    setMessages(prev => [...prev, { role: 'user', content: userMessage }])

    try {
      const token = await getToken()
      const data = await apiFetch<any>(
        `${process.env.NEXT_PUBLIC_API_URL}/api/learn/${courseSlug}/${lessonSlug}/chat?locale=${locale}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ message: userMessage })
        }
      )
      setMessages(data.messages || [])
    } catch (err) {
      console.error('Failed to send message:', err)
      showToast('Failed to send message — try again', 'error')
      // Revert optimistic update on error
      setMessages(prev => prev.slice(0, -1))
    } finally {
      setSendingMessage(false)
    }
  }

  const markLessonComplete = async () => {
    try {
      const token = await getToken()
      await apiFetch(
        `${process.env.NEXT_PUBLIC_API_URL}/api/learn/${courseSlug}/${lessonSlug}/progress?locale=${locale}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({ status: 'completed' })
        }
      )

      // Trigger XP gain animation
      const earnedXP = lesson?.lesson_type === 'exercise' ? 15 : 10
      setXpEarned(earnedXP)
      setShowXPGain(true)
    } catch (err) {
      console.error('Failed to mark lesson complete:', err)
      showToast('Failed to save progress — try again', 'error')
    }
  }

  // Handle correct move in exercise
  const handleCorrectMove = async () => {
    setQuickCelebrationMessage(t('lesson.greatMove'))
    setShowQuickCelebration(true)
    await markLessonComplete()
  }

  const completeLessonAndRedirect = async () => {
    if (completingLesson) return

    setCompletingLesson(true)
    try {
      await markLessonComplete()
      // Show celebration overlay before redirecting
      setShowCelebration(true)
    } catch (err) {
      console.error('Failed to complete lesson:', err)
      setCompletingLesson(false)
    }
  }

  const handleCelebrationClose = () => {
    setShowCelebration(false)
    setCompletingLesson(false)
    router.push(`/learn/${courseSlug}`)
  }

  if (loading || !isLoaded) {
    return <LoadingScreen isVisible={true} />
  }

  if (error || !isSignedIn) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="text-xl text-red-500 mb-4">
            {error || t('lesson.signInRequired')}
          </div>
          <SignInButton mode="modal">
            <button className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-2 px-6 rounded transition-colors">
              {t('common.signIn')}
            </button>
          </SignInButton>
          <div className="mt-4">
            <Link href={`/learn/${courseSlug}`} className="text-blue-600 hover:underline">
              ← {t('lesson.backToCourse')}
            </Link>
          </div>
        </div>
      </div>
    )
  }

  if (!lesson) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <div className="text-center">
          <div className="text-xl text-red-500 mb-4">{t('lesson.notFound')}</div>
          <Link href={`/learn/${courseSlug}`} className="text-blue-600 hover:underline">
            ← {t('lesson.backToCourse')}
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="container mx-auto px-4 py-8">
      <Breadcrumbs />
      <button
        onClick={() => router.push(`/learn/${courseSlug}`)}
        className="text-blue-600 hover:underline mb-4"
      >
        ← {t('lesson.backTo', { course: lesson.course_title || t('lesson.course') })}
      </button>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Lesson Content */}
        <div className="lg:col-span-2 bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
          <h1 className="text-3xl font-bold mb-4">{lesson.title}</h1>

          <span className={`inline-block px-3 py-1 rounded-full text-sm mb-6 ${
            lesson.lesson_type === 'theory'
              ? 'bg-blue-100 text-blue-800'
              : lesson.lesson_type === 'exercise'
              ? 'bg-yellow-100 text-yellow-800'
              : 'bg-purple-100 text-purple-800'
          }`}>
            {t(`course.lessonTypes.${lesson.lesson_type}`)}
          </span>

          <div className="prose dark:prose-invert max-w-none mb-6">
            <ReactMarkdown
              components={{
                p: ({ children }) => {
                  // Check if paragraph contains only a YouTube URL
                  const childArray = Array.isArray(children) ? children : [children]
                  const child = childArray[0]
                  if (typeof child === 'string') {
                    const text = child.trim()

                    // Detect YouTube URLs
                    const youtubeRegex = /^https?:\/\/(?:www\.)?(?:youtube\.com\/(?:embed\/|watch\?v=)|youtu\.be\/)([a-zA-Z0-9_-]{11})(?:\?.*)?$/
                    const match = text.match(youtubeRegex)

                    if (match) {
                      const videoId = match[1]
                      return (
                        <div style={{ position: 'relative', paddingBottom: '56.25%', height: 0, overflow: 'hidden' }}>
                          <iframe
                            src={`https://www.youtube.com/embed/${videoId}`}
                            style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' }}
                            frameBorder="0"
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                            allowFullScreen
                          />
                        </div>
                      )
                    }
                  }

                  // Default paragraph rendering
                  return <p>{children}</p>
                }
              }}
            >
              {lesson.content}
            </ReactMarkdown>
          </div>

          {/* Multi-puzzle lesson - show PuzzleSequence */}
          {lesson.has_multiple_puzzles && lesson.puzzle_count && lesson.puzzle_count > 0 && (
            <div className="mb-6">
              <h3 className="font-semibold mb-4">
                {t('lesson.practicePuzzles', { count: lesson.puzzle_count })}
              </h3>
              <PuzzleSequence
                courseSlug={courseSlug}
                lessonSlug={lessonSlug}
                getToken={getToken}
                onAllPuzzlesComplete={markLessonComplete}
              />
            </div>
          )}

          {/* Single puzzle lesson - show AnimatedChessBoard directly */}
          {!lesson.has_multiple_puzzles && lesson.exercise_fen && (lesson.solution_move || lesson.exercise_solution?.targets) && (
            <div className="mb-6">
              <InlineTip message={t('mascot.messages.findBestMove')} mood="thinking" variant="compact" />
              <div className="mt-4">
                <AnimatedChessBoard
                  fen={lesson.exercise_fen}
                  solutionMove={lesson.solution_move || undefined}
                  targetSquares={lesson.exercise_solution?.targets}
                  onCorrectMove={handleCorrectMove}
                  onIncorrectMove={(move) => {
                    // Move validation handled internally
                  }}
                  showHints={true}
                  enableAnimations={true}
                  arrowFromSquare={lesson.exercise_solution?.arrow?.from}
                  arrowPath={lesson.exercise_solution?.arrow?.path}
                  showArrowsOverlay={!lesson.exercise_solution?.targets}
                  showStar={!lesson.exercise_solution?.targets}
                  strictValidation={lesson.exercise_type === 'one_move_puzzle' && !((lesson.exercise_solution?.arrow?.path?.length ?? 0) > 1)}
                />
              </div>
              {lesson.hint_text && (
                <InlineTip message={lesson.hint_text} mood="happy" variant="highlight" />
              )}
            </div>
          )}

          <button
            onClick={completeLessonAndRedirect}
            disabled={completingLesson}
            className="w-full bg-gradient-to-r from-green-500 to-green-600 hover:from-green-600 hover:to-green-700 text-white font-semibold py-4 px-6 rounded-xl transition-all shadow-lg hover:shadow-xl active:scale-98 disabled:opacity-50 flex items-center justify-center gap-3"
          >
            {completingLesson ? (
              <>
                <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                {t('lesson.completing')}
              </>
            ) : (
              <>
                <span>{t('lesson.completeLesson')}</span>
                <span className="bg-white/20 px-2 py-0.5 rounded-full text-sm">
                  +{lesson.lesson_type === 'exercise' ? 15 : 10} XP
                </span>
              </>
            )}
          </button>
        </div>

        {/* AI Chat */}
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg overflow-hidden self-start">
          {/* Header with collapse toggle */}
          <div
            className="flex items-center justify-between p-4 cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-750 transition-colors"
            onClick={() => setIsChatExpanded(!isChatExpanded)}
          >
            <div className="flex items-center gap-2">
              <MessageCircle className="w-5 h-5 text-blue-600" />
              <h2 className="text-xl font-bold">{t('lesson.aiTutor')}</h2>
              {!isChatExpanded && messages.length > 0 && (
                <span className="bg-blue-100 text-blue-600 text-xs font-medium px-2 py-0.5 rounded-full">
                  {messages.length}
                </span>
              )}
            </div>
            <button
              className="p-1.5 rounded-full hover:bg-gray-200 dark:hover:bg-gray-600 transition-colors"
              aria-label={isChatExpanded ? t('lesson.collapseChat') : t('lesson.expandChat')}
            >
              {isChatExpanded ? (
                <ChevronUp className="w-5 h-5 text-gray-500" />
              ) : (
                <ChevronDown className="w-5 h-5 text-gray-500" />
              )}
            </button>
          </div>

          {/* Collapsible content - Messages area */}
          {isChatExpanded && (
            <div className="border-t border-gray-100 dark:border-gray-700">
              <div
                ref={chatContentRef}
                className="h-[400px] overflow-y-auto space-y-4 p-4"
              >
                {messages.length === 0 && (
                  <p className="text-gray-500 text-center mt-8">
                    {t('lesson.aiTutorPrompt')}
                  </p>
                )}

                {messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`p-3 rounded-lg ${
                      msg.role === 'user'
                        ? 'bg-blue-100 dark:bg-blue-900 ml-8'
                        : 'bg-gray-100 dark:bg-gray-700 mr-8'
                    }`}
                  >
                    <div className="font-semibold text-sm mb-1">
                      {msg.role === 'user' ? t('lesson.you') : t('lesson.aiTutor')}
                    </div>
                    <div className="text-sm">{msg.content}</div>
                  </div>
                ))}

                {sendingMessage && (
                  <div className="bg-gray-100 dark:bg-gray-700 mr-8 p-3 rounded-lg">
                    <div className="font-semibold text-sm mb-1">{t('lesson.aiTutor')}</div>
                    <div className="text-sm">{t('lesson.thinking')}</div>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Input - always visible */}
          <div className="flex space-x-2 p-4 border-t border-gray-100 dark:border-gray-700">
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendMessage()}
              placeholder={t('lesson.askQuestion')}
              className="flex-1 px-4 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-700 dark:border-gray-600"
              disabled={sendingMessage}
            />
            <button
              onClick={sendMessage}
              disabled={sendingMessage || !inputMessage.trim()}
              className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-2 rounded-lg transition-colors disabled:opacity-50"
            >
              {t('lesson.send')}
            </button>
          </div>
        </div>
      </div>

      {/* Gamification Overlays */}
      {showXPGain && (
        <XPGain amount={xpEarned} onComplete={() => setShowXPGain(false)} />
      )}

      {showQuickCelebration && (
        <QuickCelebration
          message={quickCelebrationMessage}
          icon="✨"
          xp={5}
          onComplete={() => setShowQuickCelebration(false)}
        />
      )}

      {showCelebration && (
        <CelebrationOverlay
          type="lessonComplete"
          title={t('gamification.celebration.lessonComplete')}
          subtitle={`${t('lesson.youveCompleted')} "${lesson.title}"`}
          xpGained={xpEarned}
          onClose={handleCelebrationClose}
          autoClose={false}
        />
      )}
    </div>
  )
}
