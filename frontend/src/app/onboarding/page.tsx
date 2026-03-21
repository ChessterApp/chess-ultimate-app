"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useLocale } from "next-intl";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { useGameData } from "@/lib/onboarding/GameDataContext";
import { getMostPlayedOpenings } from "@/lib/onboarding/gameFetcher";
import { translateOpeningName } from "@/lib/openings/openingNamesI18n";

const TOTAL_STEPS = 16;

const STEP_GROUPS = [
  { start: 1, end: 3 },   // About You (welcome, attribution, experience)
  { start: 4, end: 8 },   // Your Game (platform, username, ELO rating, focus, challenge)
  { start: 9, end: 11 },  // Goals (practice time, goal, timeline)
  { start: 12, end: 15 }, // Assessment (puzzle, skill profile, building plan, opening DNA)
  { start: 16, end: 16 }, // Your Plan (custom plan)
];

export default function OnboardingPage() {
  const t = useTranslations("onboarding");
  const router = useRouter();
  const locale = useLocale();
  const { gameData, fetchGames, isLoading } = useGameData();
  const [step, setStep] = useState(1);
  const [direction, setDirection] = useState<"forward" | "back">("forward");
  const [phase, setPhase] = useState<"idle" | "exiting" | "entering">("idle");

  // Answers state
  const [answers, setAnswers] = useState({
    attribution: "",
    experience: "",
    platform: "" as "" | "chessdotcom" | "lichess" | "none",
    platformUsername: "",
    onlineRating: 0,
    startFetch: false,
    eloRating: 800,
    noRating: false,
    focusAreas: [] as string[],
    challenge: "",
    practiceTime: "",
    goal: "",
    timeline: "",
    gameData: null as any, // OnboardingGameData | null - will be populated by game fetcher
  });

  // Sync game data into answers when it arrives
  useEffect(() => {
    if (gameData) setAnswers(a => ({ ...a, gameData }));
  }, [gameData]);

  // Trigger game fetch when username is validated
  const prevStartFetch = useRef(false);
  useEffect(() => {
    if (answers.startFetch && !prevStartFetch.current && answers.platform && answers.platform !== 'none' && answers.platformUsername) {
      fetchGames(answers.platform as 'lichess' | 'chessdotcom', answers.platformUsername);
    }
    prevStartFetch.current = answers.startFetch;
  }, [answers.startFetch, answers.platform, answers.platformUsername, fetchGames]);

  const goNext = useCallback(() => {
    if (phase !== "idle") return;
    setDirection("forward");
    setPhase("exiting");
    setTimeout(() => {
      if (step >= TOTAL_STEPS) {
        router.push("/learn");
      } else {
        // Skip step 5 (username) if platform is 'none'
        if (step === 4 && answers.platform === "none") {
          setStep(6);
        // Skip step 15 (opening DNA) only if no platform selected
        } else if (step === 14 && answers.platform === "none") {
          setStep(16);
        } else {
          setStep((s) => s + 1);
        }
      }
      setPhase("entering");
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setPhase("idle");
        });
      });
    }, 300);
  }, [phase, step, router, answers.platform, answers.gameData]);

  const goBack = useCallback(() => {
    if (phase !== "idle" || step <= 1) return;
    setDirection("back");
    setPhase("exiting");
    setTimeout(() => {
      setStep((s) => {
        // Skip step 5 going back if platform is 'none'
        if (s === 6 && answers.platform === "none") return 4;
        // Skip step 15 going back if platform is 'none'
        if (s === 16 && answers.platform === "none") return 14;
        return s - 1;
      });
      setPhase("entering");
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          setPhase("idle");
        });
      });
    }, 300);
  }, [phase, step, answers.platform]);

  const isEntering = phase === "entering";
  const slideClass =
    phase === "exiting"
      ? direction === "forward"
        ? "translate-x-[-100%]"
        : "translate-x-[100%]"
      : isEntering
        ? direction === "forward"
          ? "translate-x-[100%]"
          : "translate-x-[-100%]"
        : "translate-x-0";

  return (
    <div className="min-h-screen flex flex-col overflow-hidden">
      {/* Language switcher */}
      <div className="fixed top-12 right-6 z-50">
        <LanguageSwitcher currentLocale={locale} variant="minimal" className="[&_button]:text-white/80 [&_button]:hover:text-white [&_button]:hover:bg-white/10" />
      </div>

      {/* Segmented progress bar */}
      <div className="fixed top-0 left-0 right-0 z-50 px-6 pt-4 pb-2 flex items-center gap-1">
        {step > 1 && (
          <button onClick={goBack} className="text-white/80 hover:text-white p-1 mr-2 flex-shrink-0">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
          </button>
        )}
        {STEP_GROUPS.map((group, i) => {
          const isCompleted = step > group.end;
          const isActive = step >= group.start && step <= group.end;
          const fillPercent = isActive
            ? ((step - group.start) / (group.end - group.start + 1)) * 100
            : 0;
          return (
            <div key={i} className="flex-1 h-[6px] rounded-full overflow-hidden bg-white/30">
              <div
                className={`h-full rounded-full transition-all duration-500 ease-out ${
                  isCompleted ? 'bg-white w-full' : isActive ? 'bg-white' : ''
                }`}
                style={{
                  width: isCompleted ? '100%' : isActive ? `${fillPercent}%` : '0%',
                }}
              />
            </div>
          );
        })}
      </div>

      {/* Content */}
      <div
        className={`flex-1 flex flex-col ease-in-out ${slideClass} ${isEntering ? '' : 'transition-transform duration-300'}`}
        style={isEntering ? { transition: 'none' } : undefined}
      >
        <div className="flex-1 flex flex-col justify-center max-w-md mx-auto w-full px-6 pt-16 pb-8">
          {step === 1 && <StepWelcome t={t} onNext={goNext} />}
          {step === 2 && <StepAttribution t={t} onSelect={(v: string) => { setAnswers(a => ({ ...a, attribution: v })); goNext(); }} />}
          {step === 3 && <StepExperience t={t} onSelect={(v: string) => { setAnswers(a => ({ ...a, experience: v })); goNext(); }} />}
          {step === 4 && <StepPlatform t={t} onSelect={(v: "chessdotcom" | "lichess" | "none") => { setAnswers(a => ({ ...a, platform: v })); if (v === "none") { setDirection("forward"); setPhase("exiting"); setTimeout(() => { setStep(6); setPhase("entering"); requestAnimationFrame(() => { requestAnimationFrame(() => { setPhase("idle"); }); }); }, 300); } else { goNext(); } }} />}
          {step === 5 && answers.platform !== "none" && <StepUsername t={t} answers={answers} setAnswers={setAnswers} onNext={goNext} />}
          {step === 6 && <StepRating t={t} answers={answers} setAnswers={setAnswers} onNext={goNext} />}
          {step === 7 && <StepFocusAreas t={t} answers={answers} setAnswers={setAnswers} onNext={goNext} />}
          {step === 8 && <StepChallenge t={t} onSelect={(v: string) => { setAnswers(a => ({ ...a, challenge: v })); goNext(); }} />}
          {step === 9 && <StepPracticeTime t={t} onSelect={(v: string) => { setAnswers(a => ({ ...a, practiceTime: v })); goNext(); }} />}
          {step === 10 && <StepGoal t={t} answers={answers} onSelect={(v: string) => { setAnswers(a => ({ ...a, goal: v })); goNext(); }} />}
          {step === 11 && <StepTimeline t={t} onSelect={(v: string) => { setAnswers(a => ({ ...a, timeline: v })); goNext(); }} />}
          {step === 12 && <StepPuzzle t={t} onNext={goNext} />}
          {step === 13 && <StepSkillProfile t={t} answers={answers} onNext={goNext} />}
          {step === 14 && <StepBuildingPlan t={t} answers={answers} onComplete={goNext} isFetchingGames={isLoading} />}
          {step === 15 && <StepOpeningDNAGate t={t} answers={answers} isLoading={isLoading} onNext={goNext} />}
          {step === 16 && <StepCustomPlan t={t} answers={answers} onNext={goNext} />}
          {step === 17 && <StepPaywall1 t={t} onNext={goNext} />}
          {step === 18 && <StepPaywall2 t={t} onNext={goNext} />}
          {step === 19 && <StepPaywall t={t} router={router} />}
        </div>
      </div>
    </div>
  );
}

