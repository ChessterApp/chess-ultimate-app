"use client"

import { usePathname } from "next/navigation"
import type { ReactNode } from "react"
import { useState, useEffect } from "react"

const variants = {
  hidden: { opacity: 0, y: 8 },
  enter: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
}

export default function PageTransition({ children }: { children: ReactNode }) {
  const pathname = usePathname()
  const [FramerComponents, setFramerComponents] = useState<any>(null)

  useEffect(() => {
    // Dynamically import framer-motion only when component mounts
    import("framer-motion").then((mod) => {
      setFramerComponents({
        motion: mod.motion,
        AnimatePresence: mod.AnimatePresence,
      })
    })
  }, [])

  // Render children without animation while loading framer-motion
  if (!FramerComponents) {
    return <div>{children}</div>
  }

  const { motion, AnimatePresence } = FramerComponents

  return (
    <AnimatePresence mode="wait" initial={false}>
      <motion.div
        key={pathname}
        variants={variants}
        initial="hidden"
        animate="enter"
        exit="exit"
        transition={{ duration: 0.2, ease: "easeInOut" }}
      >
        {children}
      </motion.div>
    </AnimatePresence>
  )
}
