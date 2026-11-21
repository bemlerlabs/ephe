'use client'

import { m } from 'framer-motion'
import { useRef, useEffect, useState } from 'react'

interface BlurTextProps {
  text: string
  delay?: number
  className?: string
}

export default function BlurText({ text, delay = 0, className = '' }: BlurTextProps) {
  const ref = useRef<HTMLDivElement>(null)
  const [inView, setInView] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    // DD-18: the entrance is a one-time event. The observer fires on every
    // enter/exit — without a latch the blur-in animation restarted on state
    // changes and the old plus the new copy stood one frame on top of each other.
    // Reduced motion: no entrance at all (R14 policy), the text is there at once.
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      setInView(true)
      return
    }
    const obs = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) setInView(true)
      },
      { threshold: 0.1 },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  const words = text.split(' ')

  return (
    <div ref={ref} className={`flex flex-wrap justify-center ${className}`}>
      {words.map((word, i) => (
        <m.span
          key={i}
          className="inline-block mr-[0.28em]"
          initial={{ filter: 'blur(10px)', opacity: 0, y: 50 }}
          animate={inView ? { filter: 'blur(0px)', opacity: 1, y: 0 } : {}}
          transition={{
            duration: 0.7,
            delay: i * 0.1 + delay,
            ease: [0.22, 1, 0.36, 1],
          }}
        >
          {word}
        </m.span>
      ))}
    </div>
  )
}