/* ─── Step Components ─── */

function StepWelcome({ t, onNext }: { t: any; onNext: () => void }) {
  return (
    <div className="flex-1 flex flex-col items-center justify-center text-center gap-6">
      <div className="w-40 h-40 rounded-full bg-white overflow-hidden flex items-center justify-center p-3 shadow-xl">
        <Image src="/static/images/chesster-logo-v3.png" alt="Chesster" width={140} height={140} />
      </div>
      <h1 className="text-3xl font-bold text-white">{t("welcome.title")}</h1>
      <p className="text-white/70 text-lg">{t("welcome.subtitle")}</p>
      <button onClick={onNext} className="mt-4 bg-white text-purple-700 font-bold text-lg px-10 py-4 rounded-full shadow-lg hover:scale-105 transition-transform active:scale-95">
        {t("welcome.getStarted")}
      </button>
      <p className="text-white/80 text-sm mt-4"><a href="/sign-in" className="text-white underline hover:text-white/90">{t("welcome.signIn")}</a></p>
    </div>
  );
}

function OptionCard({ emoji, label, onClick, selected }: { emoji: string; label: string; onClick: () => void; selected?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`flex flex-col items-center justify-center gap-2 bg-white rounded-2xl p-4 min-h-[80px] shadow-md hover:scale-[1.02] active:scale-[0.98] transition-all ${selected ? "ring-2 ring-purple-500" : ""}`}
    >
      <span className="text-2xl">{emoji}</span>
      <span className="text-sm font-medium text-gray-800">{label}</span>
    </button>
  );
}

function StepAttribution({ t, onSelect }: { t: any; onSelect: (v: string) => void }) {
  const options = [
    { key: "socialMedia", emoji: "📱" },
    { key: "friend", emoji: "👥" },
    { key: "appStore", emoji: "🏪" },
    { key: "youtube", emoji: "▶️" },
    { key: "ad", emoji: "📣" },
    { key: "other", emoji: "💬" },
  ];
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("attribution.title")}</h2>
      <div className="grid grid-cols-2 gap-3">
        {options.map((o) => (
          <OptionCard key={o.key} emoji={o.emoji} label={t(`attribution.${o.key}`)} onClick={() => onSelect(o.key)} />
        ))}
      </div>
    </div>
  );
}

function StepExperience({ t, onSelect }: { t: any; onSelect: (v: string) => void }) {
  const levels = [
    { key: "beginner", emoji: "🌱" },
    { key: "intermediate", emoji: "♟️" },
    { key: "advanced", emoji: "🏆" },
  ];
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("experience.title")}</h2>
      <div className="flex flex-col gap-3">
        {levels.map((l) => (
          <button
            key={l.key}
            onClick={() => onSelect(l.key)}
            className="flex items-center gap-4 bg-white rounded-2xl p-5 shadow-md hover:scale-[1.01] active:scale-[0.99] transition-all"
          >
            <span className="text-3xl">{l.emoji}</span>
            <div className="text-left">
              <div className="font-bold text-gray-900">{t(`experience.${l.key}.title`)}</div>
              <div className="text-sm text-gray-500">{t(`experience.${l.key}.desc`)}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function StepPlatform({ t, onSelect }: { t: any; onSelect: (v: "chessdotcom" | "lichess" | "none") => void }) {
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("platform.title")}</h2>
      <div className="flex flex-col gap-3">
        <button
          onClick={() => onSelect("chessdotcom")}
          className="flex items-center gap-4 bg-white rounded-2xl p-5 shadow-md hover:scale-[1.01] active:scale-[0.99] transition-all"
        >
          <Image src="/static/images/platforms/chesscom.png" alt="Chess.com" width={48} height={48} className="rounded-lg" />
          <div className="text-left">
            <div className="font-bold text-gray-900">Chess.com</div>
            <div className="text-sm text-gray-500">{t("platform.importDesc")}</div>
          </div>
        </button>
        <button
          onClick={() => onSelect("lichess")}
          className="flex items-center gap-4 bg-white rounded-2xl p-5 shadow-md hover:scale-[1.01] active:scale-[0.99] transition-all"
        >
          <Image src="/static/images/platforms/lichess.png" alt="Lichess" width={48} height={48} className="rounded-lg" />
          <div className="text-left">
            <div className="font-bold text-gray-900">Lichess.org</div>
            <div className="text-sm text-gray-500">{t("platform.importDesc")}</div>
          </div>
        </button>
        <button
          onClick={() => onSelect("none")}
          className="flex items-center gap-4 bg-white rounded-2xl p-5 shadow-md hover:scale-[1.01] active:scale-[0.99] transition-all"
        >
          <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5 21 12m0 0-7.5 7.5M21 12H3" /></svg>
          <span className="font-bold text-gray-500">{t("platform.skip")}</span>
        </button>
      </div>
    </div>
  );
}

function StepUsername({ t, answers, setAnswers, onNext }: { t: any; answers: any; setAnswers: any; onNext: () => void }) {
  const [username, setUsername] = useState(answers.platformUsername || "");
  const [status, setStatus] = useState<"idle" | "checking" | "found" | "notfound">("idle");
  const [foundRating, setFoundRating] = useState<number | null>(null);
  const [ratingType, setRatingType] = useState<string>("");
  const debounceRef = useRef<NodeJS.Timeout | null>(null);

  const platformName = answers.platform === "chessdotcom" ? "Chess.com" : "Lichess";

  const validateUsername = useCallback(async (name: string) => {
    if (!name.trim()) { setStatus("idle"); return; }
    setStatus("checking");
    setFoundRating(null);
    try {
      if (answers.platform === "lichess") {
        const res = await fetch(`https://lichess.org/api/user/${name}`);
        if (res.ok) {
          const data = await res.json();
          const lichessEntries: [string, number][] = [
                ["Rapid", data?.perfs?.rapid?.rating],
                ["Blitz", data?.perfs?.blitz?.rating],
                ["Bullet", data?.perfs?.bullet?.rating],
                ["Classical", data?.perfs?.classical?.rating],
                ["Correspondence", data?.perfs?.correspondence?.rating],
              ].filter((e): e is [string, number] => typeof e[1] === "number" && e[1] > 0);
              const best = lichessEntries.sort((a, b) => b[1] - a[1])[0];
              const rating = best ? best[1] : 0;
          setFoundRating(rating);
          setRatingType(best ? best[0] : "");
          setStatus("found");
          setAnswers((a: any) => ({ ...a, platformUsername: name, onlineRating: rating, startFetch: true }));
        } else {
          setStatus("notfound");
        }
      } else {
        const res = await fetch(`https://api.chess.com/pub/player/${name.toLowerCase()}`);
        if (res.ok) {
          // Fetch stats for rating
          try {
            const statsRes = await fetch(`https://api.chess.com/pub/player/${name.toLowerCase()}/stats`);
            if (statsRes.ok) {
              const stats = await statsRes.json();
              const chessEntries: [string, number][] = [
                ["Rapid", stats?.chess_rapid?.last?.rating],
                ["Blitz", stats?.chess_blitz?.last?.rating],
                ["Bullet", stats?.chess_bullet?.last?.rating],
                ["Daily", stats?.chess_daily?.last?.rating],
              ].filter((e): e is [string, number] => typeof e[1] === "number" && e[1] > 0);
              const best = chessEntries.sort((a, b) => b[1] - a[1])[0];
              const rating = best ? best[1] : 0;
              setFoundRating(rating);
              setRatingType(best ? best[0] : "");
              setAnswers((a: any) => ({ ...a, platformUsername: name, onlineRating: rating, startFetch: true }));
            } else {
              setAnswers((a: any) => ({ ...a, platformUsername: name, startFetch: true }));
            }
          } catch {
            setAnswers((a: any) => ({ ...a, platformUsername: name, startFetch: true }));
          }
          setStatus("found");
        } else {
          setStatus("notfound");
        }
      }
    } catch {
      setStatus("notfound");
    }
  }, [answers.platform, setAnswers]);

  const handleChange = (value: string) => {
    setUsername(value);
    setStatus("idle");
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => validateUsername(value), 500);
  };

  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">
        {t("username.title", { platform: platformName })}
      </h2>
      <div className="bg-white rounded-2xl p-6 shadow-md">
        <div className="flex items-center gap-3 mb-4">
          <span className="text-2xl">{answers.platform === "chessdotcom" ? "♔" : "♞"}</span>
          <input
            type="text"
            value={username}
            onChange={(e) => handleChange(e.target.value)}
            placeholder={t("username.placeholder")}
            className="flex-1 text-lg font-medium text-gray-900 outline-none border-b-2 border-gray-200 focus:border-purple-500 pb-1 transition-colors"
          />
        </div>
        {status === "checking" && (
          <p className="text-gray-400 text-sm">{t("username.checking")}</p>
        )}
        {status === "found" && (
          <p className="text-green-600 text-sm font-medium">
            ✅ {t("username.found")}{foundRating ? ` ${ratingType} ${t("username.rating", { rating: foundRating })}` : ""}
          </p>
        )}
        {status === "notfound" && (
          <p className="text-red-500 text-sm font-medium">{t("username.notFound")}</p>
        )}
      </div>
      <button
        onClick={onNext}
        disabled={status !== "found"}
        className="bg-white text-purple-700 font-bold text-lg py-4 rounded-full shadow-lg hover:scale-105 active:scale-95 transition-transform disabled:opacity-40 disabled:scale-100"
      >
        {t("username.continue")}
      </button>
    </div>
  );
}

function StepRating({ t, answers, setAnswers, onNext }: { t: any; answers: any; setAnswers: any; onNext: () => void }) {
  const getRatingLabel = (v: number) => {
    if (v < 400) return t("rating.unrated");
    if (v < 800) return t("rating.beginner");
    if (v < 1200) return t("rating.club");
    if (v < 1600) return t("rating.intermediate");
    if (v < 2000) return t("rating.advanced");
    return t("rating.expert");
  };
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <div className="text-center">
        <h2 className="text-2xl font-bold text-white">{t("rating.title")}</h2>
        <p className="text-white/60 text-sm mt-1">{t("rating.subtitle")}</p>
      </div>
      <div className="bg-white rounded-2xl p-6 shadow-md">
        {!answers.noRating && (
          <>
            <div className="text-center mb-4">
              <span className="text-5xl font-bold text-purple-700">{answers.eloRating}</span>
              <p className="text-sm text-gray-500 mt-1">{getRatingLabel(answers.eloRating)}</p>
            </div>
            <input
              type="range"
              min={0}
              max={2500}
              step={50}
              value={answers.eloRating}
              onChange={(e) => setAnswers((a: any) => ({ ...a, eloRating: parseInt(e.target.value) }))}
              className="w-full accent-purple-600"
            />
            <div className="flex justify-between text-xs text-gray-400 mt-1">
              <span>0</span><span>800</span><span>1600</span><span>2500</span>
            </div>
          </>
        )}
        <label className="flex items-center gap-3 mt-4 cursor-pointer">
          <input
            type="checkbox"
            checked={answers.noRating}
            onChange={(e) => setAnswers((a: any) => ({ ...a, noRating: e.target.checked }))}
            className="w-5 h-5 accent-purple-600"
          />
          <span className="text-gray-700">{t("rating.noRating")}</span>
        </label>
      </div>
      <button onClick={onNext} className="bg-white text-purple-700 font-bold text-lg py-4 rounded-full shadow-lg hover:scale-105 active:scale-95 transition-transform">
        {t("continue")}
      </button>
    </div>
  );
}

function StepFocusAreas({ t, answers, setAnswers, onNext }: { t: any; answers: any; setAnswers: any; onNext: () => void }) {
  const areas = [
    { key: "tactics", emoji: "♞" },
    { key: "openings", emoji: "♗" },
    { key: "endgames", emoji: "♜" },
    { key: "strategy", emoji: "♛" },
    { key: "timeManagement", emoji: "⏱" },
    { key: "calculation", emoji: "🧮" },
  ];
  const toggle = (key: string) => {
    setAnswers((a: any) => ({
      ...a,
      focusAreas: a.focusAreas.includes(key) ? a.focusAreas.filter((k: string) => k !== key) : [...a.focusAreas, key],
    }));
  };
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("focus.title")}</h2>
      <div className="grid grid-cols-2 gap-3">
        {areas.map((a) => {
          const sel = answers.focusAreas.includes(a.key);
          return (
            <button
              key={a.key}
              onClick={() => toggle(a.key)}
              className={`flex flex-col items-center justify-center gap-2 bg-white rounded-2xl p-4 min-h-[80px] shadow-md transition-all ${sel ? "ring-2 ring-purple-500" : ""}`}
            >
              <span className="text-2xl">{a.emoji}</span>
              <span className="text-sm font-medium text-gray-800">{t(`focus.${a.key}`)}</span>
              {sel && <span className="text-purple-600 text-xs">✓</span>}
            </button>
          );
        })}
      </div>
      <button
        onClick={onNext}
        disabled={answers.focusAreas.length === 0}
        className="bg-white text-purple-700 font-bold text-lg py-4 rounded-full shadow-lg hover:scale-105 active:scale-95 transition-transform disabled:opacity-40 disabled:scale-100"
      >
        {t("continue")}
      </button>
    </div>
  );
}

function StepChallenge({ t, onSelect }: { t: any; onSelect: (v: string) => void }) {
  const items = ["blunder", "openings", "time", "convert"];
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("challenge.title")}</h2>
      <div className="flex flex-col gap-3">
        {items.map((k) => (
          <button key={k} onClick={() => onSelect(k)} className="bg-white rounded-2xl p-5 shadow-md text-left font-medium text-gray-800 hover:scale-[1.01] active:scale-[0.99] transition-all">
            {t(`challenge.${k}`)}
          </button>
        ))}
      </div>
    </div>
  );
}

function StepPracticeTime({ t, onSelect }: { t: any; onSelect: (v: string) => void }) {
  const items = [
    { key: "5min", emoji: "⏰" },
    { key: "10min", emoji: "⏰" },
    { key: "15min", emoji: "⏰" },
    { key: "30min", emoji: "⏰" },
  ];
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("practiceTime.title")}</h2>
      <div className="flex flex-col gap-3">
        {items.map((i) => (
          <button key={i.key} onClick={() => onSelect(i.key)} className="flex items-center gap-4 bg-white rounded-2xl p-5 shadow-md hover:scale-[1.01] active:scale-[0.99] transition-all">
            <span className="text-2xl">{i.emoji}</span>
            <div className="text-left">
              <div className="font-bold text-gray-900">{t(`practiceTime.${i.key}.title`)}</div>
              <div className="text-sm text-gray-500">{t(`practiceTime.${i.key}.desc`)}</div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}

function StepGoal({ t, answers, onSelect }: { t: any; answers: any; onSelect: (v: string) => void }) {
  const hasNoRating = answers.noRating === true;
  const rating = answers.eloRating || 0;
  const ratingTarget = rating + 100;

  // 4th option: beginners get "Learn fundamentals", 1800+ get "Become titled player", middle get "Compete in tournaments"
  const fourthOption = rating >= 1800
    ? { key: "titledPlayer", emoji: "👑" }
    : rating < 800
      ? { key: "learnFundamentals", emoji: "📚" }
      : { key: "tournaments", emoji: "🏆" };

  const items = [
    { key: "beatFriends", emoji: "👫" },
    hasNoRating
      ? { key: "internationalRating", emoji: "📈" }
      : { key: "gainRating", emoji: "📈", dynamic: true },
    fourthOption,
    { key: "masterStrategy", emoji: "🧠" },
  ];
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("goal.title")}</h2>
      <div className="flex flex-col gap-3">
        {items.map((i) => (
          <button key={i.key} onClick={() => onSelect(i.key)} className="flex items-center gap-4 bg-white rounded-2xl p-5 shadow-md hover:scale-[1.01] active:scale-[0.99] transition-all">
            <span className="text-2xl">{i.emoji}</span>
            <span className="font-bold text-gray-900">{(i as any).dynamic ? t("goal.gainRating", { rating: ratingTarget }) : t(`goal.${i.key}`)}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function StepTimeline({ t, onSelect }: { t: any; onSelect: (v: string) => void }) {
  const items = ["1month", "3months", "6months", "1year"];
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("timeline.title")}</h2>
      <div className="flex flex-col gap-3">
        {items.map((k) => (
          <button key={k} onClick={() => onSelect(k)} className="bg-white rounded-2xl p-5 shadow-md text-center font-bold text-gray-800 hover:scale-[1.01] active:scale-[0.99] transition-all">
            {t(`timeline.${k}`)}
          </button>
        ))}
      </div>
    </div>
  );
}

function StepPuzzle({ t, onNext }: { t: any; onNext: () => void }) {
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center items-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("puzzle.title")}</h2>
      <div className="bg-white rounded-2xl p-10 shadow-md w-full flex flex-col items-center gap-4">
        <span className="text-6xl">🎯</span>
        <p className="text-gray-500 font-medium">{t("puzzle.comingSoon")}</p>
        <button onClick={onNext} className="text-purple-600 text-sm underline">{t("puzzle.skip")}</button>
      </div>
      <button onClick={onNext} className="bg-white text-purple-700 font-bold text-lg py-4 px-10 rounded-full shadow-lg hover:scale-105 active:scale-95 transition-transform">
        {t("continue")}
      </button>
    </div>
  );
}

function StepSkillProfile({ t, answers, onNext }: { t: any; answers: any; onNext: () => void }) {
  const gameData = (answers as any).gameData || null;
  const stats = gameData?.stats;

  // Compute skills from real data or use defaults
  const skills = stats
    ? (() => {
        const allOpenings = [
          ...(stats.bestOpeningsWhite || []),
          ...(stats.worstOpeningsWhite || []),
          ...(stats.bestOpeningsBlack || []),
          ...(stats.worstOpeningsBlack || []),
        ];
        const distinctOpenings = new Set(allOpenings.map((o: any) => o.eco)).size;
        const openingKnowledge = Math.min(100, distinctOpenings * 5);
        const consistency =
          stats.ratingTrend === "improving" ? 70 : stats.ratingTrend === "stable" ? 50 : 30;
        return [
          { label: t("skillProfile.winRate"), value: Math.round(stats.winRate || 0) },
          { label: t("skillProfile.openingKnowledge"), value: openingKnowledge },
          { label: t("skillProfile.consistency"), value: consistency },
          { label: t("skillProfile.endgame"), value: 50 },
        ];
      })()
    : [
        { label: t("focus.tactics"), value: 60 },
        { label: t("focus.openings"), value: 40 },
        { label: t("focus.endgames"), value: 30 },
        { label: t("focus.strategy"), value: 50 },
      ];

  const [animated, setAnimated] = useState(false);
  const [displayValues, setDisplayValues] = useState(skills.map(() => 0));

  useEffect(() => {
    // Trigger bar animation on mount
    const timer = setTimeout(() => setAnimated(true), 100);
    return () => clearTimeout(timer);
  }, []);

  useEffect(() => {
    // Count-up animation for numbers
    if (!animated) return;
    const interval = setInterval(() => {
      setDisplayValues((prev) =>
        prev.map((v, i) => {
          const target = skills[i].value;
          if (v >= target) return target;
          return Math.min(target, v + Math.max(1, Math.floor(target / 20)));
        })
      );
    }, 30);
    return () => clearInterval(interval);
  }, [animated, skills]);

  const bestOpening = stats?.bestOpeningsWhite?.[0];
  const worstOpening = stats?.worstOpeningsWhite?.[0];

  const mascotMessage = stats
    ? t("skillProfile.dataMessage", { games: stats.totalGames, opening: bestOpening?.name || "opening", weakness: worstOpening?.name || "weakest opening" })
    : t("skillProfile.message");

  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("skillProfile.title")}</h2>
      <div className="bg-white rounded-2xl p-6 shadow-md space-y-4">
        {skills.map((s, i) => (
          <div key={s.label}>
            <div className="flex justify-between text-sm font-medium text-gray-700 mb-1">
              <span>{s.label}</span>
              <span>{displayValues[i]}%</span>
            </div>
            <div className="h-3 bg-gray-200 rounded-full overflow-hidden">
              <div
                className="h-full bg-purple-600 rounded-full transition-all duration-1000 ease-out"
                style={{
                  width: animated ? `${s.value}%` : "0%",
                  transitionDelay: `${i * 150}ms`,
                }}
              />
            </div>
          </div>
        ))}

        {/* Opening insights (only with real data) */}
        {stats && bestOpening && worstOpening && (
          <div className="border-t border-gray-100 pt-3 mt-3 space-y-1">
            <p className="text-sm text-gray-700">
              🏆 {t("skillProfile.best", { name: bestOpening.name, rate: Math.round(bestOpening.winRate) })}
            </p>
            <p className="text-sm text-gray-700">
              ⚠️ {t("skillProfile.needsWork", { name: worstOpening.name, rate: Math.round(worstOpening.winRate) })}
            </p>
          </div>
        )}

        {/* Prompt to connect if no data */}
        {!stats && (
          <p className="text-xs text-gray-400 text-center pt-2">
            {t("skillProfile.connectPrompt")}
          </p>
        )}
      </div>
      <div className="flex items-start gap-3 bg-white/10 rounded-2xl p-4">
        <div className="w-12 h-12 rounded-full bg-white overflow-hidden flex items-center justify-center p-1">
          <Image src="/static/images/chesster-logo-v3.png" alt="Chesster" width={40} height={40} />
        </div>
        <div className="bg-white rounded-2xl rounded-tl-none px-4 py-3 text-sm text-gray-800 shadow">
          {mascotMessage}
        </div>
      </div>
      <button onClick={onNext} className="bg-white text-purple-700 font-bold text-lg py-4 rounded-full shadow-lg hover:scale-105 active:scale-95 transition-transform">
        {t("continue")}
      </button>
    </div>
  );
}

function StepOpeningDNAGate({ t, answers, isLoading, onNext }: { t: any; answers: any; isLoading: boolean; onNext: () => void }) {
  const hasData = !!answers.gameData?.stats && (answers.gameData?.games?.length > 0);

  // If no platform selected, skip immediately
  if (answers.platform === 'none') {
    return <AutoAdvance onNext={onNext} />;
  }

  // Data is ready — show full Opening DNA screen
  if (hasData) return <StepOpeningDNA t={t} answers={answers} onNext={onNext} />;

  // Still loading — show spinner
  if (isLoading) {
    return (
      <div className="flex-1 flex flex-col gap-6 justify-center items-center">
        <div className="w-10 h-10 border-4 border-white/30 border-t-white rounded-full animate-spin" />
        <p className="text-white text-lg font-medium animate-pulse">{t("openingDNA.analyzing") || "Analyzing your games..."}</p>
      </div>
    );
  }

  // Loading finished but no data — show fallback
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center items-center text-center">
      <span className="text-5xl">♟️</span>
      <h2 className="text-2xl font-bold text-white">{t("openingDNA.title") || "Your Opening DNA"}</h2>
      <p className="text-white/80 text-base max-w-xs">
        {t("openingDNA.fallback") || "We couldn't fetch your games, but don't worry — we'll personalize your experience as you play!"}
      </p>
      <button onClick={onNext} className="w-full bg-white text-purple-700 font-bold text-lg py-4 rounded-full shadow-lg hover:scale-105 active:scale-95 transition-transform">
        {t("continue")}
      </button>
    </div>
  );
}

function AutoAdvance({ onNext }: { onNext: () => void }) {
  useEffect(() => {
    const timer = setTimeout(onNext, 100);
    return () => clearTimeout(timer);
  }, [onNext]);
  return null;
}

function StepOpeningDNA({ t, answers, onNext }: { t: any; answers: any; onNext: () => void }) {
  const locale = useLocale();
  const gameData = answers.gameData;
  const stats = gameData?.stats;
  const games = gameData?.games || [];

  const whiteOpenings = getMostPlayedOpenings(games, 'white');
  const blackOpenings = getMostPlayedOpenings(games, 'black');

  const bestWhite = stats?.bestOpeningsWhite?.[0];
  const worstWhite = stats?.worstOpeningsWhite?.[0];
  const bestBlack = stats?.bestOpeningsBlack?.[0];
  const worstBlack = stats?.worstOpeningsBlack?.[0];

  const [phase, setPhase] = useState(0);
  const [displayValues, setDisplayValues] = useState<number[]>(
    [...whiteOpenings, ...blackOpenings].map(() => 0)
  );

  useEffect(() => {
    setPhase(1);
    const t2 = setTimeout(() => setPhase(2), 1500);
    const t3 = setTimeout(() => setPhase(3), 3000);
    return () => { clearTimeout(t2); clearTimeout(t3); };
  }, []);

  const allOpenings = [...whiteOpenings, ...blackOpenings];
  useEffect(() => {
    if (phase < 1) return;
    const interval = setInterval(() => {
      setDisplayValues((prev) =>
        prev.map((v, i) => {
          // Only animate white (0..white.len-1) in phase>=1, black in phase>=2
          if (i >= whiteOpenings.length && phase < 2) return 0;
          const target = allOpenings[i]?.playPercentage || 0;
          if (v >= target) return target;
          return Math.min(target, v + Math.max(1, Math.floor(target / 20)));
        })
      );
    }, 30);
    return () => clearInterval(interval);
  }, [phase, whiteOpenings.length, allOpenings]);

  const winRateColor = (wr: number) =>
    wr > 60 ? 'text-green-600' : wr >= 40 ? 'text-amber-500' : 'text-red-500';

  const renderSection = (
    title: string,
    icon: string,
    openings: typeof whiteOpenings,
    best: any,
    worst: any,
    offset: number,
    visible: boolean
  ) => (
    <div className={`transition-all duration-700 ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
      <h3 className="text-white font-bold text-lg mb-2">{icon} {title}</h3>
      <div className="bg-white rounded-2xl p-4 shadow-md space-y-3">
        {openings.length === 0 ? (
          <p className="text-sm text-gray-400">{t("openingDNA.noData")}</p>
        ) : openings.map((op, i) => {
          const isBest = best && op.eco === best.eco;
          const isWorst = worst && op.eco === worst.eco;
          return (
            <div key={op.eco}>
              <div className="flex items-center justify-between text-sm mb-1">
                <span className="font-medium text-gray-800 truncate max-w-[60%]">
                  {translateOpeningName(op.name, locale)}
                  {isBest && <span className="ml-1" title={t("openingDNA.best")}>⭐</span>}
                  {isWorst && !isBest && <span className="ml-1" title={t("openingDNA.needsWork")}>⚠️</span>}
                </span>
                <span className={`font-bold ${winRateColor(op.winRate)}`}>
                  {displayValues[offset + i] > 0 ? `${op.winRate}%` : '0%'} {t("openingDNA.winRate")}
                </span>
              </div>
              <div className="h-2.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-purple-500 rounded-full transition-all duration-1000 ease-out"
                  style={{
                    width: `${displayValues[offset + i]}%`,
                    transitionDelay: `${i * 200}ms`,
                  }}
                />
              </div>
              <p className="text-xs text-gray-400 mt-0.5">
                {displayValues[offset + i]}% {t("openingDNA.ofGames")} · {op.gamesPlayed} {t("openingDNA.games", { count: op.gamesPlayed })}
              </p>
            </div>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="flex-1 flex flex-col gap-5 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("openingDNA.title")}</h2>
      {renderSection(t("openingDNA.asWhite"), "♔", whiteOpenings, bestWhite, worstWhite, 0, phase >= 1)}
      {renderSection(t("openingDNA.asBlack"), "♚", blackOpenings, bestBlack, worstBlack, whiteOpenings.length, phase >= 2)}
      <div className={`transition-all duration-700 ${phase >= 3 ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-4'}`}>
        <button onClick={onNext} className="w-full bg-white text-purple-700 font-bold text-lg py-4 rounded-full shadow-lg hover:scale-105 active:scale-95 transition-transform">
          {t("continue")}
        </button>
      </div>
    </div>
  );
}

function StepBuildingPlan({ t, answers, onComplete, isFetchingGames = false }: { t: any; answers: any; onComplete: () => void; isFetchingGames?: boolean }) {
  const gameData = (answers as any).gameData || null;
  const stats = gameData?.stats;
  const platformName = answers.platform === "chessdotcom" ? "Chess.com" : answers.platform === "lichess" ? "Lichess" : "";

  const items = stats
    ? [
        t("buildingPlan.foundGames", { count: stats.totalGames, platform: platformName }),
        t("buildingPlan.analyzedRepertoire"),
        t("buildingPlan.identifiedStrengths"),
        t("buildingPlan.generating"),
      ]
    : [
        t("buildingPlan.analyzing"),
        t("buildingPlan.selecting"),
        t("buildingPlan.calibrating"),
        t("buildingPlan.ready"),
      ];

  const delay = stats ? 700 : 1000;
  const [completed, setCompleted] = useState(0);

  useEffect(() => {
    if (completed < items.length) {
      const timer = setTimeout(() => setCompleted((c) => c + 1), delay);
      return () => clearTimeout(timer);
    } else if (!isFetchingGames) {
      const timer = setTimeout(onComplete, 800);
      return () => clearTimeout(timer);
    }
    // Still fetching — keep showing the loading animation, don't auto-advance
  }, [completed, items.length, onComplete, delay, isFetchingGames]);

  const progress = (completed / items.length) * 100;

  return (
    <div className="flex-1 flex flex-col gap-8 justify-center items-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("buildingPlan.title")}</h2>

      {/* Progress bar */}
      <div className="w-full h-2 bg-white/20 rounded-full overflow-hidden">
        <div
          className="h-full bg-purple-400 rounded-full transition-all duration-500 ease-out"
          style={{ width: `${progress}%` }}
        />
      </div>

      <div className="w-full space-y-4">
        {items.map((label, i) => (
          <div key={i} className={`flex items-center gap-3 transition-all duration-500 ${i < completed ? "opacity-100" : "opacity-50"}`}>
            <span className="text-2xl">{i < completed ? "✅" : "⏳"}</span>
            <span className={`font-medium ${i < completed ? "text-green-300" : "text-white/50"}`}>
              {label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StepCustomPlan({ t, answers, onNext }: { t: any; answers: any; onNext: () => void }) {
  const gameData = (answers as any).gameData || null;
  const stats = gameData?.stats;
  const focusAreas: string[] = answers.focusAreas || [];

  const bestOpening = stats?.bestOpeningsWhite?.[0];
  const worstOpening = stats?.worstOpeningsWhite?.[0];

  // Build personalized or generic weeks
  const weeks = stats
    ? [
        {
          emoji: "♚",
          label: t("customPlan.week1.label"),
          title: worstOpening
            ? t("customPlan.improveOpening", { opening: worstOpening.name, rate: Math.round(worstOpening.winRate) })
            : t("customPlan.week1.title"),
        },
        {
          emoji: "♞",
          label: t("customPlan.week2.label"),
          title: bestOpening
            ? t("customPlan.masterOpening", { opening: bestOpening.name })
            : t("customPlan.week2.title"),
        },
        {
          emoji: "♗",
          label: t("customPlan.week3.label"),
          title: focusAreas.includes("tactics")
            ? t("customPlan.tacticalPatterns")
            : focusAreas.includes("strategy")
              ? t("customPlan.strategicPlanning")
              : t("customPlan.week3.title"),
        },
        {
          emoji: "♜",
          label: t("customPlan.week4.label"),
          title: t("customPlan.endgameMastery"),
        },
      ]
    : [
        {
          emoji: "♚",
          label: t("customPlan.week1.label"),
          title: focusAreas.includes("tactics")
            ? t("customPlan.tacticalVision")
            : t("customPlan.week1.title"),
        },
        {
          emoji: "♞",
          label: t("customPlan.week2.label"),
          title: focusAreas.includes("openings")
            ? t("customPlan.openingBuilder")
            : t("customPlan.week2.title"),
        },
        {
          emoji: "♗",
          label: t("customPlan.week3.label"),
          title: focusAreas.includes("endgames")
            ? t("customPlan.endgameEssentials")
            : focusAreas.includes("strategy")
              ? t("customPlan.strategicThinking")
              : t("customPlan.week3.title"),
        },
        {
          emoji: "♜",
          label: t("customPlan.week4.label"),
          title: focusAreas.includes("calculation")
            ? t("customPlan.calculation")
            : t("customPlan.week4.title"),
        },
      ];

  const improvementMessage = stats
    ? t("customPlan.dataImprovement")
    : t("customPlan.improvement");

  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("customPlan.title")}</h2>
      <div className="space-y-3">
        {weeks.map((w, i) => (
          <div key={i} className="bg-white rounded-2xl shadow-md overflow-hidden flex">
            <div className="w-1.5 bg-purple-600" />
            <div className="p-4 flex items-center gap-3">
              <span className="text-2xl">{w.emoji}</span>
              <div>
                <div className="text-xs text-purple-600 font-bold">{w.label}</div>
                <div className="font-bold text-gray-900">{w.title}</div>
              </div>
            </div>
          </div>
        ))}
      </div>
      <p className="text-center text-white/80 text-sm">{improvementMessage}</p>
      <button onClick={onNext} className="bg-green-500 text-white font-bold text-lg py-4 rounded-full shadow-lg hover:scale-105 active:scale-95 transition-transform">
        {t("customPlan.startButton")}
      </button>
    </div>
  );
}

function StepPaywall1({ t, onNext }: { t: any; onNext: () => void }) {
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center items-center text-center">
      <div className="bg-white rounded-3xl p-8 shadow-xl w-full">
        <div className="w-28 h-28 rounded-full bg-white overflow-hidden flex items-center justify-center p-2 mx-auto mb-4 shadow-lg">
          <Image src="/static/images/chesster-logo-v3.png" alt="Chesster" width={96} height={96} />
        </div>
        <h2 className="text-2xl font-bold text-gray-900 mb-2">{t("paywall1.title")}</h2>
        <p className="text-gray-500 mb-6">{t("paywall1.subtitle")}</p>
        <button onClick={onNext} className="w-full bg-purple-600 text-white font-bold text-lg py-4 rounded-full shadow-lg hover:scale-105 active:scale-95 transition-transform">
          {t("paywall1.button")}
        </button>
        <p className="text-gray-400 text-xs mt-3">{t("paywall1.noPayment")}</p>
      </div>
    </div>
  );
}

function StepPaywall2({ t, onNext }: { t: any; onNext: () => void }) {
  const days = [
    { key: "day1", emoji: "✅" },
    { key: "day2", emoji: "🔔" },
    { key: "day3", emoji: "💳" },
  ];
  return (
    <div className="flex-1 flex flex-col gap-6 justify-center">
      <h2 className="text-2xl font-bold text-white text-center">{t("paywall2.title")}</h2>
      <div className="bg-white rounded-2xl p-6 shadow-md space-y-4">
        {days.map((d, i) => (
          <div key={d.key} className="flex items-center gap-4">
            <span className="text-2xl">{d.emoji}</span>
            <div>
              <div className="text-xs text-gray-400">{t(`paywall2.${d.key}.label`)}</div>
              <div className="font-medium text-gray-800">{t(`paywall2.${d.key}.text`)}</div>
            </div>
          </div>
        ))}
      </div>
      <p className="text-center text-white/70 text-sm">{t("paywall2.noCharge")}</p>
      <button onClick={onNext} className="bg-white text-purple-700 font-bold text-lg py-4 rounded-full shadow-lg hover:scale-105 active:scale-95 transition-transform">
        {t("continue")}
      </button>
    </div>
  );
}

function StepPaywall({ t, router }: { t: any; router: any }) {
  const [selected, setSelected] = useState<"weekly" | "monthly" | "yearly">("yearly");
  const [loading, setLoading] = useState(false);

  const planIdMap: Record<string, string | undefined> = {
    weekly: process.env.NEXT_PUBLIC_WHOP_WEEKLY_PLAN,
    monthly: process.env.NEXT_PUBLIC_WHOP_MONTHLY_PLAN,
    yearly: process.env.NEXT_PUBLIC_WHOP_YEARLY_PLAN,
  };

  const plans = [
    { key: "weekly" as const, price: t("paywall.weeklyPrice"), trial: false },
    { key: "monthly" as const, price: t("paywall.monthlyPrice"), trial: false },
    { key: "yearly" as const, price: t("paywall.yearlyPrice"), trial: true },
  ];

  const handleSubscribe = async () => {
    const planId = planIdMap[selected];
    if (!planId || loading) return;
    setLoading(true);
    try {
      const res = await fetch("/api/whop/checkout", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ planId }),
      });
      const data = await res.json();
      if (data.checkoutUrl) {
        window.location.href = data.checkoutUrl;
      }
    } catch (err) {
      console.error("Checkout error:", err);
      setLoading(false);
    }
  };

  const handleSkip = () => {
    localStorage.setItem("chesster_onboarding_complete", "true");
    localStorage.setItem("chesster_access", "limited");
    router.push("/learn");
  };

  return (
    <div className="flex-1 flex flex-col gap-4 justify-center relative">
      {/* Skip/close button */}
      <button
        onClick={handleSkip}
        className="absolute top-0 right-0 text-white/40 hover:text-white/80 p-2 z-10"
      >
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
      </button>

      <h2 className="text-2xl font-bold text-white text-center">{t("paywall.choosePlan")}</h2>

      {/* Plan cards */}
      <div className="flex flex-col gap-3">
        {plans.map((plan) => {
          const isSelected = selected === plan.key;
          const isYearly = plan.key === "yearly";
          return (
            <button
              key={plan.key}
              onClick={() => setSelected(plan.key)}
              className={`relative rounded-2xl p-4 text-left transition-all border-2 ${
                isYearly
                  ? isSelected
                    ? "bg-gradient-to-br from-purple-900/80 to-purple-800/60 border-purple-400 scale-[1.02]"
                    : "bg-gradient-to-br from-purple-900/60 to-purple-800/40 border-purple-500/50"
                  : isSelected
                    ? "bg-white/10 border-purple-400"
                    : "bg-white/5 border-white/10 opacity-75"
              }`}
            >
              {/* Best value badge */}
              {isYearly && (
                <span className="absolute -top-2.5 right-3 bg-green-500 text-white text-[10px] font-bold px-2.5 py-0.5 rounded-full">
                  {t("paywall.bestValue")}
                </span>
              )}

              <div className="flex items-center justify-between pl-8">
                <div>
                  <div className="flex items-center gap-2">
                    <span className={`font-bold ${isYearly ? "text-white text-lg" : "text-white/90"}`}>
                      {t(`paywall.${plan.key}`)}
                    </span>
                    {isYearly && (
                      <span className="bg-purple-500/40 text-purple-200 text-[10px] font-bold px-2 py-0.5 rounded-full">
                        {t("paywall.mostPopular")}
                      </span>
                    )}
                  </div>
                  {isYearly && (
                    <p className="text-green-300 text-xs mt-0.5">{t("paywall.perMonth")}</p>
                  )}
                  {isYearly && (
                    <span className="inline-block mt-1 bg-green-500/20 text-green-300 text-[10px] font-bold px-2 py-0.5 rounded-full">
                      {t("paywall.freeTrial")}
                    </span>
                  )}
                </div>
                <div className="text-right">
                  <span className={`font-bold ${isYearly ? "text-white text-lg" : "text-white/80"}`}>
                    {plan.price}
                  </span>
                </div>
              </div>

              {/* Selection indicator */}
              <div className={`absolute top-1/2 -translate-y-1/2 left-4 w-7 h-7 rounded-full border-2 flex items-center justify-center transition-all ${
                isSelected ? "border-white bg-purple-500 shadow-lg shadow-purple-500/50" : "border-white/30 bg-white/5"
              }`}>
                {isSelected && (
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                    <path d="M3.5 8.5L6.5 11.5L12.5 4.5" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                )}
              </div>
            </button>
          );
        })}
      </div>

      {/* Trust signals */}
      <div className="flex flex-col gap-1.5 mt-1">
        <p className="text-white/70 text-sm">✓ {t("paywall.cancelAnytime")}</p>
        <p className="text-white/70 text-sm">✓ {t("paywall.freeTrialYearly")}</p>
        <p className="text-white/70 text-sm">✓ {t("paywall.reminderBeforeTrial")}</p>
      </div>

      {/* CTA */}
      <button
        onClick={handleSubscribe}
        disabled={loading}
        className={`bg-green-500 text-white font-bold text-lg py-4 rounded-full shadow-lg hover:scale-105 active:scale-95 transition-transform mt-2 ${loading ? "opacity-60 cursor-wait" : ""}`}
      >
        {loading ? "..." : selected === "yearly" ? t("paywall.startFreeTrial") : t("paywall.subscribe")}
      </button>

      {/* Terms */}
      {selected === "yearly" && (
        <p className="text-white/40 text-xs text-center">{t("paywall.trialTerms")}</p>
      )}

      {/* Restore purchase */}
      <button className="text-white/40 text-xs text-center underline mt-1">
        {t("paywall.restorePurchase")}
      </button>
    </div>
  );
}
